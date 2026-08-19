import hashlib, io, json
from pathlib import Path
import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.core import config as core_config

client = TestClient(app)


def png(image):
    ok, data = cv2.imencode('.png', image)
    assert ok
    return data.tobytes()


def image(value=50, size=(96,96)):
    a=np.full((*size,3),value,np.uint8)
    cv2.circle(a,(size[1]//2,size[0]//2),min(size)//4,value+40,-1)
    return a


def upload(data, mime='image/png'):
    return client.post('/api/images/upload', files={'file':('input.png',io.BytesIO(data),mime)})


def make_analysis(a, b):
    ua, ub = upload(png(a)), upload(png(b))
    assert ua.status_code == ub.status_code == 201
    return client.post('/api/analyses', json={'original_image_id':ua.json()['id'], 'enhanced_image_id':ub.json()['id']})


def test_health():
    assert client.get('/api/health').json() == {'status':'ok','service':'ratio-api','stage':1}


def test_full_analysis_artifact_and_download_flow():
    a=image(); b=a.copy(); cv2.rectangle(b,(72,12),(84,24),(240,240,240),-1)
    made=make_analysis(a,b); assert made.status_code==201 and made.json()['status']=='COMPARABLE'
    aid=made.json()['id']; result=client.get('/api/analyses/'+aid)
    body=result.json(); assert result.status_code==200 and body['scope']=='STAGE_1_VISUAL_EVIDENCE_ONLY'
    assert len(body['inputs']['original']['sha256'])==64 and body['metrics']['region_count']>=1
    assert client.get(f'/api/analyses/{aid}/features').status_code==200
    assert client.get(f'/api/analyses/{aid}/download').headers['content-type'].startswith('application/json')
    for name in ('difference_map.png','suspicious_mask.png','annotated.png'):
        response=client.get(f'/api/analyses/{aid}/artifacts/{name}')
        assert response.status_code==200
        decoded=cv2.imdecode(np.frombuffer(response.content,np.uint8),cv2.IMREAD_UNCHANGED)
        assert decoded is not None and decoded.shape[:2]==a.shape[:2]


def test_same_scene_different_dimensions_api_metadata():
    a=image(size=(120,104)); b=cv2.resize(a,(117,135))
    made=make_analysis(a,b); body=client.get('/api/analyses/'+made.json()['id']).json()
    assert body['status']=='COMPARABLE' and body['dimensions']['resize_applied'] is True
    assert body['dimensions']['analysis_dimensions']==[104,120]


def test_incomparable_has_report_but_no_evidence_artifacts():
    a=image(); b=np.random.default_rng(5).integers(0,256,a.shape,dtype=np.uint8)
    made=make_analysis(a,b); assert made.status_code==201
    aid=made.json()['id']; body=client.get('/api/analyses/'+aid).json()
    assert body['status']=='INCOMPARABLE_IMAGES'
    assert body['metrics'] is None and body['features']==[] and body['artifacts']=={}
    missing=client.get(f'/api/analyses/{aid}/artifacts/difference_map.png')
    assert missing.status_code==404 and missing.json()['error']=='ARTIFACT_NOT_AVAILABLE'


@pytest.mark.parametrize('data,mime,code,status', [
    (b'', 'image/png', 'EMPTY_FILE', 422),
    (b'not an image', 'image/png', 'IMAGE_DECODE_FAILED', 422),
    (b'plain text', 'text/plain', 'UNSUPPORTED_IMAGE_TYPE', 415),
])
def test_invalid_upload_paths(data,mime,code,status):
    response=upload(data,mime)
    assert response.status_code==status and response.json()['error']==code and response.json()['message']


def test_oversized_file_rejected_cleanly():
    response=upload(b'x'*(20*1024*1024+1))
    assert response.status_code==413 and response.json()['error']=='IMAGE_TOO_LARGE'


def test_megapixel_limit_rejected_cleanly():
    huge=np.zeros((6251,6400),np.uint8)  # 40,006,400 pixels; highly compressible
    response=upload(png(huge))
    assert response.status_code==413 and response.json()['error']=='MEGAPIXEL_LIMIT_EXCEEDED'


def test_missing_image_and_malformed_json_are_structured():
    missing=client.post('/api/analyses',json={'original_image_id':'0'*32,'enhanced_image_id':'1'*32})
    assert missing.status_code==404 and missing.json()['error']=='IMAGE_NOT_FOUND'
    malformed=client.post('/api/analyses',content='{bad',headers={'content-type':'application/json'})
    assert malformed.status_code==422 and malformed.json()['error']=='INVALID_REQUEST'


@pytest.mark.parametrize('payload', [
    {'enhanced_image_id':'1'*32},
    {'original_image_id':'0'*32},
])
def test_missing_required_image_field_is_structured(payload):
    response=client.post('/api/analyses',json=payload)
    assert response.status_code==422 and response.json()['error']=='INVALID_REQUEST'


def test_missing_analysis_and_artifact_are_structured():
    aid='0'*32
    assert client.get('/api/analyses/'+aid).json()['error']=='ANALYSIS_NOT_FOUND'
    assert client.get(f'/api/analyses/{aid}/artifacts/nope.png').json()['error']=='ARTIFACT_NOT_FOUND'


def test_invalid_configuration_returns_clean_error(tmp_path, monkeypatch):
    invalid=tmp_path/'invalid.json'; invalid.write_text(json.dumps({'visual_weights':{}}))
    monkeypatch.setattr(core_config,'CONFIG_PATH',invalid)
    a=upload(png(image())).json()['id']; b=upload(png(image())).json()['id']
    response=client.post('/api/analyses',json={'original_image_id':a,'enhanced_image_id':b})
    assert response.status_code==422 and response.json()['error']=='INVALID_CONFIGURATION'


def test_analysis_artifacts_are_deterministic_for_same_inputs():
    a=image(); b=a.copy(); cv2.rectangle(b,(72,12),(84,24),(240,240,240),-1)
    ua,ub=upload(png(a)).json(),upload(png(b)).json()
    ids=[]; bodies=[]
    for _ in range(2):
        made=client.post('/api/analyses',json={'original_image_id':ua['id'],'enhanced_image_id':ub['id']})
        ids.append(made.json()['id']); bodies.append(client.get('/api/analyses/'+ids[-1]).json())
    assert bodies[0]['compatibility']==bodies[1]['compatibility']
    assert bodies[0]['metrics']==bodies[1]['metrics'] and bodies[0]['features']==bodies[1]['features']
    for name in ('difference_map.png','suspicious_mask.png','annotated.png'):
        first=client.get(f'/api/analyses/{ids[0]}/artifacts/{name}').content
        second=client.get(f'/api/analyses/{ids[1]}/artifacts/{name}').content
        assert hashlib.sha256(first).digest()==hashlib.sha256(second).digest()


def test_input_bytes_remain_immutable():
    data=png(image()); before=hashlib.sha256(data).hexdigest(); uploaded=upload(data).json()
    made=client.post('/api/analyses',json={'original_image_id':uploaded['id'],'enhanced_image_id':uploaded['id']})
    assert made.status_code==201
    metadata=next(Path(core_config.UPLOAD_DIR).glob(uploaded['id']+'.json'))
    record=json.loads(metadata.read_text()); stored=Path(record['path']).read_bytes()
    assert hashlib.sha256(stored).hexdigest()==before==uploaded['sha256']
