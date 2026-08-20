from __future__ import annotations
import hashlib,json
from pathlib import Path
from backend.app.core.config import load_phase2_config,load_scientific_config
from backend.app.services.store import get_analysis,get_image,analysis_path,utc_now
from backend.app.services.datasets import get_dataset,resolve_dataset_path
from ratio_core.evidence import analyze_image_pair
from ratio_core.dem import load_dem
from ratio_core.registration import auto_dimension_registration,fit_affine,fit_affine_validated,RegistrationResult
from ratio_core.physical import verify_region
from ratio_core.policy import evaluate_policy
from ratio_core.provenance import build_passport


def _write(path,obj):path.write_text(json.dumps(obj,indent=2),encoding='utf-8')
def _read(path):return json.loads(path.read_text())

def attach_reference(analysis_id,dataset_id):
    analysis=get_analysis(analysis_id);dataset=get_dataset(dataset_id);folder=analysis_path(analysis_id)
    reference_compatibility={'status':'UNAVAILABLE','score':None,'reason':'REFERENCE_IMAGE_NOT_PROVIDED'}
    image_path=dataset.get('image_path')
    if image_path:
        import cv2
        from backend.app.core.config import ROOT
        p=Path(image_path);p=p if p.is_absolute() else ROOT/p
        reference_image=cv2.imread(str(p),cv2.IMREAD_UNCHANGED)
        if reference_image is not None:
            _,uploaded=get_image(analysis['inputs']['original']['id'])
            assessed=analyze_image_pair(uploaded,reference_image,load_scientific_config())
            reference_compatibility={'status':assessed.comparison.comparison_status,'score':assessed.comparison.compatibility_score,'reason':assessed.comparison.reason_code}
    record={'dataset_id':dataset_id,'attached_at':utc_now(),'classification':dataset['classification'],'product_id':dataset.get('product_id'),'reference_image_compatibility':reference_compatibility}
    _write(folder/'reference.json',record)
    registration=None
    if dataset.get('metadata_alignment_reliable') and dataset.get('reference_dimensions') and reference_compatibility['status']=='COMPARABLE':
        dims=(analysis['dimensions']['analysis_dimensions'] or analysis['dimensions']['original_dimensions'])
        registration=auto_dimension_registration(tuple(dims),tuple(dataset['reference_dimensions']),True).to_dict();_write(folder/'registration.json',registration)
    return {'reference':record,'registration':registration}

def save_manual_registration(analysis_id,image_points,reference_points,validation_image_points=None,validation_reference_points=None):
    """Phase 3B: three fit points determine the transform; optional independent
    validation points test it without participating in the fit."""
    analysis=get_analysis(analysis_id);folder=analysis_path(analysis_id);ref_path=folder/'reference.json'
    if not ref_path.exists():raise FileNotFoundError('REFERENCE_UNAVAILABLE')
    config=load_phase2_config();dims=analysis['dimensions']['analysis_dimensions'] or analysis['dimensions']['original_dimensions']
    if validation_image_points or validation_reference_points:
        result=fit_affine_validated(image_points,reference_points,tuple(dims),config,
                                    validation_image_points or None,validation_reference_points or None)
    else:
        result=fit_affine(image_points,reference_points,tuple(dims),config)
    _write(folder/'registration.json',result.to_dict());return result.to_dict()

def _unavailable_feature(feature,comparison_quality):
    return {'feature_id':feature['id'],'visual_change':feature['visual_score'],'physical_support':None,'unsupported_risk':None,
      'comparison_quality':comparison_quality,'registration_quality':0.0,'reference_quality':0.0,
      'reference_resolution':{'meters_per_pixel':None,'adequate_for_feature':False,'status':'REFERENCE_UNAVAILABLE'},
      'valid_data_percentage':0.0,'coverage_status':'REFERENCE_UNAVAILABLE','support_components':{'dem_support':None,'gradient_alignment':None,'hillshade_support':None,'local_relief_support':None},
      'available_components':[],'component_coverage_fraction':0.0,'status':'REFERENCE_UNAVAILABLE','reason_codes':['REFERENCE_UNAVAILABLE'],'reference_bbox':[]}

def _registration_failed_feature(feature,comparison_quality,registration):
    """Phase 3B: a failed registration leaves physical status UNRESOLVED, never
    CONTRADICTED and never REFERENCE_UNAVAILABLE — the reference may exist but the
    transform could not be trusted."""
    return {'feature_id':feature['id'],'visual_change':feature['visual_score'],'physical_support':None,'unsupported_risk':None,
      'comparison_quality':comparison_quality,'registration_quality':float(registration.get('quality_score',0.0)),'reference_quality':0.0,
      'reference_resolution':{'meters_per_pixel':None,'adequate_for_feature':False,'status':'REFERENCE_UNCERTAIN'},
      'valid_data_percentage':0.0,'coverage_status':'REFERENCE_UNCERTAIN','support_components':{'dem_support':None,'gradient_alignment':None,'hillshade_support':None,'local_relief_support':None},
      'available_components':[],'component_coverage_fraction':0.0,'status':'UNRESOLVED','reason_codes':['REGISTRATION_QUALITY_INSUFFICIENT'],'reference_bbox':[]}

def verify_analysis(analysis_id,mission):
    analysis=get_analysis(analysis_id);folder=analysis_path(analysis_id);config=load_phase2_config();features=analysis['features'];comparison=analysis['comparison_status'];comparison_quality=analysis['compatibility']['score']
    meaningful=[f for f in features if f['visual_score']>=config['visual']['min_meaningful_change']]
    fast_path=comparison=='COMPARABLE' and not meaningful
    dataset=None;registration=None;evidence=[];verification_status='COMPLETED'
    if comparison!='COMPARABLE':verification_status='NOT_PERFORMED_COMPARABILITY'
    elif fast_path:verification_status='NOT_REQUIRED'
    else:
        ref_path=folder/'reference.json'
        if not ref_path.exists():
            verification_status='REFERENCE_UNAVAILABLE';evidence=[_unavailable_feature(f,comparison_quality) for f in meaningful]
        else:
            ref=_read(ref_path);dataset=get_dataset(ref['dataset_id']);reg_path=folder/'registration.json'
            if not reg_path.exists():
                verification_status='REGISTRATION_FAILED';evidence=[_unavailable_feature(f,comparison_quality) for f in meaningful]
            else:
                registration=_read(reg_path)
                if registration['status']=='REGISTRATION_FAILED':
                    verification_status='REGISTRATION_FAILED'
                    evidence=[_registration_failed_feature(f,comparison_quality,registration) for f in meaningful]
                else:
                    dem=load_dem(str(resolve_dataset_path(dataset)));_,original=get_image(analysis['inputs']['original']['id']);_,enhanced=get_image(analysis['inputs']['enhanced']['id'])
                    rerun=analyze_image_pair(original,enhanced,load_scientific_config())
                    if rerun.normalized_original is None:verification_status='NOT_PERFORMED_COMPARABILITY'
                    else:
                        reg=RegistrationResult(**registration)
                        evidence=[verify_region(f,rerun.normalized_original,rerun.normalized_enhanced,dem,reg,comparison_quality,config,dataset.get('illumination')).to_dict() for f in meaningful]
    policy=evaluate_policy(mission,comparison,evidence,config,fast_path).to_dict()
    record={'schema_version':'2.0','analysis_id':analysis_id,'created_at':utc_now(),'mission_profile':mission,
      'comparison_status':comparison,'comparison_quality':comparison_quality,'dem_verification_status':verification_status,
      'no_significant_change':fast_path,'visual_change_summary':{'meaningful_region_count':len(meaningful),'maximum_region_visual_change':max([f['visual_score'] for f in features],default=0)},
      'dataset':None if dataset is None else {k:dataset.get(k) for k in ['id','classification','mission','instrument','product_id','source','resolution_m_per_pixel','description','sha256']},
      'registration':registration,'features':evidence,'policy':policy,'configuration':config,
      'artifacts':{} if dataset is None else {'dem':f'/api/datasets/{dataset["id"]}/preview?kind=dem','hillshade':f'/api/datasets/{dataset["id"]}/preview?kind=hillshade'}}
    _write(folder/'phase2.json',record)
    hashes={}
    for name in ['difference_map.png','suspicious_mask.png','annotated.png']:
        p=folder/name
        if p.exists():hashes[name]=hashlib.sha256(p.read_bytes()).hexdigest()
    passport=build_passport(analysis,dataset,registration,record,hashes);_write(folder/'passport.json',passport)
    try:
        from backend.app.services import evidence_api
        _write(folder/'evidence_report.json',evidence_api.evidence_report(analysis_id))
    except Exception:
        pass  # evidence report is an additive Phase-3 artifact; verification must not fail without it
    return record

def get_physical(analysis_id):
    path=analysis_path(analysis_id)/'phase2.json'
    if not path.exists():raise FileNotFoundError('PHYSICAL_EVIDENCE_UNAVAILABLE')
    return _read(path)

def get_passport(analysis_id):
    path=analysis_path(analysis_id)/'passport.json'
    if not path.exists():raise FileNotFoundError('PASSPORT_UNAVAILABLE')
    return _read(path)

def export_analysis(analysis_id):
    phase2=get_physical(analysis_id);decision=phase2['policy']['decision']
    if decision not in {'SAFE_TO_EXPORT','NO_SIGNIFICANT_CHANGE'}:raise PermissionError('POLICY_BLOCKED_EXPORT')
    payload={'analysis_id':analysis_id,'designation':phase2['policy']['export_designation'],'mission_profile':phase2['mission_profile'],'policy':phase2['policy'],'passport':get_passport(analysis_id)}
    path=analysis_path(analysis_id)/'mission_export.json';_write(path,payload);return path,payload
