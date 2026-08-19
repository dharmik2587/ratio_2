"""Machine-readable Phase-2 processing passport."""
from __future__ import annotations
import hashlib,json
from datetime import datetime,timezone
from uuid import uuid4

def build_passport(analysis,dataset,registration,phase2,artifact_hashes,software_version='2.0.0'):
    passport={
      'schema_version':'2.0','passport_id':uuid4().hex,'analysis_id':analysis['id'],'created_at':datetime.now(timezone.utc).isoformat(),
      'original_hash':analysis['inputs']['original']['sha256'],'enhanced_hash':analysis['inputs']['enhanced']['sha256'],
      'dem_hash':None if dataset is None else dataset.get('sha256') or dataset.get('hashes',{}).get('derived_dem_sha256'),
      'dataset_id':None if dataset is None else dataset['id'],'product_id':None if dataset is None else dataset.get('product_id'),
      'dataset_classification':None if dataset is None else dataset.get('classification'),'analysis_version':'PHASE_2','software_version':software_version,
      'configuration':phase2['configuration'],'mission_profile':phase2['mission_profile'],'registration':registration,
      'reference_resolution_m':None if dataset is None else dataset.get('resolution_m_per_pixel'),
      'valid_data_percentage':[x.get('valid_data_percentage') for x in phase2.get('features',[])],
      'visual_change':[x.get('visual_change') for x in phase2.get('features',[])],
      'physical_support':[x.get('physical_support') for x in phase2.get('features',[])],
      'unsupported_risk':[x.get('unsupported_risk') for x in phase2.get('features',[])],
      'decision':phase2['policy'],'artifact_hashes':artifact_hashes
    }
    canonical=json.dumps(passport,sort_keys=True,separators=(',',':')).encode();passport['passport_sha256']=hashlib.sha256(canonical).hexdigest()
    return passport
