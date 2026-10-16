from datetime import datetime, timezone
from .content import DIMENSIONS, FACETS, TYPE_NAMES, ALGORITHM
from .guidance import CONTEXTS, DEFAULT_TEMPLATE

SECTIONS={"base":"基础人格","personality":"人格深化","career":"职业发展","social":"社交关系","romance":"恋爱关系"}

def validate_bank(bank):
    qs=bank.get("questions",[])
    if len(qs)!=300: raise ValueError("详细题库必须恰好 300 题")
    if len({q.get('id') for q in qs})!=300: raise ValueError("题目编号必须唯一")
    if len({q.get('text','').strip() for q in qs})!=300: raise ValueError("存在重复题目")
    for i,q in enumerate(qs):
        if not isinstance(q.get('text'),str) or not 8<=len(q['text'].strip())<=240: raise ValueError(f"第 {i+1} 题文字长度不合适")
        if type(q.get('direction')) is not int or q['direction'] not in [-1,1]: raise ValueError("评分方向必须是 +1 或 -1")
        if q.get('section') not in SECTIONS: raise ValueError("未知章节")
        if i<99 and q['section']!='base': raise ValueError("前 99 题必须为共用基础题")
        if 99<=i<120 and q['section']!='personality': raise ValueError("第 100–120 题必须为人格深化")
        if i>=120 and q['section']!=['career','social','romance'][(i-120)//60]: raise ValueError("专项顺序或题量不正确")
        if i<120 and (q.get('dimension') not in DIMENSIONS or q.get('na')): raise ValueError("人格题须归属四维且不可不适用")
        if i>=120 and (q.get('facet') not in FACETS or q['facet'].split('.')[0]!=q['section'] or q.get('dimension') is not None or not q.get('na')): raise ValueError("专项题归属不正确")
    for dim,n in {"EI":25,"SN":25,"TF":25,"JP":24}.items():
        if sum(q.get('dimension')==dim for q in qs[:99])!=n: raise ValueError("基础四维题量不正确")
        if sum(q.get('dimension')==dim for q in qs[:120])!=30: raise ValueError("扩展四维必须各 30 题")
    for f in FACETS:
        if sum(q.get('facet')==f for q in qs)!=10: raise ValueError("专项主题必须各 10 题")
    for key,value in bank.get('recommendations',{}).items():
        if key not in FACETS or not isinstance(value,dict): raise ValueError("未知建议主题")
        for direction,text in value.items():
            if direction not in ['high','low'] or not isinstance(text,str) or not 8<=len(text)<=1200: raise ValueError("建议内容无效")
    for key,text in bank.get("template",{}).items():
        if key not in DEFAULT_TEMPLATE or not isinstance(text,str) or not 8<=len(text)<=1200: raise ValueError("报告模板内容无效")
    return bank

def score(bank, mode, answers):
    if mode not in ['basic','full']: raise ValueError("未知测试版本")
    qs=bank['questions'][:99] if mode=='basic' else bank['questions']
    expected={q['id'] for q in qs}
    if set(answers)!=expected: raise ValueError("题目不完整或包含未知题目，请检查漏题与问卷版本")
    for q in qs:
        a=answers[q['id']]
        if a is None:
            if not q.get('na'): raise ValueError("人格题不能选择不适用")
        elif type(a) is not int or not -3<=a<=3: raise ValueError("答案必须为 -3 至 3 的整数")
    def position(items):
        valid=[q for q in items if answers[q['id']] is not None]
        return (100*(sum(answers[q['id']]*q['direction'] for q in valid)+3*len(valid))/(6*len(valid))) if valid else None
    def dims(items):
        result=[]
        for key,meta in DIMENSIONS.items():
            selected=[q for q in items if q.get('dimension')==key]
            p=position(selected)
            letter='X' if abs(p-50)<1e-9 else key[0 if p>50 else 1]
            strength,blindspot,scenario=CONTEXTS[key]["high" if p>=50 else "low"]
            if 45<=p<=55:
                strength="两端方法都可能成为可用资源，具体优势需要结合情境观察。"
                blindspot="偏好接近时，单个字母容易掩盖环境、角色与经验带来的差异。"
                scenario="选择一个最近的真实场景，记录你先采用了哪端方法、为什么，以及换一种方式是否更有效。"
            result.append({"strength":strength,"blindspot":blindspot,"scenario":scenario,"key":key,"title":meta['title'],"left":meta['left'],"right":meta['right'],"score":round(p,1),"letter":letter,"borderline":45<=p<=55,"count":len(selected),"observation":meta['high' if p>=50 else 'low'],"advice":meta['high_tip' if p>=50 else 'low_tip'] if not 45<=p<=55 else f"你的两端偏好接近。分别观察独处与互动、稳定与变化等具体场景，避免仅凭字母限制自己。在这一维可以尝试：{meta['high_tip']}"})
        return result
    dimensions=dims(qs[:120] if mode=='full' else qs)
    baseline=dims(qs[:99])
    code=''.join(d['letter'] for d in dimensions)
    candidates=[c for c in TYPE_NAMES if all(a=='X' or a==b for a,b in zip(code,c))]
    topics=[]
    for key,meta in FACETS.items():
        items=[q for q in qs if q.get('facet')==key]
        if not items: continue
        valid=[q for q in items if answers[q['id']] is not None]
        p=position(items);enough=len(valid)>=7
        direction='high' if p is not None and p>=50 else 'low'
        evidence=sorted(valid,key=lambda q:abs(answers[q['id']]),reverse=True)[:2]
        advice=bank.get('recommendations',{}).get(key,{}).get(direction,meta[direction])
        topics.append({"key":key,"section":key.split('.')[0],"title":meta['title'],"left":meta['left'],"right":meta['right'],"score":round(p,1) if enough else None,"valid":len(valid),"total":10,"insufficient":not enough,"balanced":enough and 45<=p<=55,"observation":("两种方式都可能适合你，需结合情境核对" if enough and 45<=p<=55 else (f"你的回答相对偏向{meta['right'] if direction=='high' else meta['left']}" if enough else "当前回答不足以支持个性化判断")),"advice":advice if enough else "先回顾一个真实的日常情境：当时你需要什么、做了什么、有什么感受。信息充分后再作进一步判断。","evidence":[{"text":q['text'],"answer":answers[q['id']]} for q in evidence] if enough else [],"review":bank.get("template",{}).get("review",DEFAULT_TEMPLATE["review"])})
    if mode=='full':
        priorities=[]
        for section in ['career','social','romance']:
            available=[t for t in topics if t['section']==section and not t['insufficient']]
            selected=max(available,key=lambda t:abs(t['score']-50)) if available else None
            priorities.append({"title":f"{SECTIONS[section]} · {selected['title'] if selected else '先补充真实情境'}","text":selected['advice'] if selected else "该模块信息不足。先记录自己在一个具体场景中的需要与反应，再核对是否愿意补充相关回答。","source":section})
    else:
        priorities=[{"title":d['title'],"text":d['advice'],"source":'dimensions'} for d in sorted(dimensions,key=lambda d:abs(d['score']-50),reverse=True)[:3]]
    baseline_code=''.join(d['letter'] for d in baseline)
    warnings=[]
    values=[v for v in answers.values() if v is not None]
    if values and len(set(values))==1: warnings.append("本次有效题目使用了相同选项。若并非你的通常体验，可回看具体情境；系统没有因此改动分数。")
    if any(d['borderline'] for d in dimensions): warnings.append("部分维度接近均衡，少量回答变化就可能影响类型字母；请优先阅读连续分数和情境解释。")
    if any(t['insufficient'] for t in topics): warnings.append("部分专项主题有效回答不足，只提供反思问题，不生成确定的个性判断。")
    if mode=='full' and baseline_code!=code: warnings.append(f"99 题基线为 {baseline_code}，扩展人格观察为 {code}。新增情境回答改变了偏好位置，不代表前次回答错误。")
    daily_advice=[{"title":"学习与工作","text":dimensions[1]["scenario"]+dimensions[3]["advice"]},{"title":"沟通与关系","text":dimensions[2]["scenario"]},{"title":"压力与恢复","text":dimensions[0]["scenario"]+"记录持续耗能的情境，先调整一个可改变的负荷。"}]
    return {"template":{**DEFAULT_TEMPLATE,**bank.get("template",{})},"templateVersion":bank["id"],"schema":1,"mode":mode,"version":bank['id'],"algorithm":ALGORITHM,"createdAt":datetime.now(timezone.utc).isoformat(),"type":code,"name":TYPE_NAMES.get(code,"多面偏好探索者"),"candidates":candidates,"dimensions":dimensions,"baseline":baseline,"baselineType":baseline_code,"topics":topics,"priorities":priorities,"coverage":{"answered":len(answers),"valid":len(values),"notApplicable":len(answers)-len(values)},"warnings":warnings,"notice":bank.get('notice',''),"plan":[{"title":"觉察自己的节奏","task":"每天记录一件让你投入的事、一件耗能的事，以及当时的环境。不要急着评价好坏。","review":"一周后寻找重复出现的情境，选一个可以调整的小环节。"},{"title":"做一次小范围尝试","task":priorities[0]['text'],"review":"记录实际感受与可见结果，用体验验证偏好。"},{"title":"练习清晰地表达需要","task":"选一个日常安排，用事实、感受、需要和一个具体请求与相关的人沟通。","review":"核对对方是否理解，也询问对方愿意怎样配合。"},{"title":"复盘并保留有效方法","task":"回顾前三周，保留一个有效习惯，调整一个不适合的做法，为下一阶段设小目标。","review":"以可持续程度与现实反馈衡量变化，不以人格字母衡量好坏。"}] if mode=='full' else [{"title":"7 天觉察练习","task":"每天记录互动与独处、具体与抽象、标准与价值、计划与变化中，哪种安排更适合当时的你。","review":"第七天挑一个小调整实践，再比较精力与完成体验。"}],"dailyAdvice":daily_advice}
