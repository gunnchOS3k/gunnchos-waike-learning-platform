"""Version-bound practicals, plus an adapter to the existing Hub gradebook.

The public routes are stateless practice. The authenticated route submits to the
existing AssessmentService, never awards mastery, and requires a real enrollment.
"""
import base64
import hashlib
import hmac
import importlib.util
import json
import os
from pathlib import Path
import secrets
import time
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from app.auth import Actor, require_learner, require_actor
from app.modules.assessment_lifecycle import ServiceError, _id, _now

router=APIRouter(prefix='/api/v1/digital-confidence',tags=['Digital Confidence'])
ASSIGNMENT='DIGITAL_CONFIDENCE-independent-v1'
REL='curriculum/digital_rc/GENERAL_IT/delivery/digital_confidence.json'

class Work(BaseModel):
    model_config=ConfigDict(extra='forbid')
    token:str=Field(min_length=32,max_length=4000)
    answers:dict=Field(max_length=10)

class Submission(Work):
    section_id:str=Field(min_length=1,max_length=150)
    idempotency_key:str=Field(min_length=1,max_length=150)

def materials(request):
    value=request.app.state.waike_root
    if not value:raise HTTPException(503,'Canonical curriculum unavailable')
    root=Path(value);path=root/REL
    if not path.is_file():raise HTTPException(503,'Digital Confidence delivery is not installed')
    raw=path.read_bytes();definition=json.loads(raw)
    code=root/'src/waike_course_ready/digital_confidence.py'
    spec=importlib.util.spec_from_file_location('waike_dc_verified',code)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return definition,hashlib.sha256(raw+code.read_bytes()).hexdigest(),module

def signing_key(request):
    key=getattr(request.app.state,'dc_signing_key',None)
    if key is None:
        configured=os.environ.get('WAIKE_PRACTICE_SIGNING_KEY','')
        if len(configured)>=32:key=configured.encode()
        elif os.environ.get('WAIKE_ENV') in ('development','test'):key=secrets.token_bytes(32)
        else:raise HTTPException(503,'Practice signing key must be configured by the operator')
        request.app.state.dc_signing_key=key
    return key

def unpack(request,token,expected_hash):
    try:
        encoded,signature=token.split('.')
        expected=hmac.new(signing_key(request),encoded.encode(),hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected,signature):raise ValueError()
        payload=json.loads(base64.urlsafe_b64decode(encoded+'='*(-len(encoded)%4)))
        if payload['revision']!=expected_hash:raise HTTPException(409,'Content changed; request a fresh case')
        if payload['expires']<time.time():raise HTTPException(409,'Case expired; request a fresh case')
        return payload
    except HTTPException:raise
    except (ValueError,KeyError,TypeError):raise HTTPException(422,'Invalid case token')

def assessed(request,body):
    _,revision,module=materials(request)
    case=unpack(request,body.token,revision)
    if len(json.dumps(body.answers).encode())>16000:raise HTTPException(413,'Evidence exceeds 16 KB')
    for name,value in body.answers.items():
        if len(name)>80 or not isinstance(value,(str,int,float,dict)) or isinstance(value,bool):raise HTTPException(422,'Invalid answer type')
        if isinstance(value,str) and len(value)>2000:raise HTTPException(422,'Answer is too long')
        if isinstance(value,dict) and (set(value)!={'name','text'} or any(not isinstance(v,str) or len(v)>4000 for v in value.values())):raise HTTPException(422,'Invalid file evidence')
    result=module.evaluate(case['unit'],case['parameters'],body.answers)
    return case,result

@router.get('/cases/{unit}')
def issue(unit:int,request:Request,revision:str):
    _,current,module=materials(request)
    if current!=revision:raise HTTPException(409,'Content changed; reload the course')
    if not 1<=unit<=11:raise HTTPException(404,'Unknown unit')
    seed=secrets.randbits(32)
    payload={'unit':unit,'revision':current,'nonce':secrets.token_hex(12),'expires':int(time.time())+3600,'parameters':module.parameters(seed,unit)}
    encoded=base64.urlsafe_b64encode(json.dumps(payload,sort_keys=True).encode()).decode().rstrip('=')
    signature=hmac.new(signing_key(request),encoded.encode(),hashlib.sha256).hexdigest()
    return {'token':encoded+'.'+signature,'parameters':payload['parameters'],'expires':payload['expires'],'unit':unit,'revision':current,'persisted':False}

@router.post('/evaluate')
def evaluate(body:Work,request:Request):
    case,result=assessed(request,body)
    return {**result,'revision':case['revision'],'persisted':False,'submitted':False}


def install_definition(app):
    """Register canonical assessment content only. Creates no users/enrollments."""
    root=app.state.waike_root
    if not root or not (Path(root)/REL).is_file():return
    definition=json.loads((Path(root)/REL).read_text());conn=app.state.db
    if conn.execute('SELECT 1 FROM assignments WHERE assignment_id=?',(ASSIGNMENT,)).fetchone():return
    now=_now();rubric='rubric_dc_independent_v1';outcome='outcome_dc_independent_v1'
    body='# Independent Digital Confidence portfolio\n\n'+definition['completion']['independent']+'\n\n'+definition['completion']['review']+'\n\nUse the fresh-case practical workspace. No credentials or real patron data. A helper may support accessibility; the learner must explain their own choices.'
    with conn:
        conn.execute('INSERT INTO outcomes VALUES (?,?,?,?,?)',(outcome,'DIGITAL_CONFIDENCE','DC-INDEPENDENT','Digital Confidence practical competence','Files, restoration, analysis, safety and explained recovery.'))
        conn.execute('INSERT INTO rubrics VALUES (?,?,?,?,?)',(rubric,'waike.v1','Independent Digital Confidence evidence',REL,app.state.assessment.source_commit))
        for index,c in enumerate(definition['independent']['criteria']):
            cid='dc2-'+c['id']
            conn.execute('INSERT INTO rubric_criteria VALUES (?,?,?,?,?)',(cid,rubric,c['description'],1,index))
            for score,label in [(0,'Revise / insufficient observed evidence'),(1,'Verified by instructor against the stated criterion')]:
                conn.execute('INSERT INTO rubric_levels VALUES (?,?,?,?,?)',(f'{cid}-L{score}',cid,score,label,label))
        conn.execute('INSERT INTO assignments(assignment_id,module_id,schema_version,title,week,body_markdown,source_path,source_commit,rubric_id,outcome_id,mastery_threshold,portfolio_connection,revision_policy,current_version,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
          (ASSIGNMENT,'DIGITAL_CONFIDENCE','waike.v1',definition['independent']['title'],10,body,REL,app.state.assessment.source_commit,rubric,outcome,1,1,'allowed_with_changelog',1,now))
        conn.execute('INSERT INTO assignment_versions VALUES (?,?,?,?,?,?,?,?)',(_id('asgv'),ASSIGNMENT,1,definition['independent']['title'],body,rubric,hashlib.sha256(body.encode()).hexdigest(),now))

@router.post('/submissions')
def submit(body:Submission,request:Request,actor:Actor=Depends(require_actor)):
    require_learner(actor)
    case,result=assessed(request,body)
    if case['unit']!=11:raise HTTPException(422,'Independent work requires a fresh independent case')
    if not result['checks_passed']:raise HTTPException(422,{'message':'Revise the evidence before submission','checks':result['checks']})
    conn=request.app.state.db
    section=conn.execute('SELECT p.module_id FROM sections s JOIN packages p ON p.package_id=s.package_id WHERE s.section_id=?',(body.section_id,)).fetchone()
    if not section or section['module_id']!='DIGITAL_CONFIDENCE':raise HTTPException(403,'Digital Confidence section required')
    evidence=json.dumps({'case':case,'answers':body.answers,'automatic_checks':result,'status':'pending instructor review'},sort_keys=True)
    try:
        service=request.app.state.assessment
        receipt=service.submit(actor,ASSIGNMENT,body.idempotency_key,evidence,artifact_name='dc-independent-evidence.json',artifact_bytes=evidence.encode(),content_type='application/json',section_id=body.section_id)
        return {'submission':receipt,'status':'SUBMITTED','human_review':'pending','competency_demonstrated':False}
    except ServiceError as e:raise HTTPException(e.status,e.code)

@router.get('/progress')
def progress(request:Request,actor:Actor=Depends(require_actor)):
    require_learner(actor)
    service=request.app.state.assessment
    history=service.submission_history(actor,ASSIGNMENT)
    mastery=service.latest_mastery(actor,ASSIGNMENT)
    _,revision,_=materials(request)
    current=False
    if history:
        sub=service.get_submission(actor,history[0]['submission_id'])
        try:current=json.loads(sub['text_response'])['case']['revision']==revision
        except (KeyError,TypeError,ValueError):pass
    demonstrated=bool(current and mastery and mastery['mastered'])
    return {'submitted':bool(history),'evaluated':bool(mastery),'completed':demonstrated,'competency_demonstrated':demonstrated,'human_review':'recorded instructor evaluation' if mastery else 'pending','source_current':current,'history':history,'mastery':mastery,'portfolio':service.list_portfolio(actor)}
