import io,json
from pathlib import Path
import cv2,numpy as np
from fastapi.testclient import TestClient
from backend.app.main import app

ROOT=Path(__file__).parents[1];client=TestClient(app)
def png(a):ok,d=cv2.imencode('.png',a);assert ok;return d.tobytes()
def upload_bytes(data):
 r=client.post('/api/images/upload',files={'file':('x.png',io.BytesIO(data),'image/png')});assert r.status_code==201;return r.json()['id']
def analyze(a,b):
 x,y=upload_bytes(png(a)),upload_bytes(png(b));r=client.post('/api/analyses',json={'original_image_id':x,'enhanced_image_id':y});assert r.status_code==201;return r.json()['id']

def test_phase2_health_preserves_phase1_health_contract():
    assert client.get('/api/health/phase2').json()=={'status':'ok','service':'ratio-api','phase':2,'phase1_frozen':True}


def test_dataset_manifest_and_real_dem_preview():
 r=client.get('/api/datasets');assert r.status_code==200
 ids={x['id'] for x in r.json()['datasets']};assert 'NASA_SVS_LRO_NEARSIDE_45' in ids
 p=client.get('/api/datasets/NASA_SVS_LRO_NEARSIDE_45/preview?kind=hillshade');assert p.status_code==200
 assert cv2.imdecode(np.frombuffer(p.content,np.uint8),cv2.IMREAD_COLOR).shape[:2]==(360,360)

def test_no_significant_change_fast_path_export_and_passport():
 a=np.full((96,96),60,np.uint8);cv2.circle(a,(48,48),20,100,-1);aid=analyze(a,a.copy())
 result=client.post(f'/api/analyses/{aid}/verify',json={'mission_profile':'ROUTE_PLANNING'})
 assert result.status_code==200;body=result.json();assert body['dem_verification_status']=='NOT_REQUIRED' and body['policy']['decision']=='NO_SIGNIFICANT_CHANGE'
 assert client.post(f'/api/analyses/{aid}/export').status_code==200
 passport=client.get(f'/api/analyses/{aid}/passport');assert passport.status_code==200 and len(passport.json()['passport_sha256'])==64

def test_missing_reference_returns_unavailable_not_contradicted():
 a=cv2.imread(str(ROOT/'datasets/real/derived/lroc_nearside_original.png'));b=a.copy();cv2.circle(b,(390,130),14,(220,220,220),-1);aid=analyze(a,b)
 result=client.post(f'/api/analyses/{aid}/verify',json={'mission_profile':'MAPPING'}).json()
 assert result['dem_verification_status']=='REFERENCE_UNAVAILABLE'
 assert result['features'][0]['status']=='REFERENCE_UNAVAILABLE' and result['features'][0]['physical_support'] is None

def test_real_based_synthetic_hazard_auto_registration_policy_and_firewall():
 a=cv2.imread(str(ROOT/'datasets/real/derived/lroc_nearside_original.png'))
 b=cv2.imread(str(ROOT/'datasets/real/derived/lroc_nearside_synthetic_hazard.png'))
 aid=analyze(a,b)
 attached=client.post(f'/api/analyses/{aid}/reference',json={'dataset_id':'NASA_SVS_LRO_SYNTHETIC_HAZARD'})
 assert attached.status_code==200 and attached.json()['registration']['method']=='AUTO_METADATA'
 result=client.post(f'/api/analyses/{aid}/verify',json={'mission_profile':'ROUTE_PLANNING'});assert result.status_code==200
 body=result.json();feature=body['features'][0]
 assert body['dataset']['classification']=='SYNTHETIC_DEMO' and feature['reference_quality']>.8
 assert feature['support_components']['hillshade_support'] is None and feature['unsupported_risk'] is not None
 assert body['policy']['decision'] in {'REVIEW_REQUIRED','NOT_SAFE'}
 blocked=client.post(f'/api/analyses/{aid}/export');assert blocked.status_code==409 and blocked.json()['error']=='POLICY_BLOCKED_EXPORT'
 passport=client.get(f'/api/analyses/{aid}/passport').json();assert passport['dataset_id']=='NASA_SVS_LRO_SYNTHETIC_HAZARD' and passport['dem_hash']

def test_manual_three_point_alignment_and_bad_points():
 a=cv2.imread(str(ROOT/'datasets/real/derived/lroc_nearside_original.png'));b=a.copy();cv2.circle(b,(380,140),18,(230,230,230),-1);aid=analyze(a,b)
 assert client.post(f'/api/analyses/{aid}/reference',json={'dataset_id':'NASA_SVS_LRO_NEARSIDE_45'}).status_code==200
 src=[[30,30],[480,30],[30,480]];dst=[[21,21],[337,21],[21,337]]
 good=client.post(f'/api/analyses/{aid}/align',json={'image_points':src,'reference_points':dst})
 assert good.status_code==200 and good.json()['method']=='MANUAL_3_POINT' and good.json()['quality_score']<=.85
 bad=client.post(f'/api/analyses/{aid}/align',json={'image_points':[[0,0],[1,1],[2,2]],'reference_points':dst})
 assert bad.status_code==422 and bad.json()['error']=='DEGENERATE_CONTROL_POINTS'

def test_auto_registration_requires_reference_image_correspondence():
    a=np.random.default_rng(7).integers(0,256,(512,512,3),dtype=np.uint8);b=a.copy();cv2.circle(b,(100,100),8,(255,255,255),-1);aid=analyze(a,b)
    attached=client.post(f'/api/analyses/{aid}/reference',json={'dataset_id':'NASA_SVS_LRO_NEARSIDE_45'})
    assert attached.status_code==200
    assert attached.json()['reference']['reference_image_compatibility']['status']!='COMPARABLE'
    assert attached.json()['registration'] is None


def test_phase2_structured_exceptions():
 missing=client.post('/api/analyses/'+'0'*32+'/reference',json={'dataset_id':'missing'})
 assert missing.status_code==404 and missing.json()['error']=='REFERENCE_UNAVAILABLE'
 assert client.get('/api/datasets/missing/preview').json()['error']=='DEM_NOT_FOUND'
 assert client.post('/api/analyses/'+'0'*32+'/export').json()['error']=='PHYSICAL_EVIDENCE_UNAVAILABLE'
