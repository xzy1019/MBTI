import copy
import pytest
from backend.app.content import make_bank
from backend.app.scoring import score,validate_bank

@pytest.fixture
def bank(): return validate_bank(make_bank())

def answers(bank,value=3,mode='full'):
    qs=bank['questions'][:99] if mode=='basic' else bank['questions']
    return {q['id']:q['direction']*value for q in qs}

@pytest.mark.parametrize('mode,count',['basic 99'.split(), 'full 300'.split()])
def test_structure(bank,mode,count):
    r=score(bank,mode,answers(bank,mode=mode))
    assert r['coverage']['answered']==int(count)
    assert [d['count'] for d in r['dimensions']]==([25,25,25,24] if mode=='basic' else [30]*4)
    assert len(r['topics'])==(0 if mode=='basic' else 18)

@pytest.mark.parametrize('value,code,percent',[(3,'ESTJ',100),(-3,'INFP',0),(0,'XXXX',50)])
@pytest.mark.parametrize('mode',['basic','full'])
def test_keyed_reverse_and_normalization(bank,value,code,percent,mode):
    r=score(bank,mode,answers(bank,value,mode))
    assert r['type']==code
    assert all(d['score']==percent for d in r['dimensions'])
    assert all(d['borderline']==(value==0) for d in r['dimensions'])

def test_baseline_preserved_and_domains_independent(bank):
    a=answers(bank);b=copy.deepcopy(a)
    for q in bank['questions'][120:]:b[q['id']]*=-1
    r,s=score(bank,'full',a),score(bank,'full',b)
    assert r['type']==s['type'] and r['dimensions']==s['dimensions']
    assert r['priorities']!=s['priorities']
    base=score(bank,'basic',{q['id']:a[q['id']] for q in bank['questions'][:99]})
    assert r['baseline']==base['dimensions']

def test_na_not_zero_and_minimum_coverage(bank):
    a=answers(bank);qs=bank['questions'][120:130]
    for q in qs[:3]:a[q['id']]=None
    r=score(bank,'full',a)['topics'][0]
    assert r['valid']==7 and r['score']==100 and not r['insufficient']
    a[qs[3]['id']]=None
    r=score(bank,'full',a)['topics'][0]
    assert r['valid']==6 and r['score'] is None and r['insufficient'] and not r['evidence']

@pytest.mark.parametrize('bad',[True,3.5,'3',4,-4,None])
def test_invalid_core_answer(bank,bad):
    a=answers(bank);a[bank['questions'][0]['id']]=bad
    with pytest.raises(ValueError):score(bank,'full',a)

def test_missing_unknown_and_wrong_mode(bank):
    a=answers(bank);a.pop(next(iter(a)))
    with pytest.raises(ValueError):score(bank,'full',a)
    a['unknown']=0
    with pytest.raises(ValueError):score(bank,'full',a)
    with pytest.raises(ValueError):score(bank,'500',a)

@pytest.mark.parametrize('mutation',['duplicate','direction','mapping','recommendation','template'])
def test_publish_validation(bank,mutation):
    if mutation=='duplicate':bank['questions'][1]['text']=bank['questions'][0]['text']
    if mutation=='direction':bank['questions'][0]['direction']=True
    if mutation=='mapping':bank['questions'][0]['section']='career'
    if mutation=='recommendation':bank['recommendations']={'unknown':{'high':'这是一条无效的建议内容。'}}
    if mutation=='template':bank['template']={'unknown':'这是一条无效的模板内容。'}
    with pytest.raises(ValueError):validate_bank(bank)

def test_reproducible_numeric_results_and_template(bank):
    a=answers(bank,2)
    r=score(bank,'full',a);s=score(bank,'full',a)
    for k in ['createdAt']:r.pop(k);s.pop(k)
    assert r==s
    bank['template']={'review':'每隔七天记录精力、完成结果和协商反馈，再核对是否调整。'}
    assert score(bank,'full',a)['topics'][0]['review']==bank['template']['review']
