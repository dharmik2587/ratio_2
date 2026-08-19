"""Deterministic mission gates; no LLM or learned model participates."""
from dataclasses import asdict,dataclass

@dataclass(frozen=True)
class MissionDecision:
    mission_profile:str;decision:str;export_designation:str;reason_codes:list[str]
    def to_dict(self):return asdict(self)

def evaluate_policy(mission,comparison_status,features,config,no_significant_change=False):
    if mission not in config['missions']:raise ValueError('INVALID_MISSION_PROFILE')
    if comparison_status=='INCOMPARABLE_IMAGES':return MissionDecision(mission,'REVIEW_REQUIRED','REVIEW_REQUIRED',['INPUT_IMAGES_INCOMPARABLE'])
    if comparison_status!='COMPARABLE':return MissionDecision(mission,'REVIEW_REQUIRED','REVIEW_REQUIRED',['COMPARABILITY_REVIEW_REQUIRED'])
    if no_significant_change:return MissionDecision(mission,'NO_SIGNIFICANT_CHANGE','SAFE_TO_EXPORT',['DEM_VERIFICATION_NOT_REQUIRED'])
    if not features:return MissionDecision(mission,'REVIEW_REQUIRED','REVIEW_REQUIRED',['PHYSICAL_EVIDENCE_UNAVAILABLE'])
    thresholds=config['missions'][mission];reasons=[];critical=False;hard_block=False;low_support_with_adequate_reference=False
    for f in features:
        if f['status']=='CONTRADICTED':hard_block=True;reasons.append(f['feature_id']+':PHYSICAL_EVIDENCE_CONTRADICTED')
        if f['status'] in {'REFERENCE_UNAVAILABLE','REFERENCE_INADEQUATE','UNRESOLVED'}:critical=True;reasons.append(f['feature_id']+':'+f['status'])
        if f['registration_quality']<thresholds['min_registration_quality']:critical=True;reasons.append(f['feature_id']+':REGISTRATION_GATE_FAILED')
        if f['reference_quality']<thresholds['min_reference_quality']:critical=True;reasons.append(f['feature_id']+':REFERENCE_GATE_FAILED')
        if f['physical_support'] is None or f['physical_support']<thresholds['min_physical_support']:
            critical=True;reasons.append(f['feature_id']+':PHYSICAL_SUPPORT_GATE_FAILED')
            if f['physical_support'] is not None and f['reference_quality']>=thresholds['min_reference_quality'] and f['registration_quality']>=thresholds['min_registration_quality'] and f['status'] not in {'REFERENCE_UNAVAILABLE','REFERENCE_INADEQUATE'}:low_support_with_adequate_reference=True
        if f['unsupported_risk'] is not None and f['unsupported_risk']>thresholds['max_unsupported_risk']:
            critical=True;reasons.append(f['feature_id']+':UNSUPPORTED_RISK_GATE_FAILED')
            if f['unsupported_risk']>=config['risk']['block_threshold']:hard_block=True
    if hard_block or (mission=='ROUTE_PLANNING' and low_support_with_adequate_reference):
        return MissionDecision(mission,'NOT_SAFE','NOT_SAFE_FOR_NAVIGATION',sorted(set(reasons)))
    if critical:return MissionDecision(mission,'REVIEW_REQUIRED','REVIEW_REQUIRED',sorted(set(reasons)))
    return MissionDecision(mission,'SAFE_TO_EXPORT','ROUTE_PLANNING_CANDIDATE' if mission=='ROUTE_PLANNING' else 'MISSION_USE_CANDIDATE',['ALL_MANDATORY_GATES_PASSED'])
