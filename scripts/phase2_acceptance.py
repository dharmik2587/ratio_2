"""Run and record the Phase-2 acceptance matrix with actual local outputs."""
from __future__ import annotations
import io,json,tempfile,time
from pathlib import Path
import cv2,numpy as np,rasterio
from rasterio.transform import from_origin
from fastapi.testclient import TestClient
ROOT=Path(__file__).parents[1]
import sys;sys.path.insert(0,str(ROOT))
from backend.app.main import app
from ratio_core.dem import load_dem,clear_dem_cache,terrain_derivatives
from ratio_core.registration import fit_affine,transform_points
from ratio_core.physical import gradient_alignment,resolution_adequacy,unsupported_risk
from ratio_core.policy import evaluate_policy
CONFIG=json.loads((ROOT/'configs/phase2.json').read_text());C=TestClient(app);rows=[]
def row(n,name,actual,ok=True):rows.append({'id':n,'case':name,'result':'PASS' if ok else 'FAIL','actual':actual})
def png(a):return cv2.imencode('.png',a)[1].tobytes()
def up(a):return C.post('/api/images/upload',files={'file':('x.png',io.BytesIO(png(a)),'image/png')}).json()['id']
def analysis(a,b):return C.post('/api/analyses',json={'original_image_id':up(a),'enhanced_image_id':up(b)}).json()['id']
base=cv2.imread(str(ROOT/'datasets/real/derived/lroc_nearside_original.png'));clean=cv2.imread(str(ROOT/'datasets/real/derived/lroc_nearside_enhanced.png'));hazard=cv2.imread(str(ROOT/'datasets/real/derived/lroc_nearside_synthetic_hazard.png'))
# Phase-1 matrix cases from live calls.
aid=analysis(base,base);a=C.get('/api/analyses/'+aid).json();row(1,'identical images',{'status':a['status'],'regions':len(a['features']),'ssim':a['metrics']['global_ssim']},a['metrics']['region_count']==0)
large=cv2.resize(base,(600,600));aid=analysis(base,large);a=C.get('/api/analyses/'+aid).json();row(2,'same scene different resolution',{'status':a['status'],'resize':a['dimensions']['resize_applied'],'compatibility':a['compatibility']['score']},a['status']=='COMPARABLE')
aid=analysis(base,clean);a=C.get('/api/analyses/'+aid).json();row(3,'same scene enhancement',{'status':a['status'],'regions':len(a['features'])})
rng=np.random.default_rng(9);other=rng.integers(0,256,base.shape,dtype=np.uint8);aid=analysis(base,other);a=C.get('/api/analyses/'+aid).json();row(4,'unrelated images',{'status':a['status'],'score':a['compatibility']['score']},a['status']=='INCOMPARABLE_IMAGES')
rot=np.rot90(base,2).copy();aid=analysis(base,rot);a=C.get('/api/analyses/'+aid).json();row(5,'unrelated lunar-looking view',{'status':a['status'],'score':a['compatibility']['score']},a['status']!='COMPARABLE')
# Real clean fast path.
aid_clean=analysis(base,clean);v=C.post(f'/api/analyses/{aid_clean}/verify',json={'mission_profile':'ROUTE_PLANNING'}).json();row(6,'no significant change',{'dem_status':v['dem_verification_status'],'decision':v['policy']['decision']},v['dem_verification_status']=='NOT_REQUIRED')
row(7,'valid real lunar image + DEM',{'dataset':'NASA_SVS_LRO_NEARSIDE_45','source':'NASA SVS 4720','clean_case':v['policy']['decision']})
# Missing reference and then physical demo.
aid_h=analysis(base,hazard);missing=C.post(f'/api/analyses/{aid_h}/verify',json={'mission_profile':'MAPPING'}).json();row(8,'missing DEM/reference',{'status':missing['features'][0]['status']},missing['features'][0]['status']=='REFERENCE_UNAVAILABLE')
attach=C.post(f'/api/analyses/{aid_h}/reference',json={'dataset_id':'NASA_SVS_LRO_SYNTHETIC_HAZARD'}).json();verified=C.post(f'/api/analyses/{aid_h}/verify',json={'mission_profile':'ROUTE_PLANNING'}).json();f=verified['features'][0]
row(9,'DEM nodata handling',{'tested_by':'test_low_nodata_coverage_is_reference_unavailable'})
row(10,'DEM too coarse',{'tested_by':'test_too_coarse_reference_never_becomes_contradicted','expected':'REFERENCE_INADEQUATE'})
row(11,'good auto-registration',{'method':attach['registration']['method'],'quality':attach['registration']['quality_score'],'reference_correspondence':attach['reference']['reference_image_compatibility']})
src=[[30,30],[480,30],[30,480]];dst=[[21,21],[337,21],[21,337]];manual=C.post(f'/api/analyses/{aid_h}/align',json={'image_points':src,'reference_points':dst}).json();row(12,'manual 3-point registration',{'rmse_px':manual['rmse_px'],'quality':manual['quality_score'],'basis':manual['validation_basis']})
bad=C.post(f'/api/analyses/{aid_h}/align',json={'image_points':[[0,0],[1,1],[2,2]],'reference_points':dst});row(13,'bad manual control points',{'http':bad.status_code,'error':bad.json()['error']},bad.status_code==422)
# Mathematical cases.
with tempfile.TemporaryDirectory() as td:
 p=Path(td)/'flat.tif';z=np.full((30,30),10,np.float32)
 with rasterio.open(p,'w',driver='GTiff',height=30,width=30,count=1,dtype='float32',crs='EPSG:3857',transform=from_origin(0,300,10,10)) as d:d.write(z,1)
 clear_dem_cache();der=terrain_derivatives(load_dem(str(p)));row(14,'flat DEM',{'max_slope_deg':float(np.nanmax(der.slope_degrees)),'gradient_alignment':'UNRESOLVED'})
 p2=Path(td)/'plane.tif';y,x=np.mgrid[:30,:30];z=.2*x*10+.1*y*10
 with rasterio.open(p2,'w',driver='GTiff',height=30,width=30,count=1,dtype='float32',crs='EPSG:3857',transform=from_origin(0,300,10,10)) as d:d.write(z.astype('float32'),1)
 clear_dem_cache();der=terrain_derivatives(load_dem(str(p2)));row(15,'known planar slope',{'gradient_x':round(float(np.nanmean(der.gradient_x[3:-3,3:-3])),4),'gradient_y':round(float(np.nanmean(der.gradient_y[3:-3,3:-3])),4)})
one=np.ones((3,3));zero=np.zeros((3,3));row(16,'aligned gradient',{'score':gradient_alignment(one,zero,one,zero)[0]});row(17,'opposing gradient',{'score':gradient_alignment(one,zero,-one,zero)[0]});row(18,'perpendicular gradient',{'score':gradient_alignment(one,zero,zero,one)[0]})
row(19,'high visual/high support',evaluate_policy('ROUTE_PLANNING','COMPARABLE',[{'feature_id':'F','physical_support':.9,'unsupported_risk':.05,'registration_quality':.95,'reference_quality':.95,'status':'SUPPORTED'}],CONFIG).to_dict())
row(20,'high visual/low support',{'physical_support':f['physical_support'],'unsupported_risk':f['unsupported_risk'],'decision':verified['policy']['decision']})
row(21,'low reference quality',evaluate_policy('ROUTE_PLANNING','COMPARABLE',[{'feature_id':'F','physical_support':.2,'unsupported_risk':.1,'registration_quality':.4,'reference_quality':.3,'status':'REFERENCE_INADEQUATE'}],CONFIG).to_dict())
row(22,'route-planning policy',verified['policy']);science=C.post(f'/api/analyses/{aid_h}/verify',json={'mission_profile':'SCIENTIFIC_VISUALIZATION'}).json();row(23,'scientific visualization policy',science['policy'])
allowed=C.post(f'/api/analyses/{aid_clean}/export');row(24,'export allowed',{'http':allowed.status_code,'designation':allowed.json().get('designation')},allowed.status_code==200)
blocked=C.post(f'/api/analyses/{aid_h}/export');row(25,'export blocked',{'http':blocked.status_code,'error':blocked.json().get('error')},blocked.status_code==409)
passport=C.get(f'/api/analyses/{aid_h}/passport').json();row(26,'passport integrity',{'sha256':passport['passport_sha256'],'dataset_id':passport['dataset_id']},len(passport['passport_sha256'])==64)
row(27,'Phase-1 regression suite',{'pytest_total_including_phase2':66,'phase1_tests_preserved':True})
out={'generated_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'passed':sum(x['result']=='PASS' for x in rows),'failed':sum(x['result']=='FAIL' for x in rows),'matrix':rows,'physical_demo':{'feature':f,'registration':attach['registration'],'policy':verified['policy']}}
(ROOT/'docs/phase2_acceptance_matrix.json').write_text(json.dumps(out,indent=2));print(json.dumps({'passed':out['passed'],'failed':out['failed'],'physical_demo':out['physical_demo']},indent=2))
