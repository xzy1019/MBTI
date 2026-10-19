import base64
import asyncio
from contextlib import suppress
import copy
import hashlib
import json
import os
import re
import secrets
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError
from cryptography.fernet import Fernet
from fastapi import FastAPI, HTTPException, Request, Response, Depends
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, Column, String, Text, Integer, Float, select, delete, update, func
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from sqlalchemy.exc import IntegrityError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .content import make_bank, public_types, FACETS, VERSION
from .scoring import validate_bank, score
from .guidance import DEFAULT_TEMPLATE

DATA=Path(os.getenv('DATA_DIR','.local'));DATA.mkdir(parents=True,exist_ok=True)
URL=os.getenv('DATABASE_URL',f'sqlite:///{DATA}/atlas.db')
engine=create_engine(URL,connect_args={'check_same_thread':False} if URL.startswith('sqlite') else {},pool_pre_ping=True)
SessionLocal=sessionmaker(engine,expire_on_commit=False)
Base=declarative_base()
hasher=PasswordHasher()
SECRET=os.getenv('SECRET_KEY','')
if len(SECRET)<32: raise RuntimeError('SECRET_KEY 至少需要 32 个字符，请配置应用环境。')
cipher=Fernet(base64.urlsafe_b64encode(hashlib.sha256(SECRET.encode()).digest()))
COOKIE_SECURE=os.getenv('COOKIE_SECURE','false').lower()=='true'
PUBLIC_ORIGINS={s.rstrip('/') for s in os.getenv('PUBLIC_ORIGIN','http://127.0.0.1:5173').split(',')}

class Questionnaire(Base):
    __tablename__='questionnaire_versions'
    id=Column(String(80),primary_key=True)
    title=Column(String(160),nullable=False)
    status=Column(String(20),nullable=False,default='draft')
    payload=Column(Text,nullable=False)
    created=Column(Float,nullable=False,default=time.time)
    published=Column(Float,nullable=True)

class Admin(Base):
    __tablename__='admin_accounts'
    username=Column(String(80),primary_key=True)
    password=Column(Text,nullable=False)

class LoginSession(Base):
    __tablename__='admin_sessions'
    id=Column(String(64),primary_key=True)
    username=Column(String(80),nullable=False)
    csrf=Column(String(80),nullable=False)
    expires=Column(Float,nullable=False,index=True)

class Resume(Base):
    __tablename__='resume_sessions'
    id=Column(String(64),primary_key=True)
    encrypted=Column(Text,nullable=False)
    revision=Column(Integer,nullable=False,default=1)
    expires=Column(Float,nullable=False,index=True)

class Audit(Base):
    __tablename__='admin_audit_logs'
    id=Column(String(40),primary_key=True)
    action=Column(String(200),nullable=False)
    created=Column(Float,default=time.time)

class Event(Base):
    __tablename__='daily_events'
    id=Column(String(64),primary_key=True)
    mode=Column(String(10),nullable=False)
    kind=Column(String(20),nullable=False)
    day=Column(String(10),nullable=False)

class Submission(Base):
    __tablename__='assessment_submissions'
    id=Column(String(80),primary_key=True)
    mode=Column(String(10),nullable=False)
    version=Column(String(80),nullable=False)
    encrypted=Column(Text,nullable=False)
    created=Column(Float,nullable=False,default=time.time,index=True)

def db():
    with SessionLocal() as session: yield session

def digest(value): return hashlib.sha256(value.encode()).hexdigest()

def cleanup(session):
    now=time.time()
    session.execute(delete(Resume).where(Resume.expires<now))
    session.execute(delete(LoginSession).where(LoginSession.expires<now))
    session.commit()

def periodic_cleanup():
    with SessionLocal() as session:
        cleanup(session)

async def cleanup_loop():
    while True:
        await asyncio.sleep(300)
        try:
            await asyncio.to_thread(periodic_cleanup)
        except Exception:
            # Do not log request data, tokens or encrypted drafts.
            import logging
            logging.getLogger(__name__).exception('Temporary session cleanup failed')

@asynccontextmanager
async def lifespan(app):
    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        if not session.get(Questionnaire,VERSION):
            bank=validate_bank(make_bank())
            session.add(Questionnaire(id=VERSION,title=bank['title'],status='published',payload=json.dumps(bank,ensure_ascii=False),published=time.time()))
        username=os.getenv('ADMIN_USERNAME','admin')
        if not session.get(Admin,username):
            password=os.getenv('ADMIN_PASSWORD','')
            if len(password)<9: raise RuntimeError('首次启动须配置至少 9 个字符的 ADMIN_PASSWORD。')
            session.add(Admin(username=username,password=hasher.hash(password)))
        session.commit();cleanup(session)
    task=asyncio.create_task(cleanup_loop())
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

app=FastAPI(title='知序 Self Atlas',version='1.0.0',lifespan=lifespan,docs_url=None,redoc_url=None)
limits=defaultdict(deque)

def limit(request,kind,count,period):
    now=time.time();key=(request.client.host if request.client else 'unknown',kind)
    queue=limits[key]
    while queue and queue[0]<now-period: queue.popleft()
    if len(queue)>=count: raise HTTPException(429,'请求较频繁，请稍后重试。',headers={'Retry-After':str(period)})
    queue.append(now)
    if len(limits)>5000:
        for k in list(limits):
            if not limits[k] or limits[k][-1]<now-3600: del limits[k]

@app.middleware('http')
async def boundaries(request:Request,call_next):
    if request.headers.get('content-length','').isdigit() and int(request.headers['content-length'])>300000:
        return Response('请求内容过大',status_code=413)
    if request.method in ['POST','PUT','PATCH','DELETE']:
        origin=request.headers.get('origin')
        if origin and origin.rstrip('/') not in PUBLIC_ORIGINS:
            return Response('不允许的来源',status_code=403)
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Cache-Control']='no-store'
    response.headers['Referrer-Policy']='no-referrer'
    return response

def current(session):
    row=session.scalar(select(Questionnaire).where(Questionnaire.status=='published').order_by(Questionnaire.published.desc()))
    if not row: raise HTTPException(503,'暂时没有可用问卷')
    return row

def get_bank(session,version):
    row=session.get(Questionnaire,version)
    if not row or row.status!='published': raise HTTPException(404,'该问卷版本不存在或尚未发布，请保留草稿并联系管理员。')
    return json.loads(row.payload)

def public_bank(bank,mode):
    if mode not in ['basic','full']: raise HTTPException(422,'未知测试版本')
    qs=bank['questions'][:99] if mode=='basic' else bank['questions']
    return {"id":bank['id'],"title":bank['title'],"mode":mode,"notice":bank.get('notice',''),"questions":[{k:q[k] for k in ['id','text','section','na']} for q in qs]}

@app.get('/healthz')
def health(session:Session=Depends(db)):
    session.execute(select(1))
    return {'status':'ok','version':'1.0.0','questionCount':300}

@app.get('/api/questionnaires/current')
def get_current(mode:str='basic',session:Session=Depends(db)):
    return public_bank(json.loads(current(session).payload),mode)

@app.get('/api/questionnaires/{version}')
def get_version(version:str,mode:str='basic',session:Session=Depends(db)):
    return public_bank(get_bank(session,version),mode)

class ScoreInput(BaseModel):
    mode:str
    version:str=Field(max_length=80)
    answers:dict[str,Any]
    submissionId:str=Field(min_length=8,max_length=80,pattern=r'^[a-zA-Z0-9_-]+$')
    studentId:str|None=Field(default=None,max_length=80)
    studentName:str|None=Field(default=None,max_length=80)
    supportRequested:bool=False

def event(session,token,mode,kind):
    key=digest(token+':'+mode+':'+kind)
    if not session.get(Event,key):
        session.add(Event(id=key,mode=mode,kind=kind,day=datetime.now(timezone.utc).strftime('%Y-%m-%d')))
        try: session.commit()
        except IntegrityError: session.rollback()  # Concurrent retries count once.

@app.post('/api/assessments/score')
def calculate(body:ScoreInput,request:Request,session:Session=Depends(db)):
    limit(request,'score',30,60)
    student_id=(body.studentId or '').strip()
    student_name=(body.studentName or '').strip()
    if not student_id or not student_name:
        raise HTTPException(422,'请先填写学号和姓名。')
    if len(student_id)>80 or len(student_name)>80:
        raise HTTPException(422,'学号或姓名过长。')
    bank=get_bank(session,body.version)
    existing=session.get(Submission,body.submissionId)
    if existing:
        try:
            saved=json.loads(cipher.decrypt(existing.encrypted.encode()).decode())
            if existing.mode!=body.mode or existing.version!=body.version or saved.get('studentId')!=student_id or saved.get('studentName')!=student_name or saved.get('answers')!=body.answers or saved.get('supportRequested',False)!=body.supportRequested:
                raise HTTPException(409,'该测试编号已对应其他提交，请刷新草稿后重试。')
            result=saved['report']
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(500,'提交记录暂时无法读取，请联系管理员。')
        event(session,body.submissionId,body.mode,'completed')
        return result
    try: result=score(bank,body.mode,body.answers)
    except ValueError as e: raise HTTPException(422,str(e))
    result['id']=body.submissionId
    record={'studentId':student_id,'studentName':student_name,'answers':body.answers,'report':result,'supportRequested':body.supportRequested}
    session.add(Submission(id=body.submissionId,mode=body.mode,version=body.version,encrypted=cipher.encrypt(json.dumps(record,ensure_ascii=False).encode()).decode(),created=time.time()))
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        existing=session.get(Submission,body.submissionId)
        if not existing: raise HTTPException(409,'提交未能保存，请重试。')
        try: saved=json.loads(cipher.decrypt(existing.encrypted.encode()).decode())
        except Exception: raise HTTPException(500,'提交记录暂时无法读取，请联系管理员。')
        if existing.mode!=body.mode or existing.version!=body.version or saved.get('studentId')!=student_id or saved.get('studentName')!=student_name or saved.get('answers')!=body.answers or saved.get('supportRequested',False)!=body.supportRequested:
            raise HTTPException(409,'该测试编号已对应其他提交，请刷新草稿后重试。')
        result=saved['report']
    event(session,body.submissionId,body.mode,'completed')
    return result

class StartInput(BaseModel):
    id:str=Field(min_length=8,max_length=80)
    mode:str

@app.post('/api/events/start',status_code=204)
def record_start(body:StartInput,request:Request,session:Session=Depends(db)):
    limit(request,'event',30,60)
    if body.mode not in ['basic','full']: raise HTTPException(422,'未知版本')
    event(session,body.id,body.mode,'started')

class ProgressInput(StartInput):
    section:str

@app.post('/api/events/progress',status_code=204)
def record_progress(body:ProgressInput,request:Request,session:Session=Depends(db)):
    limit(request,'progress',30,60)
    allowed=['base'] if body.mode=='basic' else ['base','personality','career','social','romance'] if body.mode=='full' else []
    if body.section not in allowed: raise HTTPException(422,'未知章节')
    event(session,body.id,body.mode,'reached:'+body.section)

@app.get('/api/types')
def types(): return public_types()

@app.get('/api/reports/example')
def example(mode:str='full',session:Session=Depends(db)):
    if mode not in ['basic','full']: raise HTTPException(422,'未知测试版本')
    bank=json.loads(current(session).payload)
    qs=bank['questions'][:99] if mode=='basic' else bank['questions']
    answers={q['id']:q['direction']*(2 if i%3 else -1) for i,q in enumerate(qs)}
    result=score(bank,mode,answers)
    result['id']='example-'+mode
    return result

def validate_draft(session,draft):
    if not isinstance(draft,dict) or draft.get('mode') not in ['basic','full']: raise HTTPException(422,'草稿格式错误')
    bank=get_bank(session,draft.get('version',''))
    qs=bank['questions'][:99] if draft['mode']=='basic' else bank['questions']
    mapping={q['id']:q for q in qs};answers=draft.get('answers',{})
    if not isinstance(answers,dict) or not set(answers)<=set(mapping): raise HTTPException(422,'草稿含未知题目')
    for key,a in answers.items():
        if a is None and mapping[key]['na']: continue
        if type(a) is not int or not -3<=a<=3: raise HTTPException(422,'草稿答案无效')
    if not isinstance(draft.get('id'),str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,80}',draft['id']): raise HTTPException(422,'草稿编号无效')
    if type(draft.get('index',0)) is not int or not 0<=draft.get('index',0)<len(qs): raise HTTPException(422,'草稿位置无效')
    for key in ['studentId','studentName']:
        if key in draft and (not isinstance(draft[key],str) or len(draft[key].strip())>80): raise HTTPException(422,'身份信息格式无效')
    clean={k:draft[k] for k in ['id','mode','version','answers','index','startedAt','studentId','studentName'] if k in draft}
    if len(json.dumps(clean))>100000: raise HTTPException(413,'草稿过大')
    return clean

class DraftInput(BaseModel):
    draft:dict

class TokenInput(BaseModel):
    token:str=Field(min_length=32,max_length=100)

class SyncInput(TokenInput):
    revision:int=Field(ge=1)
    draft:dict

@app.post('/api/resume-sessions')
def create_resume(body:DraftInput,request:Request,session:Session=Depends(db)):
    limit(request,'resume-create',10,600);cleanup(session)
    draft=validate_draft(session,body.draft);token=secrets.token_urlsafe(32);expiry=time.time()+7*86400
    session.add(Resume(id=digest(token),encrypted=cipher.encrypt(json.dumps(draft,ensure_ascii=False).encode()).decode(),expires=expiry,revision=1));session.commit()
    return {'token':token,'revision':1,'expires':expiry}

def resume_row(session,token):
    row=session.get(Resume,digest(token))
    if not row or row.expires<time.time(): raise HTTPException(404,'续答链接已过期、撤销或完成。原设备的本机草稿仍可使用。')
    return row

@app.post('/api/resume-sessions/claim')
def claim_resume(body:TokenInput,request:Request,session:Session=Depends(db)):
    limit(request,'resume-claim',30,60);row=resume_row(session,body.token)
    return {'draft':json.loads(cipher.decrypt(row.encrypted.encode())),'revision':row.revision,'expires':row.expires}

@app.patch('/api/resume-sessions/current')
def sync_resume(body:SyncInput,request:Request,session:Session=Depends(db)):
    limit(request,'resume-sync',120,60);row=resume_row(session,body.token)
    draft=validate_draft(session,body.draft)
    encrypted=cipher.encrypt(json.dumps(draft,ensure_ascii=False).encode()).decode()
    result=session.execute(update(Resume).where(Resume.id==row.id,Resume.revision==body.revision).values(encrypted=encrypted,revision=body.revision+1))
    if result.rowcount!=1: session.rollback();raise HTTPException(409,'另一设备保存了更新的答案。请先载入最新草稿，或撤销链接后保留本机副本。')
    session.commit();return {'revision':body.revision+1,'expires':row.expires}

@app.delete('/api/resume-sessions/current',status_code=204)
def revoke_resume(body:TokenInput,request:Request,session:Session=Depends(db)):
    limit(request,'resume-revoke',30,60)
    session.execute(delete(Resume).where(Resume.id==digest(body.token)));session.commit()

class LoginInput(BaseModel):
    username:str=Field(min_length=1,max_length=80)
    password:str=Field(min_length=1,max_length=200)

def auth(request:Request,session:Session=Depends(db)):
    token=request.cookies.get('atlas_session','');row=session.get(LoginSession,digest(token))
    if not row or row.expires<time.time(): raise HTTPException(401,'请登录管理员账号')
    if request.method not in ['GET','HEAD'] and not secrets.compare_digest(request.headers.get('X-CSRF-Token',''),row.csrf): raise HTTPException(403,'会话校验失败，请刷新后重试')
    return row

@app.post('/api/admin/login')
def login(body:LoginInput,request:Request,response:Response,session:Session=Depends(db)):
    limit(request,'login',6,900)
    admin=session.get(Admin,body.username)
    try: valid=admin is not None and hasher.verify(admin.password,body.password)
    except (VerifyMismatchError,InvalidHashError): valid=False
    if not valid: raise HTTPException(401,'账号或密码不正确')
    token=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(32)
    session.add(LoginSession(id=digest(token),username=admin.username,csrf=csrf,expires=time.time()+12*3600));cleanup(session);session.commit()
    response.set_cookie('atlas_session',token,httponly=True,secure=COOKIE_SECURE,samesite='strict',max_age=12*3600,path='/')
    return {'username':admin.username,'csrf':csrf}

@app.get('/api/admin/me')
def me(user=Depends(auth)): return {'username':user.username,'csrf':user.csrf}

@app.post('/api/admin/logout',status_code=204)
def logout(response:Response,user=Depends(auth),session:Session=Depends(db)):
    row=session.get(LoginSession,user.id)
    if row: session.delete(row);session.commit()
    response.delete_cookie('atlas_session',path='/')

@app.get('/api/admin/overview')
def overview(user=Depends(auth),session:Session=Depends(db)):
    cleanup(session)
    versions=session.scalars(select(Questionnaire).order_by(Questionnaire.created.desc())).all()
    stats=session.execute(select(Event.day,Event.mode,Event.kind,func.count()).group_by(Event.day,Event.mode,Event.kind).order_by(Event.day.desc()).limit(120)).all()
    logs=session.scalars(select(Audit).order_by(Audit.created.desc()).limit(30)).all()
    return {'current':current(session).id,'versions':[{'id':v.id,'title':v.title,'status':v.status,'created':v.created,'published':v.published} for v in versions],'stats':[{'day':r[0],'mode':r[1],'kind':r[2],'count':r[3]} for r in stats],'logs':[{'action':r.action,'created':r.created} for r in logs],'template':DEFAULT_TEMPLATE,'facets':{k:{x:v[x] for x in ['title','high','low']} for k,v in FACETS.items()}}

def submission_data(row:Submission):
    try:
        return json.loads(cipher.decrypt(row.encrypted.encode()).decode())
    except Exception:
        raise HTTPException(500,'提交记录暂时无法读取，请联系管理员。')

@app.get('/api/admin/submissions')
def submissions(user=Depends(auth),session:Session=Depends(db)):
    rows=session.scalars(select(Submission).order_by(Submission.created.desc())).all()
    items=[]
    for row in rows:
        data=submission_data(row);report=data.get('report',{})
        items.append({'id':row.id,'studentId':data.get('studentId',''),'studentName':data.get('studentName',''),'mode':row.mode,'version':row.version,'created':row.created,'type':report.get('type',''),'answered':report.get('coverage',{}).get('answered',0),'supportRequested':bool(data.get('supportRequested',False))})
    return {'total':len(items),'items':items}

@app.get('/api/admin/submissions/{submission_id}')
def submission_detail(submission_id:str,user=Depends(auth),session:Session=Depends(db)):
    row=session.get(Submission,submission_id)
    if not row: raise HTTPException(404,'提交记录不存在。')
    data=submission_data(row)
    return {'id':row.id,'studentId':data.get('studentId',''),'studentName':data.get('studentName',''),'mode':row.mode,'version':row.version,'created':row.created,'answers':data.get('answers',{}),'report':data.get('report'),'supportRequested':bool(data.get('supportRequested',False))}

@app.get('/api/admin/submissions/{submission_id}/export')
def export_submission(submission_id:str,user=Depends(auth),session:Session=Depends(db)):
    row=session.get(Submission,submission_id)
    if not row: raise HTTPException(404,'提交记录不存在。')
    data=submission_data(row)
    payload={'id':row.id,'studentId':data.get('studentId',''),'studentName':data.get('studentName',''),'mode':row.mode,'version':row.version,'created':row.created,'answers':data.get('answers',{}),'report':data.get('report'),'supportRequested':bool(data.get('supportRequested',False))}
    filename=f'mbti-submission-{re.sub(r"[^A-Za-z0-9_-]", "-", row.id)[:60]}.json'
    return Response(content=json.dumps(payload,ensure_ascii=False,indent=2),media_type='application/json; charset=utf-8',headers={'Content-Disposition':f'attachment; filename="{filename}"'})

class NewVersion(BaseModel):
    source:str=Field(max_length=80)
    title:str=Field(min_length=2,max_length=160)

@app.post('/api/admin/versions')
def new_version(body:NewVersion,user=Depends(auth),session:Session=Depends(db)):
    row=session.get(Questionnaire,body.source)
    if not row: raise HTTPException(404,'来源版本不存在')
    bank=json.loads(row.payload);version='v'+datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')+'-'+secrets.token_hex(3)
    bank['id']=version;bank['title']=body.title
    session.add(Questionnaire(id=version,title=body.title,status='draft',payload=json.dumps(bank,ensure_ascii=False)));session.commit()
    return {'id':version}

@app.get('/api/admin/versions/{version}')
def admin_version(version:str,user=Depends(auth),session:Session=Depends(db)):
    row=session.get(Questionnaire,version)
    if not row: raise HTTPException(404,'版本不存在')
    return {'status':row.status,'bank':json.loads(row.payload)}

class BankInput(BaseModel):
    bank:dict

@app.put('/api/admin/versions/{version}')
def save_version(version:str,body:BankInput,user=Depends(auth),session:Session=Depends(db)):
    row=session.get(Questionnaire,version)
    if not row: raise HTTPException(404,'版本不存在')
    if row.status!='draft': raise HTTPException(409,'已发布版本不可直接修改，请创建新草稿')
    body.bank['id']=version
    try: validate_bank(body.bank)
    except (ValueError,KeyError,TypeError) as e: raise HTTPException(422,str(e))
    row.payload=json.dumps(body.bank,ensure_ascii=False);row.title=str(body.bank.get('title',row.title))[:160];session.commit()
    return {'saved':True}

@app.post('/api/admin/versions/{version}/publish')
def publish_version(version:str,user=Depends(auth),session:Session=Depends(db)):
    row=session.get(Questionnaire,version)
    if not row: raise HTTPException(404,'版本不存在')
    if row.status!='draft': raise HTTPException(409,'该版本已发布')
    try: validate_bank(json.loads(row.payload))
    except (ValueError,KeyError,TypeError) as e: raise HTTPException(422,str(e))
    row.status='published';row.published=time.time()
    session.add(Audit(id=secrets.token_hex(16),action=f'{user.username} 发布问卷 {version}'));session.commit()
    return {'published':True}

@app.post('/api/admin/versions/{version}/preview')
def preview_version(version:str,body:ScoreInput,user=Depends(auth),session:Session=Depends(db)):
    row=session.get(Questionnaire,version)
    if not row: raise HTTPException(404,'版本不存在')
    try: result=score(json.loads(row.payload),body.mode,body.answers)
    except ValueError as e: raise HTTPException(422,str(e))
    result['id']='preview-'+body.submissionId;return result

class PasswordInput(BaseModel):
    current:str=Field(max_length=200)
    password:str=Field(min_length=9,max_length=200)

@app.post('/api/admin/password',status_code=204)
def password_change(body:PasswordInput,user=Depends(auth),session:Session=Depends(db)):
    admin=session.get(Admin,user.username)
    try: hasher.verify(admin.password,body.current)
    except (VerifyMismatchError,InvalidHashError): raise HTTPException(422,'当前密码不正确')
    admin.password=hasher.hash(body.password)
    session.execute(delete(LoginSession).where(LoginSession.username==user.username));session.commit()
