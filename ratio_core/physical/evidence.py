"""Deterministic region-level terrain evidence. Scores are heuristics, not probabilities."""
from __future__ import annotations
from dataclasses import asdict,dataclass
import cv2
import numpy as np
from ratio_core.dem import DEMData,terrain_derivatives,extract_patch
from ratio_core.registration import RegistrationResult,transform_points

@dataclass(frozen=True)
class PhysicalEvidence:
    feature_id:str; visual_change:float; physical_support:float|None; unsupported_risk:float|None
    comparison_quality:float; registration_quality:float; reference_quality:float
    reference_resolution:dict; valid_data_percentage:float; coverage_status:str
    support_components:dict; available_components:list[str]; component_coverage_fraction:float
    status:str; reason_codes:list[str]; reference_bbox:list[int]
    def to_dict(self):return asdict(self)

def gradient_alignment(vx,vy,dx,dy,valid_mask=None,epsilon=1e-4):
    """Mean orientation-insensitive |cos| between intensity and elevation gradients.

    Returns (None,"GRADIENT_ALIGNMENT_UNRESOLVED") when vectors/overlap are
    insufficient. A numeric zero is reserved for resolved orthogonality.
    """
    vx,vy,dx,dy=map(lambda a:np.asarray(a,float),(vx,vy,dx,dy))
    if not (vx.shape==vy.shape==dx.shape==dy.shape):raise ValueError("Gradient arrays must share shape")
    valid=np.isfinite(vx)&np.isfinite(vy)&np.isfinite(dx)&np.isfinite(dy)
    if valid_mask is not None:valid&=np.asarray(valid_mask,bool)
    vm=np.hypot(vx,vy);dm=np.hypot(dx,dy);valid&=(vm>epsilon)&(dm>epsilon)
    if not valid.any():return None,'GRADIENT_ALIGNMENT_UNRESOLVED'
    cosine=np.abs((vx[valid]*dx[valid]+vy[valid]*dy[valid])/(vm[valid]*dm[valid]))
    return round(float(np.mean(np.clip(cosine,0,1))),4),'GRADIENT_ALIGNMENT_RESOLVED'

def resolution_adequacy(feature_scale_m,reference_resolution_m,config):
    if feature_scale_m<=0 or reference_resolution_m<=0:return 'REFERENCE_UNCERTAIN',0.0
    ratio=feature_scale_m/reference_resolution_m;rc=config['reference']
    if ratio>=float(rc['adequate_feature_pixels']):status='REFERENCE_RESOLUTION_ADEQUATE'
    elif ratio>=float(rc['uncertain_feature_pixels']):status='REFERENCE_UNCERTAIN'
    else:status='REFERENCE_TOO_COARSE'
    return status,round(float(ratio),4)

def weighted_physical_support(components,weights):
    available={k:float(v) for k,v in components.items() if v is not None and np.isfinite(v)}
    denominator=sum(float(weights[k]) for k in available)
    if denominator<=0:return None,[],0.0
    score=sum(float(weights[k])*v for k,v in available.items())/denominator
    return round(float(np.clip(score,0,1)),4),list(available),round(denominator/sum(weights.values()),4)

def unsupported_risk(visual_change,physical_support,comparison_quality,registration_quality,reference_adequacy,risk_config=None):
    if physical_support is None:return None
    factors={'visual_change':visual_change,'lack_of_physical_support':1-physical_support,'comparison_quality':comparison_quality,'registration_quality':registration_quality,'reference_adequacy':reference_adequacy}
    exponents={k:1.0 for k in factors} if risk_config is None else risk_config['exponents']
    value=1.0
    for key,factor in factors.items():value*=float(np.clip(factor,0,1))**float(exponents[key])
    return round(float(np.clip(value,0,1)),4)

def _coverage_status(fraction,config):
    rc=config['reference']
    if fraction<float(rc['unavailable_valid_fraction']):return 'REFERENCE_UNAVAILABLE'
    if fraction<float(rc['low_valid_fraction']):return 'LOW_REFERENCE_COVERAGE'
    if fraction<float(rc['adequate_valid_fraction']):return 'MEDIUM_REFERENCE_COVERAGE'
    return 'HIGH_REFERENCE_COVERAGE'

def _reference_quality(registration,valid_fraction,resolution_status,config):
    rw=config['reference']['quality_weights']; resolution={'REFERENCE_RESOLUTION_ADEQUATE':1.0,'REFERENCE_UNCERTAIN':.55,'REFERENCE_TOO_COARSE':.15}.get(resolution_status,0)
    coverage=np.clip(valid_fraction/float(config['reference']['adequate_valid_fraction']),0,1)
    return round(float(rw['registration']*registration+rw['coverage']*coverage+rw['resolution']*resolution),4)

def verify_region(feature,original_gray,enhanced_gray,dem:DEMData,registration:RegistrationResult,comparison_quality,config,illumination=None):
    """Cross-check one Phase-1 region against a registered DEM patch.

    DEM support and local relief indicate terrain signal presence, not feature identity.
    Gradient alignment is directional consistency. Hillshade is unavailable unless
    acquisition illumination is supplied. Missing components are omitted, never zeroed.
    """
    x,y,w,h=feature['bbox'];corners=np.array([[x,y],[x+w,y],[x,y+h],[x+w,y+h]],float)
    mapped=transform_points(registration.matrix,corners);x0,y0=np.floor(mapped.min(axis=0)).astype(int);x1,y1=np.ceil(mapped.max(axis=0)).astype(int)
    ref_bbox=(int(x0),int(y0),max(1,int(x1-x0)),max(1,int(y1-y0)))
    try:
        elevation=extract_patch(dem.elevation_m,ref_bbox);valid=extract_patch(dem.valid_mask,ref_bbox)
    except ValueError:
        return PhysicalEvidence(feature['id'],feature['visual_score'],None,None,comparison_quality,registration.quality_score,0,
            {'meters_per_pixel':max(dem.x_resolution_m,dem.y_resolution_m),'feature_scale_m':0,'resolution_ratio':0,'status':'REFERENCE_UNCERTAIN','adequate_for_feature':False},0,'REFERENCE_UNAVAILABLE',
            {'dem_support':None,'gradient_alignment':None,'hillshade_support':None,'local_relief_support':None},[],0,'REFERENCE_UNAVAILABLE',['NO_OVERLAP'],list(ref_bbox))
    fraction=float(valid.mean());coverage=_coverage_status(fraction,config);resolution=max(dem.x_resolution_m,dem.y_resolution_m)
    feature_scale=min(ref_bbox[2]*dem.x_resolution_m,ref_bbox[3]*dem.y_resolution_m);resolution_status,ratio=resolution_adequacy(feature_scale,resolution,config)
    ref_quality=_reference_quality(registration.quality_score,fraction,resolution_status,config)
    components={'dem_support':None,'gradient_alignment':None,'hillshade_support':None,'local_relief_support':None};reasons=['VISUAL_CHANGE_DETECTED']
    if coverage=='REFERENCE_UNAVAILABLE':
        return PhysicalEvidence(feature['id'],feature['visual_score'],None,None,comparison_quality,registration.quality_score,ref_quality,
          {'meters_per_pixel':resolution,'feature_scale_m':round(feature_scale,3),'resolution_ratio':ratio,'status':resolution_status,'adequate_for_feature':False},round(fraction*100,3),coverage,components,[],0,'REFERENCE_UNAVAILABLE',reasons+['INSUFFICIENT_REFERENCE_COVERAGE'],list(ref_bbox))
    if resolution_status=='REFERENCE_TOO_COARSE':reasons.append('REFERENCE_TOO_COARSE')
    derivatives=terrain_derivatives(dem)
    gx=extract_patch(derivatives.gradient_x,ref_bbox);gy=extract_patch(derivatives.gradient_y,ref_bbox);mag=extract_patch(derivatives.gradient_magnitude,ref_bbox)
    terrain_valid=valid&np.isfinite(mag)
    if terrain_valid.any():
        components['dem_support']=round(float(np.clip(np.nanmean(mag[terrain_valid])/float(config['physical_support']['terrain_gradient_full_support']),0,1)),4)
        relief=float(np.nanmax(elevation[valid])-np.nanmin(elevation[valid]))
        components['local_relief_support']=round(float(np.clip(relief/float(config['physical_support']['local_relief_full_support_m']),0,1)),4)
    visual=enhanced_gray[y:y+h,x:x+w]
    if visual.size and elevation.size:
        visual=cv2.resize(visual,(elevation.shape[1],elevation.shape[0]),interpolation=cv2.INTER_AREA)
        vx=cv2.Sobel(visual.astype(np.float32),cv2.CV_32F,1,0,ksize=3);vy=cv2.Sobel(visual.astype(np.float32),cv2.CV_32F,0,1,ksize=3)
        alignment,alignment_status=gradient_alignment(vx,vy,gx,gy,terrain_valid,float(config['physical_support']['gradient_epsilon']))
        components['gradient_alignment']=alignment;reasons.append(alignment_status)
        if illumination is not None:
            shade=extract_patch(derivatives.hillshade,ref_bbox);v=visual[terrain_valid];s=shade[terrain_valid]
            if len(v)>3 and np.std(v)>1e-6 and np.std(s)>1e-6:components['hillshade_support']=round(float(np.clip((np.corrcoef(v,s)[0,1]+1)/2,0,1)),4)
        else:reasons.append('HILLSHADE_COMPARISON_UNAVAILABLE')
    support,available,component_fraction=weighted_physical_support(components,config['physical_support']['weights'])
    risk=unsupported_risk(feature['visual_score'],support,comparison_quality,registration.quality_score,ref_quality,config['risk'])
    preconditions=(registration.status=='REGISTRATION_SUCCESS' and registration.quality_score>=.75 and coverage=='HIGH_REFERENCE_COVERAGE' and resolution_status=='REFERENCE_RESOLUTION_ADEQUATE')
    ps=config['physical_support']
    if resolution_status!='REFERENCE_RESOLUTION_ADEQUATE':status='REFERENCE_INADEQUATE'
    elif registration.status!='REGISTRATION_SUCCESS':status='UNRESOLVED';reasons.append('REGISTRATION_QUALITY_INSUFFICIENT')
    elif support is None:status='UNRESOLVED'
    elif support>=float(ps['supported_threshold']):status='SUPPORTED';reasons.append('PHYSICAL_SUPPORT_STRONG')
    elif support>=float(ps['partial_threshold']):status='PARTIALLY_SUPPORTED';reasons.append('PHYSICAL_SUPPORT_PARTIAL')
    elif preconditions and components['gradient_alignment'] is not None and support<=float(ps['contradiction_threshold']):status='CONTRADICTED';reasons.append('PHYSICAL_DISAGREEMENT_STRONG')
    else:status='UNRESOLVED';reasons.append('PHYSICAL_EVIDENCE_AMBIGUOUS')
    return PhysicalEvidence(feature['id'],feature['visual_score'],support,risk,comparison_quality,registration.quality_score,ref_quality,
      {'meters_per_pixel':resolution,'feature_scale_m':round(feature_scale,3),'resolution_ratio':ratio,'status':resolution_status,'adequate_for_feature':resolution_status=='REFERENCE_RESOLUTION_ADEQUATE'},
      round(fraction*100,3),coverage,components,available,component_fraction,status,reasons,list(ref_bbox))
