from __future__ import annotations
import math

def _unit(value,name):
    value=float(value)
    if not math.isfinite(value) or not 0<=value<=1:raise ValueError(f'{name} must be in [0,1]')

def _weights(values,name):
    for value in values.values():_unit(value,name)
    if abs(sum(map(float,values.values()))-1)>1e-6:raise ValueError(f'{name} must sum to 1')

def validate_phase2_config(config):
    try:
        _unit(config['visual']['min_meaningful_change'],'min meaningful change')
        ps=config['physical_support'];_weights(ps['weights'],'physical support weights')
        for k in ['supported_threshold','partial_threshold','contradiction_threshold']:_unit(ps[k],k)
        if not float(ps['contradiction_threshold'])<float(ps['partial_threshold'])<float(ps['supported_threshold']):raise ValueError('Physical support thresholds must be ordered')
        if float(ps['gradient_epsilon'])<=0 or float(ps['terrain_gradient_full_support'])<=0 or float(ps['local_relief_full_support_m'])<=0:raise ValueError('Physical scales must be positive')
        ref=config['reference'];_weights(ref['quality_weights'],'reference quality weights')
        for k in ['unavailable_valid_fraction','low_valid_fraction','adequate_valid_fraction']:_unit(ref[k],k)
        if not float(ref['unavailable_valid_fraction'])<float(ref['low_valid_fraction'])<float(ref['adequate_valid_fraction']):raise ValueError('Reference coverage thresholds must be ordered')
        risk=config['risk'];_unit(risk['review_threshold'],'risk review threshold');_unit(risk['block_threshold'],'risk block threshold')
        if risk['formula']!='multiplicative_power_product':raise ValueError('Unsupported risk formula')
        expected={'visual_change','lack_of_physical_support','comparison_quality','registration_quality','reference_adequacy'}
        if set(risk['exponents'])!=expected or any(not math.isfinite(float(v)) or float(v)<0 for v in risk['exponents'].values()):raise ValueError('Risk exponents are invalid')
        if float(risk['review_threshold'])>=float(risk['block_threshold']):raise ValueError('Risk thresholds must be ordered')
        required={'SCIENTIFIC_VISUALIZATION','MAPPING','HAZARD_ASSESSMENT','ROUTE_PLANNING'}
        if set(config['missions'])!=required:raise ValueError('Mission profiles are incomplete')
        for mission,values in config['missions'].items():
            for key,value in values.items():_unit(value,f'{mission}.{key}')
    except KeyError as exc:raise ValueError(f'Missing Phase-2 configuration field: {exc.args[0]}') from exc
