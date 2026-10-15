import json,hashlib,os,sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from app.main import create_app,HubConfig

ROOT=Path(os.environ['WAIKE_ROOT'])
sys.path.insert(0,str(ROOT/'src'))
from waike_course_ready.digital_confidence import evaluate

def answers(unit,p):
    # Independent arithmetic/file construction from the issued public case.
    if unit==1:return {'file':{'name':p['filename'],'text':p['text']}}
    free=(p['size']-p['used']-p['reserved'])/p['size']*100
    return {'renamed':{'name':p['filename'],'text':p['text']},'restored':{'name':p['restored_filename'],'text':p['text']},'free_percent':free,'policy':'meets' if free>=15 else 'below','next_action':'preserve files and request an authorized maintenance plan','reflection':'I preserved the original file and restored a changed copy to a new destination. The checksum verifies bytes, while a reviewer must observe my actual performance.'}

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv('WAIKE_ENV','test')
    monkeypatch.setenv('WAIKE_ROOT',str(ROOT))
    app=create_app(HubConfig(fixture_auth_enabled=True,production_auth_enabled=False),db_path=tmp_path/'dc.db',seed=True)
    return TestClient(app)

def case(client,unit):
    data=(ROOT/'curriculum/digital_rc/GENERAL_IT/delivery/digital_confidence.json').read_bytes()
    revision=hashlib.sha256(data+(ROOT/'src/waike_course_ready/digital_confidence.py').read_bytes()).hexdigest()
    response=client.get(f'/api/v1/digital-confidence/cases/{unit}',params={'revision':revision})
    assert response.status_code==200,response.text
    return response.json()

def test_case_is_version_bound_and_tamper_evident(client):
    c=case(client,1);a=answers(1,c['parameters']);endpoint='/api/v1/digital-confidence/evaluate'
    r=client.post(endpoint,json={'token':c['token'],'answers':a});assert r.status_code==200;assert r.json()['checks_passed'];assert not r.json()['competency_demonstrated'];assert not r.json()['submitted']
    assert client.post(endpoint,json={'token':c['token']+'0','answers':a}).status_code==422
    assert client.get('/api/v1/digital-confidence/cases/1',params={'revision':'0'*64}).status_code==409
    a['file']['text']+='wrong';assert not client.post(endpoint,json={'token':c['token'],'answers':a}).json()['checks_passed']

def test_public_cannot_submit_or_read_progress(client):
    assert client.get('/api/v1/digital-confidence/progress').status_code==401
    assert client.post('/api/v1/digital-confidence/submissions',json={}).status_code==401

def hdr(actor,role):return {'X-Waike-Actor-Id':actor,'X-Waike-Actor-Role':role}

def test_existing_gradebook_submission_review_and_competence(client):
    learner=hdr('learner-a','learner');instructor=hdr('instructor-a','instructor')
    c=case(client,11);payload={'token':c['token'],'answers':answers(11,c['parameters']),'section_id':'sec_alpha_dc_w01','idempotency_key':'independent-1'}
    r=client.post('/api/v1/digital-confidence/submissions',json=payload,headers=learner)
    assert r.status_code==200,r.text
    sub=r.json()['submission'];assert r.json()['human_review']=='pending';assert not r.json()['competency_demonstrated']
    progress=client.get('/api/v1/digital-confidence/progress',headers=learner).json()
    assert progress['submitted'];assert not progress['completed'];assert not progress['evaluated']
    detail=client.get('/api/v1/assignments/DIGITAL_CONFIDENCE-independent-v1',headers=learner).json()
    criteria=detail['rubric']['criteria'];assert len(criteria)==4
    # Instructor grading is exercised using the EXISTING authoritative service,
    # with a synthetic test actor. This is not a claim of human validation.
    from app.auth import Actor,Role
    actor=Actor(actor_id='instructor-alpha',role=Role.INSTRUCTOR,display_name='Synthetic instructor',site_id='site-alpha')
    service=client.app.state.assessment
    service.grade_submission(actor,sub['submission_id'],[{'criterion_id':x['criterion_id'],'level_id':x['levels'][0]['level_id'],'points':1,'comment':'Synthetic acceptance-test evaluation.'} for x in criteria],'Synthetic fixture review; no human learner validation.')
    progress=client.get('/api/v1/digital-confidence/progress',headers=learner).json()
    assert progress['evaluated'];assert progress['completed'];assert progress['competency_demonstrated'];assert progress['portfolio']
