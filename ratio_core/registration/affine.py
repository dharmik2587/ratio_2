"""Image-pixel to reference-pixel affine registration with explicit quality.

Phase 2 (frozen): three-point least-squares affine fit with quality caps.

Phase 3 (additive): `fit_affine_validated` keeps the three fit points as the
transform authority and adds INDEPENDENT validation points that did not
participate in the fit. A zero fit RMSE is never treated as proof of correct
registration: with exactly three non-collinear fit points the fit residual is
zero by construction, so only the independent points test the transform.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import numpy as np

@dataclass(frozen=True)
class RegistrationResult:
    method:str; status:str; matrix:list[list[float]]; rmse_px:float; max_error_px:float
    quality_score:float; quality_label:str; image_points:list[list[float]]; reference_points:list[list[float]]
    validation_basis:str; timestamp:str
    # Phase-3 additive fields (defaults keep Phase-2 records unchanged)
    fit_rmse_px:float = 0.0
    fit_max_error_px:float = 0.0
    fit_point_count:int = 0
    validation_points:list[list[float]] | None = None
    validation_residuals_px:list[float] | None = None
    validation_rmse_px:float | None = None
    validation_max_error_px:float | None = None
    validation_point_count:int = 0
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

def _fit_matrix(src:np.ndarray,dst:np.ndarray)->np.ndarray:
    design=np.c_[src,np.ones(len(src))]
    if np.linalg.matrix_rank(design)<3: raise ValueError("DEGENERATE_CONTROL_POINTS")
    params=np.linalg.lstsq(design,dst,rcond=None)[0]; matrix=np.eye(3);matrix[:2,:]=params.T
    return matrix

def fit_affine(image_points,reference_points,image_dimensions,config)->RegistrationResult:
    """Least-squares affine fit for >=3 correspondences. PHASE-2 FROZEN.

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

def fit_affine_validated(image_points,reference_points,image_dimensions,config,validation_image_points=None,validation_reference_points=None)->RegistrationResult:
    """PHASE 3B — three fit points plus independent validation points.

    The first three correspondences define the affine transform exactly as in
    Phase 2. Any additional correspondences are INDEPENDENT: they never enter the
    fit; their residuals test the transform against terrain it has not seen.

    Status levels:
      INVALID — validation residual exceeds the configured maximum, or the fit
                geometry/control points are unusable.
      LOW     — fit accepted but residuals are poor.
      MEDIUM  — acceptable residuals within the medium band.
      HIGH    — fit and independent residuals within the high-quality band.

    Phase-2 gates are preserved: exactly three points still produce
    MINIMAL_EXACT_FIT with the quality cap, and an unvalidated minimal fit can
    never reach a higher quality than the frozen Phase-2 cap.
    """
    src=np.asarray(image_points,float);dst=np.asarray(reference_points,float)
    if src.shape!=dst.shape or src.ndim!=2 or src.shape[1]!=2 or len(src)<3: raise ValueError("INSUFFICIENT_CONTROL_POINTS")
    if not np.all(np.isfinite(src)) or not np.all(np.isfinite(dst)): raise ValueError("INVALID_CONTROL_POINTS")
    vsrc=np.asarray(validation_image_points or [],float);vdst=np.asarray(validation_reference_points or [],float)
    if vsrc.shape!=vdst.shape or vsrc.ndim!=2 or (len(vsrc)>0 and vsrc.shape[1]!=2): raise ValueError("INVALID_VALIDATION_POINTS")
    if len(vsrc)>0 and not (np.all(np.isfinite(vsrc)) and np.all(np.isfinite(vdst))): raise ValueError("INVALID_VALIDATION_POINTS")
    matrix=_fit_matrix(src,dst)
    predicted=transform_points(matrix,src);errors=np.linalg.norm(predicted-dst,axis=1)
    fit_rmse=float(np.sqrt(np.mean(errors**2)));fit_max=float(errors.max())
    rc=config['registration']
    geom=_geometry_quality(src,image_dimensions)
    max_validation_px=float(rc.get('max_validation_error_px',20.0))
    if len(vsrc)==0:
        # Backwards-compatible with Phase-2 semantics when no independent point exists.
        residual_quality=float(np.exp(-fit_rmse/max(float(rc['medium_rmse_px']),1e-6)))
        quality=geom*residual_quality
        if len(src)==3: quality=min(quality,float(rc['minimal_fit_quality_cap']))
        if geom<.1: status,label='REGISTRATION_FAILED','LOW'
        elif fit_rmse<=float(rc['high_rmse_px']):status,label='REGISTRATION_SUCCESS','HIGH' if quality>=.75 else 'MEDIUM'
        elif fit_rmse<=float(rc['medium_rmse_px']):status,label='REGISTRATION_REVIEW','MEDIUM'
        else:status,label='REGISTRATION_FAILED','LOW'
        basis='MINIMAL_EXACT_FIT' if len(src)==3 else 'LEAST_SQUARES_VALIDATED'
        return RegistrationResult('MANUAL_3_POINT',status,matrix.round(10).tolist(),round(fit_rmse,4),round(fit_max,4),round(quality,4),label,src.tolist(),dst.tolist(),basis,datetime.now(timezone.utc).isoformat(),
            fit_rmse_px=round(fit_rmse,4),fit_max_error_px=round(fit_max,4),fit_point_count=len(src),
            validation_points=None,validation_residuals_px=None,validation_rmse_px=None,validation_max_error_px=None,validation_point_count=0)
    vpred=transform_points(matrix,vsrc);verr=np.linalg.norm(vpred-vdst,axis=1)
    v_rmse=float(np.sqrt(np.mean(verr**2)));v_max=float(verr.max())
    fit_quality=float(np.exp(-fit_rmse/max(float(rc['medium_rmse_px']),1e-6)))
    v_quality=float(np.exp(-v_rmse/max(float(rc['medium_rmse_px']),1e-6)))
    quality=geom*fit_quality*v_quality
    # Independent validation can never push a minimal fit above the Phase-2 cap.
    quality=min(quality,float(rc.get('validated_fit_quality_cap',rc['minimal_fit_quality_cap'])))
    basis='FIT_3_VALIDATE_INDEPENDENT'
    if geom<.1: status,label='REGISTRATION_FAILED','LOW'
    elif v_max>max_validation_px: status,label='REGISTRATION_FAILED','INVALID'
    elif v_max<=float(rc['high_rmse_px']): status,label='REGISTRATION_SUCCESS','HIGH' if quality>=.75 else 'MEDIUM'
    elif v_max<=float(rc['medium_rmse_px']): status,label='REGISTRATION_REVIEW','MEDIUM'
    else: status,label='REGISTRATION_REVIEW','LOW'
    return RegistrationResult('MANUAL_3_POINT_VALIDATED',status,matrix.round(10).tolist(),round(fit_rmse,4),round(fit_max,4),round(quality,4),label,src.tolist(),dst.tolist(),basis,datetime.now(timezone.utc).isoformat(),
        fit_rmse_px=round(fit_rmse,4),fit_max_error_px=round(fit_max,4),fit_point_count=len(src),
        validation_points=vsrc.tolist(),validation_residuals_px=[round(float(x),4) for x in verr],
        validation_rmse_px=round(v_rmse,4),validation_max_error_px=round(v_max,4),validation_point_count=len(vsrc))

def auto_dimension_registration(image_dimensions,reference_dimensions,metadata_reliable=True)->RegistrationResult:
    """Affine map for a manifest-declared common footprint, not feature matching."""
    if not metadata_reliable: raise ValueError("REGISTRATION_FAILED")
    iw,ih=image_dimensions;rw,rh=reference_dimensions
    if min(iw,ih,rw,rh)<2: raise ValueError("REGISTRATION_FAILED")
    matrix=np.array([[(rw-1)/(iw-1),0,0],[0,(rh-1)/(ih-1),0],[0,0,1]],float)
    return RegistrationResult('AUTO_METADATA','REGISTRATION_SUCCESS',matrix.tolist(),0.0,0.0,.98,'HIGH',[],[],'MANIFEST_COMMON_FOOTPRINT',datetime.now(timezone.utc).isoformat())
