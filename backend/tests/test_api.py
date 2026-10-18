import json,time
from sqlalchemy import select
from backend.app import main

def draft(client):
    bank=client.get('/api/questionnaires/current').json()
    return {'id':'test-draft-1234','mode':'basic','version':bank['id'],'answers':{bank['questions'][0]['id']:2},'index':1,'startedAt':'2026-10-16T00:00:00Z'}

def test_public_bank_and_example_no_stats(client):
    a=client.get('/api/questionnaires/current?mode=basic').json()
    b=client.get('/api/questionnaires/current?mode=full').json()
    assert len(a['questions'])==99 and len(b['questions'])==300
    assert a['questions']==b['questions'][:99]
    assert 'direction' not in a['questions'][0]
    assert client.get('/api/reports/example?mode=full').status_code==200
    with main.SessionLocal() as s:assert not s.scalars(select(main.Event)).all()
    assert client.get('/healthz').json()['status']=='ok'

def test_score_submission_is_idempotent_and_encrypted(client):
    d=draft(client);bank=client.get('/api/questionnaires/current').json()
    body={'submissionId':'idempotent-1234','mode':'basic','version':d['version'],'answers':{q['id']:0 for q in bank['questions']},'studentId':'test-001','studentName':'测试用户'}
    for _ in range(2):
        r=client.post('/api/assessments/score',json=body)
        assert r.status_code==200 and r.json()['type']=='XXXX'
    with main.SessionLocal() as s:
        assert len(s.scalars(select(main.Event)).all())==1
        assert not s.scalars(select(main.Resume)).all()
        submission=s.get(main.Submission,'idempotent-1234')
        assert submission is not None and '测试用户' not in submission.encrypted and 'test-001' not in submission.encrypted

def test_submission_requires_identity_and_admin_can_view_export(admin):
    bank=admin.get('/api/questionnaires/current').json()
    answers={q['id']:2 for q in bank['questions']}
    body={'submissionId':'student-submission-123','mode':'basic','version':bank['id'],'answers':answers,'studentId':'20260001','studentName':'测试同学'}
    assert admin.post('/api/assessments/score',json={**body,'studentName':''}).status_code==422
    assert admin.get('/api/admin/submissions').json()=={'total':0,'items':[]}
    result=admin.post('/api/assessments/score',json=body)
    assert result.status_code==200
    assert admin.post('/api/assessments/score',json=body).json()==result.json()
    assert admin.post('/api/assessments/score',json={**body,'studentName':'另一位'}).status_code==409
    changed={**body,'answers':{**answers,bank['questions'][0]['id']:3}}
    assert admin.post('/api/assessments/score',json=changed).status_code==409
    listing=admin.get('/api/admin/submissions').json()
    assert listing['total']==1 and listing['items'][0]['studentName']=='测试同学'
    detail=admin.get('/api/admin/submissions/student-submission-123').json()
    assert detail['answers']==answers and detail['report']['type']==result.json()['type']
    exported=admin.get('/api/admin/submissions/student-submission-123/export')
    assert exported.status_code==200 and exported.headers['content-type'].startswith('application/json')
    assert exported.json()['studentId']=='20260001' and exported.json()['answers']==answers
    with main.SessionLocal() as s:
        row=s.get(main.Submission,'student-submission-123')
        assert '测试同学' not in row.encrypted and '20260001' not in row.encrypted

def test_submission_admin_routes_require_login(client):
    assert client.get('/api/admin/submissions').status_code==401
    assert client.get('/api/admin/submissions/no-such-id').status_code==401

def test_resume_encrypted_conflict_revoke(client):
    d=draft(client);r=client.post('/api/resume-sessions',json={'draft':d});assert r.status_code==200
    token=r.json()['token'];assert len(token)>=32
    with main.SessionLocal() as s:
        row=s.get(main.Resume,main.digest(token));assert d['version'] not in row.encrypted
    assert client.post('/api/resume-sessions/claim',json={'token':token}).json()['draft']==d
    body={'token':token,'revision':1,'draft':d}
    assert client.patch('/api/resume-sessions/current',json=body).json()['revision']==2
    assert client.patch('/api/resume-sessions/current',json=body).status_code==409
    assert client.request('DELETE','/api/resume-sessions/current',json={'token':token}).status_code==204
    assert client.post('/api/resume-sessions/claim',json={'token':token}).status_code==404

def test_expiry_and_cleanup(client):
    token=client.post('/api/resume-sessions',json={'draft':draft(client)}).json()['token']
    with main.SessionLocal() as s:
        row=s.get(main.Resume,main.digest(token));row.expires=time.time()-1;s.commit()
    assert client.post('/api/resume-sessions/claim',json={'token':token}).status_code==404
    main.periodic_cleanup()
    with main.SessionLocal() as s:assert s.get(main.Resume,main.digest(token)) is None

def test_origin_auth_and_csrf(client):
    assert client.get('/api/admin/overview').status_code==401
    assert client.post('/api/admin/login',headers={'origin':'https://unknown.example'},json={'username':'admin','password':'irrelevant'}).status_code==403
    r=client.post('/api/admin/login',json={'username':'admin','password':'test-only-admin-password-16chars'})
    assert 'HttpOnly' in r.headers['set-cookie'] and 'SameSite=strict' in r.headers['set-cookie']
    assert client.post('/api/admin/logout').status_code==403
    client.headers['X-CSRF-Token']=r.json()['csrf']
    assert client.post('/api/admin/logout').status_code==204
    assert client.get('/api/admin/me').status_code==401

def test_immutable_version_old_draft_and_preview(admin):
    old=admin.get('/api/questionnaires/current').json()['id']
    bank=admin.get('/api/admin/versions/'+old).json()['bank']
    assert admin.put('/api/admin/versions/'+old,json={'bank':bank}).status_code==409
    new=admin.post('/api/admin/versions',json={'source':old,'title':'测试修订问卷'}).json()['id']
    data=admin.get('/api/admin/versions/'+new).json()['bank'];data['questions'][0]['text']+='（请按近半年习惯回答）'
    assert admin.put('/api/admin/versions/'+new,json={'bank':data}).status_code==200
    body={'mode':'full','version':new,'answers':{q['id']:0 for q in data['questions']},'submissionId':'preview-test-123'}
    assert admin.post('/api/admin/versions/'+new+'/preview',json=body).status_code==200
    assert admin.post('/api/admin/versions/'+new+'/publish').status_code==200
    assert admin.get('/api/questionnaires/current').json()['id']==new
    assert admin.get('/api/questionnaires/'+old).json()['questions'][0]['text']!=data['questions'][0]['text']
    assert admin.put('/api/admin/versions/'+new,json={'bank':data}).status_code==409
    assert not admin.get('/api/admin/overview').json()['stats']

def test_password_change_revokes_session(admin):
    r=admin.post('/api/admin/password',json={'current':'test-only-admin-password-16chars','password':'new-test-password-longer-than16'})
    assert r.status_code==204 and admin.get('/api/admin/me').status_code==401

def test_anonymous_section_progress_idempotent(client):
    body={'id':'section-visit-test','mode':'full','section':'career'}
    assert client.post('/api/events/progress',json=body).status_code==204
    assert client.post('/api/events/progress',json=body).status_code==204
    body['mode']='basic'
    assert client.post('/api/events/progress',json=body).status_code==422
    with main.SessionLocal() as s:
        rows=s.scalars(select(main.Event)).all()
        assert len(rows)==1 and rows[0].kind=='reached:career'
