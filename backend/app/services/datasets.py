from __future__ import annotations
import hashlib,json,shutil
from pathlib import Path
from uuid import uuid4
import cv2,numpy as np
from backend.app.core.config import ROOT,DATA_DIR
from ratio_core.dem import load_dem,terrain_derivatives

BUILTIN=[ROOT/'datasets/manifests/phase2_datasets.json',ROOT/'datasets/manifests/phase3_datasets.json']; REGISTRY=DATA_DIR/'datasets/index.json'; REFERENCE_DIR=DATA_DIR/'references'
REQUIRED={'id','mission','instrument','product_id','data_type','source','local_path','resolution_m_per_pixel','coordinate_reference_system','classification'}

def _custom():
    if not REGISTRY.exists():return []
    return json.loads(REGISTRY.read_text()).get('entries',[])

def list_datasets():
    built=[]
    for manifest_path in BUILTIN:
        if manifest_path.exists():
            built.extend(json.loads(manifest_path.read_text()).get('entries',[]))
    result=[]
    for item in built+_custom():
        entry=dict(item);path=resolve_dataset_path(entry);entry['available']=path.exists()
        if path.exists():entry['sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
        result.append(entry)
    return result

def get_dataset(dataset_id):
    for item in list_datasets():
        if item['id']==dataset_id:return item
    raise FileNotFoundError(dataset_id)

def resolve_dataset_path(entry):
    p=Path(entry['local_path']);return p if p.is_absolute() else ROOT/p

def register_dataset(manifest,dem_bytes,filename):
    missing=REQUIRED-set(manifest)
    if missing:raise ValueError('Missing dataset fields: '+','.join(sorted(missing)))
    if manifest['classification'] not in {'REAL','SYNTHETIC_DEMO','TEST_DATA','DEMO'}:raise ValueError('Invalid dataset classification')
    if any(x['id']==manifest['id'] for x in list_datasets()):raise ValueError('Dataset ID already exists')
    if not dem_bytes:raise ValueError('DEM file is empty')
    REFERENCE_DIR.mkdir(parents=True,exist_ok=True);dest=REFERENCE_DIR/f"{uuid4().hex}_{Path(filename).name}";dest.write_bytes(dem_bytes)
    try:dem=load_dem(str(dest))
    except Exception:
        dest.unlink(missing_ok=True);raise
    entry=dict(manifest);entry['local_path']=str(dest);entry['sha256']=dem.sha256;entry['reference_dimensions']=[dem.elevation_m.shape[1],dem.elevation_m.shape[0]]
    entries=_custom()+[entry];REGISTRY.parent.mkdir(parents=True,exist_ok=True);REGISTRY.write_text(json.dumps({'schema_version':'2.0','entries':entries},indent=2))
    return entry

def dataset_preview(dataset_id,kind='hillshade'):
    entry=get_dataset(dataset_id);dem=load_dem(str(resolve_dataset_path(entry)));der=terrain_derivatives(dem)
    array=der.hillshade if kind=='hillshade' else dem.elevation_m
    valid=dem.valid_mask&np.isfinite(array);scaled=np.zeros(array.shape,np.uint8)
    if valid.any():
        lo,hi=np.percentile(array[valid],[2,98]);scaled[valid]=np.uint8(np.clip((array[valid]-lo)/max(hi-lo,1e-9)*255,0,255))
    colored=cv2.applyColorMap(scaled,cv2.COLORMAP_BONE if kind=='hillshade' else cv2.COLORMAP_TURBO);colored[~valid]=(25,15,15)
    ok,png=cv2.imencode('.png',colored);assert ok;return png.tobytes()
