"""Image-pixel to reference-pixel affine registration with explicit quality."""
from __future__ import annotations
from dataclasses import asdict,dataclass
from datetime import datetime,timezone
import numpy as np

@dataclass(frozen=True)
class RegistrationResult:
    method:str; status:str; matrix:list[list[float]]; rmse_px:float; max_error_px:float
    quality_score:float; quality_label:str; image_points:list[list[float]]; reference_points:list[list[float]]
    validation_basis:str; timestamp:str
    def to_dict(self): return asdict(self)

def transform_points(matrix,points):
    m=np.asarray(matrix,float);p=np.asarray(points,float)
    return np.c_[p,np.ones(len(p))]@m.T[:, :2]

def _geometry_quality(points:np.ndarray,image_dimensions:tuple[int,int])->float:
    centered=points-points.mean(axis=0); singular=np.linalg.svd(centered,compute_uv=False)
    if singular[-1]<1e-8:return 0.0
    bbox_area=max(1.0,image_dimensions[0]*image_dimensions[1]);
    if len(points)==3:
        u,v=points[1]-points[0],points[2]-points[0];area=abs(u[0]*v[1]-u[1]*v[0])/2
    else: area=np.ptp(points[:,0])*np.ptp(points[:,1])
    return float(np.clip(area/(bbox_area*.15),0,1)*np.clip(singular[-1]/singular[0]*5,0,1))

def fit_affine(image_points,reference_points,image_dimensions,config)->RegistrationResult:
    """Least-squares affine fit for >=3 correspondences.

    Exactly three non-collinear points are an exact fit, so residual cannot detect a
    wrong landmark correspondence. Quality is capped and provenance says MINIMAL_EXACT_FIT.
    """
    src=np.asarray(image_points,float);dst=np.asarray(reference_points,float)
    if src.shape!=dst.shape or src.ndim!=2 or src.shape[1]!=2 or len(src)<3: raise ValueError("INSUFFICIENT_CONTROL_POINTS")
    if not np.all(np.isfinite(src)) or not np.all(np.isfinite(dst)): raise ValueError("INVALID_CONTROL_POINTS")
    design=np.c_[src,np.ones(len(src))]
    if np.linalg.matrix_rank(design)<3: raise ValueError("DEGENERATE_CONTROL_POINTS")
    params=np.linalg.lstsq(design,dst,rcond=None)[0]; matrix=np.eye(3);matrix[:2,:]=params.T
    predicted=transform_points(matrix,src);errors=np.linalg.norm(predicted-dst,axis=1)
    rmse=float(np.sqrt(np.mean(errors**2)));maximum=float(errors.max());geom=_geometry_quality(src,image_dimensions)
    rc=config['registration']; residual_quality=float(np.exp(-rmse/max(float(rc['medium_rmse_px']),1e-6)))
    quality=geom*residual_quality;basis='LEAST_SQUARES_VALIDATED' if len(src)>3 else 'MINIMAL_EXACT_FIT'
    if len(src)==3: quality=min(quality,float(rc['minimal_fit_quality_cap']))
    if geom<.1: status,label='REGISTRATION_FAILED','LOW'
    elif rmse<=float(rc['high_rmse_px']):status,label='REGISTRATION_SUCCESS','HIGH' if quality>=.75 else 'MEDIUM'
    elif rmse<=float(rc['medium_rmse_px']):status,label='REGISTRATION_REVIEW','MEDIUM'
    else:status,label='REGISTRATION_FAILED','LOW'
    return RegistrationResult('MANUAL_3_POINT',status,matrix.round(10).tolist(),round(rmse,4),round(maximum,4),round(quality,4),label,src.tolist(),dst.tolist(),basis,datetime.now(timezone.utc).isoformat())

def auto_dimension_registration(image_dimensions,reference_dimensions,metadata_reliable=True)->RegistrationResult:
    """Affine map for a manifest-declared common footprint, not feature matching."""
    if not metadata_reliable: raise ValueError("REGISTRATION_FAILED")
    iw,ih=image_dimensions;rw,rh=reference_dimensions
    if min(iw,ih,rw,rh)<2: raise ValueError("REGISTRATION_FAILED")
    matrix=np.array([[(rw-1)/(iw-1),0,0],[0,(rh-1)/(ih-1),0],[0,0,1]],float)
    return RegistrationResult('AUTO_METADATA','REGISTRATION_SUCCESS',matrix.tolist(),0.0,0.0,.98,'HIGH',[],[],'MANIFEST_COMMON_FOOTPRINT',datetime.now(timezone.utc).isoformat())
