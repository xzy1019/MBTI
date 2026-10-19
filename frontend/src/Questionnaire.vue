<script setup lang="ts">
import {computed,nextTick,onMounted,onBeforeUnmount,ref} from 'vue'
import {useRouter} from 'vue-router'
import {ArrowLeft,ArrowRight,BookmarkCheck,Coffee,Check,Grid2X2,Link,WifiOff,X,Copy,LoaderCircle} from 'lucide-vue-next'
import QRCode from 'qrcode'
import {api,post,load,save,keepReport,fetchBank,uid,date,sections,labels,ApiError,type Bank,type Draft,type Mode,type Report} from './lib'
const props=defineProps<{mode:Mode}>();const router=useRouter()
const bank=ref<Bank>();const draft=ref<Draft>();const basicDraft=ref<Draft>();const started=ref(false);const paused=ref(false);const loading=ref(true);const submitting=ref(false);const error=ref('');const saved=ref('');const saveFailure=ref(false);const reuse=ref(true);const showGrid=ref(false);const breakAt=ref<number|null>(null);const showReview=ref(false)
const studentId=ref('');const studentName=ref('');const supportRequested=ref(false)
const advancing=ref(false);const questionHeading=ref<HTMLHeadingElement>();
const shareDialog=ref<HTMLDialogElement>();const shareURL=ref('');const qr=ref('');const sharing=ref(false);const syncError=ref('');const online=ref(navigator.onLine)
let advanceTimer:ReturnType<typeof setTimeout>|undefined;let advanceRevision=0
let writes=Promise.resolve();let syncTimer:ReturnType<typeof setTimeout>|undefined;let syncTask:Promise<boolean>|undefined;let syncPending=false;let active=true
const answers=computed(()=>draft.value?.answers||{});const qs=computed(()=>bank.value?.questions||[]);const index=computed(()=>draft.value?.index||0);const q=computed(()=>qs.value[index.value]);const answered=computed(()=>qs.value.filter(x=>Object.hasOwn(answers.value,x.id)).length);const complete=computed(()=>answered.value===qs.value.length&&qs.value.length>0);const hasChoice=computed(()=>!!q.value&&Object.hasOwn(answers.value,q.value.id));const canReuse=computed(()=>props.mode==='full'&&basicDraft.value?.version===bank.value?.id&&Object.keys(basicDraft.value?.answers||{}).length===99)
const sectionList=computed(()=>props.mode==='full'?['base','personality','career','social','romance']:['base'])
const sectionProgress=computed(()=>{const items=qs.value.filter(x=>x.section===q.value?.section);return{done:items.filter(x=>Object.hasOwn(answers.value,x.id)).length,total:items.length}})
const boundaries=computed(()=>props.mode==='basic'?[25,50,75]:[25,50,75,99,120,140,160,180,200,220,240,260,280])
let lastSection=''
function reach(){if(!draft.value||!q.value||lastSection===q.value.section)return;lastSection=q.value.section;void post('/api/events/progress',{id:draft.value.id,mode:props.mode,section:lastSection}).catch(()=>{})}
function persist(){if(!draft.value)return writes;draft.value.updatedAt=new Date().toISOString();const snapshot=JSON.parse(JSON.stringify(draft.value));writes=writes.catch(()=>{}).then(()=>save(`draft:${props.mode}`,snapshot)).then(()=>{saved.value='已保存到本机';saveFailure.value=false}).catch(e=>{saved.value=e.message;saveFailure.value=true;throw e});return writes}
function syncDraft():Promise<boolean>{
  if(syncTask){syncPending=true;return syncTask}
  syncTask=(async()=>{
    let ok=true
    do{
      syncPending=false
      if(!draft.value?.resume||syncError.value)return false
      const token=draft.value.resume.token;const snapshot=JSON.parse(JSON.stringify(draft.value))
      try{const response=await api<{revision:number}>(`/api/resume-sessions/current`,{method:'PATCH',body:JSON.stringify({token,revision:snapshot.resume.revision,draft:snapshot})});if(draft.value?.resume?.token===token){draft.value.resume.revision=response.revision;await persist();saved.value='本机及续答链接已更新'}}
      catch(e){ok=false;const err=e as ApiError;if(err.status===409||err.status===404)syncError.value=err.message;else saved.value='本机已保存，续答链接待联网更新'}
    }while(syncPending&&active&&ok)
    return ok
  })().finally(()=>{syncTask=undefined})
  return syncTask
}
function scheduleSync(){clearTimeout(syncTimer);syncTimer=setTimeout(()=>void syncDraft(),900)}
function cancelAdvance(){clearTimeout(advanceTimer);advanceTimer=undefined;advanceRevision++;advancing.value=false}
async function choose(value:number|null){
  if(!draft.value||!q.value||advancing.value)return
  const questionId=q.value.id;const revision=++advanceRevision;advancing.value=true
  draft.value.answers={...draft.value.answers,[questionId]:value};error.value=''
  try{
    await persist();scheduleSync()
    if(!active||revision!==advanceRevision)return
    advanceTimer=setTimeout(()=>{
      advanceTimer=undefined
      if(!active||revision!==advanceRevision||q.value?.id!==questionId)return
      void next()
    },300)
  }catch(e){if(revision===advanceRevision){cancelAdvance();error.value=(e as Error).message}}
}
async function go(i:number){cancelAdvance();if(!draft.value)return;draft.value.index=Math.max(0,Math.min(qs.value.length-1,i));showGrid.value=false;error.value='';reach();try{await persist();scheduleSync()}catch(e){error.value=(e as Error).message}window.scrollTo({top:0,behavior:'instant'});await nextTick();questionHeading.value?.focus({preventScroll:true})}
async function next(){cancelAdvance();if(!hasChoice.value)return;const after=index.value+1;if(after===99&&props.mode==='full'){breakAt.value=99;return}if(boundaries.value.includes(after)){breakAt.value=after;return}if(after>=qs.value.length){showReview.value=true;return}await go(after)}
async function continueBreak(){const n=breakAt.value;breakAt.value=null;if(n!==null)await go(n)}
async function begin(){
  if(!bank.value)return
  studentId.value=studentId.value.trim();studentName.value=studentName.value.trim()
  if(!studentId.value||!studentName.value){error.value='请先填写学号和姓名，再开始答题。';return}
  const existing=draft.value
  if(!existing){
    const base=canReuse.value&&reuse.value?basicDraft.value:undefined
    draft.value={id:uid(),mode:props.mode,version:bank.value.id,answers:base?{...base.answers}:{},index:base?99:0,startedAt:new Date().toISOString(),updatedAt:new Date().toISOString(),studentId:studentId.value,studentName:studentName.value}
    await persist();void post('/api/events/start',{id:draft.value.id,mode:props.mode}).catch(()=>{})
  }else{
    existing.studentId=studentId.value;existing.studentName=studentName.value;draft.value=existing;await persist()
  }
  started.value=true;error.value='';reach()
}
async function restart(){if(!confirm('重新开始将替换本机当前版本的草稿，已保存的历史报告不会删除。继续吗？'))return;cancelAdvance();if(draft.value?.resume)await revoke();draft.value=undefined;started.value=false;paused.value=false;showReview.value=false;breakAt.value=null;await begin()}
async function submit(mode:Mode=props.mode){
  if(!draft.value||!bank.value||submitting.value)return
  cancelAdvance()
  const relevant=mode==='basic'?qs.value.slice(0,99):qs.value;const missing=relevant.findIndex(item=>!Object.hasOwn(answers.value,item.id));if(missing>=0){error.value='还有未回答的题目，已为你定位。';showReview.value=false;await go(missing);return}
  submitting.value=true;error.value=''
  try{
    await persist();const chosen=Object.fromEntries(relevant.map(item=>[item.id,answers.value[item.id]]));const submissionId=mode===props.mode?draft.value.id:`${draft.value.id}-basic`
    const report=await post<Report>('/api/assessments/score',{mode,version:draft.value.version,answers:chosen,submissionId,studentId:draft.value.studentId||studentId.value,studentName:draft.value.studentName||studentName.value,supportRequested:supportRequested.value});await keepReport(report)
    if(mode===props.mode&&draft.value.resume){await revoke()}
    await router.push(`/report?id=${report.id}`)
  }catch(e){error.value=(e as Error).message}finally{submitting.value=false}
}
async function share(){
  cancelAdvance();if(!draft.value)return;shareDialog.value?.showModal();sharing.value=true;error.value='';
  try{await persist();if(!draft.value.resume){draft.value.resume=await post('/api/resume-sessions',{draft:draft.value});await persist()}else{const ok=await syncDraft();if(!ok)throw new Error(syncError.value||'暂时无法更新续答链接，请联网后重试。')}shareURL.value=`${new URL(router.resolve('/resume').href,location.origin).href}#${draft.value.resume!.token}`;qr.value=await QRCode.toDataURL(shareURL.value,{width:240,margin:2,color:{dark:'#253a31',light:'#ffffff'}})}catch(e){error.value=(e as Error).message}finally{sharing.value=false}
}
async function revoke(){if(!draft.value?.resume)return;await api('/api/resume-sessions/current',{method:'DELETE',body:JSON.stringify({token:draft.value.resume.token})});delete draft.value.resume;syncError.value='';shareURL.value='';qr.value='';await persist();shareDialog.value?.close()}
async function restoreLatest(){cancelAdvance();if(!draft.value?.resume||!confirm('载入其他设备的最新版本将替换当前本机答案，继续吗？'))return;try{const token=draft.value.resume.token;const r=await post('/api/resume-sessions/claim',{token});draft.value={...r.draft,updatedAt:new Date().toISOString(),resume:{token,revision:r.revision,expires:r.expires}};syncError.value='';await persist()}catch(e){error.value=(e as Error).message}}
async function copyURL(){try{if(navigator.clipboard){await navigator.clipboard.writeText(shareURL.value);saved.value='续答链接已复制'}else saved.value='请长按下方链接复制'}catch{saved.value='请手动复制下方链接'}}
function connectivity(){online.value=navigator.onLine;if(online.value)void syncDraft()}
function preventClose(e:BeforeUnloadEvent){if(saveFailure.value||submitting.value){e.preventDefault();e.returnValue=''}}
onMounted(async()=>{window.addEventListener('online',connectivity);window.addEventListener('offline',connectivity);window.addEventListener('beforeunload',preventClose);try{draft.value=await load<Draft>(`draft:${props.mode}`);basicDraft.value=await load<Draft>('draft:basic');studentId.value=draft.value?.studentId||basicDraft.value?.studentId||'';studentName.value=draft.value?.studentName||basicDraft.value?.studentName||'';bank.value=await fetchBank(props.mode,draft.value?.version);if(draft.value&&studentId.value&&studentName.value)started.value=true}catch(e){error.value=(e as Error).message}finally{loading.value=false}})
onBeforeUnmount(()=>{active=false;cancelAdvance();clearTimeout(syncTimer);window.removeEventListener('online',connectivity);window.removeEventListener('offline',connectivity);window.removeEventListener('beforeunload',preventClose)})
</script>

<template>
  <div class="page quiz-page">
    <div class="page-heading"><div><span class="eyebrow">YOUR OWN PACE</span><h1>{{mode==='basic'?'精简测试':'详细测试'}} <span class="serif accent">{{mode==='basic'?99:300}}</span><small> 题</small></h1></div><RouterLink to="/" class="text-button">返回首页</RouterLink></div>
    <div v-if="loading" class="loading-state"><LoaderCircle class="spin"/> 正在加载问卷与本机草稿…</div>
    <div v-if="error" class="alert error" role="alert">{{error}}<button v-if="!bank" class="text-button" @click="router.go(0)">重试</button></div>
    <div v-if="!online" class="alert"><WifiOff :size="16"/> 你正在离线作答。本机继续保存，联网后再提交生成报告。</div>
    <template v-if="bank">
      <section v-if="!started" class="intro-panel surface">
        <span class="eyebrow">给自己一段认真探索的时间</span><h2 class="serif">没有正确答案，<br>选择更接近平时的你。</h2><p>预计 {{mode==='basic'?'15–25':'50–80'}} 分钟，可以分次完成。请按近半年的通常习惯回答，区分真实行为与理想形象。</p>
        <div class="identity-fields"><label class="field">学号<input v-model="studentId" autocomplete="off" maxlength="80" placeholder="请输入学号" @input="error=''" required></label><label class="field">姓名<input v-model="studentName" autocomplete="name" maxlength="80" placeholder="请输入姓名" @input="error=''" required></label></div>
        <div class="intro-points"><p><BookmarkCheck :size="19"/>选择后自动保存并进入下一题；换设备请主动生成续答链接。</p><p><Coffee :size="19"/>每完成一个小节可以休息；没有强制计时。</p><p><Check :size="19"/>专项经验题可选“不适用”，信息不足会如实说明。</p></div>
        <label v-if="canReuse" class="check-row"><input type="checkbox" v-model="reuse">沿用 {{date(basicDraft!.startedAt)}} 的 99 题答案，仅补答 201 题。</label>
        <p class="fineprint">{{bank.notice}} 学号、姓名、答案和报告会在提交后保存到管理员后台，用于查看与导出；草稿仍默认保存在本机。</p><button class="primary" @click="begin">开始探索 <ArrowRight :size="17"/></button>
      </section>
      <template v-else-if="draft&&q">
        <div class="quiz-toolbar"><span class="saved-state" :class="{danger:saveFailure}" role="status"><BookmarkCheck :size="15"/>{{saved||'本机草稿已载入'}} <small v-if="draft.updatedAt">{{new Date(draft.updatedAt).toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit'})}}</small></span><div class="toolbar-actions"><button class="text-button" @click="cancelAdvance();showGrid=!showGrid"><Grid2X2 :size="15"/>题号</button><button class="text-button" @click="share"><Link :size="15"/>换设备</button><button class="text-button" @click="cancelAdvance();paused=!paused"><Coffee :size="15"/>{{paused?'继续':'暂停'}}</button></div></div>
        <div v-if="syncError" class="alert error" role="alert"><div>{{syncError}} 本机答案仍然保留。<div class="button-row"><button class="secondary" @click="restoreLatest">载入最新草稿</button><button class="secondary" @click="revoke">撤销链接，保留本机</button></div></div></div>
        <div v-if="mode==='full'" class="module-strip" aria-label="测试章节"><span v-for="s in sectionList" :key="s" :class="{active:q.section===s}" :aria-current="q.section===s?'step':undefined">{{sections[s]}}</span></div>
        <div class="progress-label"><span>第 {{index+1}} / {{qs.length}} 题 · {{sections[q.section]}}</span><span>已答 {{answered}} / {{qs.length}}</span></div><div class="progress" role="progressbar" aria-label="总答题进度" :aria-valuenow="answered" :aria-valuemax="qs.length" aria-valuemin="0"><i :style="{width:`${answered/qs.length*100}%`}"></i></div><div class="section-status">本章节已答 {{sectionProgress.done}} / {{sectionProgress.total}} 题</div>
        <section v-if="showGrid" class="surface question-overview"><div class="panel-heading"><h2>题号总览</h2><button class="icon-button" aria-label="收起题号" @click="showGrid=false"><X :size="19"/></button></div><p class="muted small">深色为已答，边框为当前题。选择题号可回看。</p><div class="question-grid"><button v-for="(item,i) in qs" :key="item.id" :class="{done:Object.hasOwn(answers,item.id),current:i===index}" :aria-label="`第 ${i+1} 题，${Object.hasOwn(answers,item.id)?'已答':'未答'}`" @click="go(i)">{{i+1}}</button></div></section>
        <section v-else-if="paused" class="surface pause-panel"><Coffee :size="34"/><h2 class="serif">先歇一会儿，再继续。</h2><p>你已完成 {{answered}} 题。答案保存在当前浏览器，稍后回来仍可继续。</p><button class="primary" @click="paused=false">继续探索 <ArrowRight :size="17"/></button></section>
        <section v-else-if="breakAt!==null" class="surface pause-panel"><Coffee :size="34"/><h2 class="serif">一个小节完成了。</h2><p>已经走过 {{breakAt}} 题，可以看看远处、伸展一下。按适合你的节奏继续。</p><div class="button-row centered"><button v-if="breakAt===99&&mode==='full'" class="secondary" :disabled="submitting" @click="submit('basic')">先看 99 题精简报告</button><button class="primary" @click="continueBreak">继续下一小节 <ArrowRight :size="17"/></button></div></section>
        <section v-else-if="showReview" class="surface pause-panel"><Check :size="34"/><h2 class="serif">把理解，带回生活。</h2><p>已完成 {{answered}} / {{qs.length}} 题；其中 {{Object.values(answers).filter(a=>a===null).length}} 题选择不适用。</p><p class="fineprint">报告会根据有效回答生成；信息不足的主题会明确说明。问卷不评估抑郁、暴力或其他心理风险。</p><label class="check-row support-request"><input v-model="supportRequested" type="checkbox">我希望管理员协助我联系学校支持资源</label><p v-if="supportRequested" class="fineprint">勾选后，管理员会看到你的姓名、学号和主动求助请求。中国大陆可拨全国心理援助热线 12356；如有眼前紧急危险，请联系可信任的人并拨打 110 或 120。</p><div class="button-row centered"><button class="secondary" @click="showReview=false;showGrid=true">回看答案</button><button class="primary" :disabled="submitting" @click="submit()"><LoaderCircle v-if="submitting" class="spin" :size="17"/>{{submitting?'正在生成报告…':'生成我的报告'}}</button></div></section>
        <section v-else class="surface question-card" :key="q.id"><span class="eyebrow">{{sections[q.section]}} · 真实的你</span><h2 ref="questionHeading" tabindex="-1">{{q.text}}</h2><p class="question-help">选择后自动进入下一题，可用“上一题”修改答案。</p><div class="answer-options" role="group" aria-label="选择符合程度"><button v-for="(label,i) in labels" :key="label" :data-answer="i-3" :disabled="advancing" :class="{selected:hasChoice&&answers[q.id]===i-3}" :aria-pressed="hasChoice&&answers[q.id]===i-3" @click="choose(i-3)"><span class="answer-circle">{{i+1}}</span><span class="answer-label">{{label}}</span></button></div><button v-if="q.na" class="na-button" :disabled="advancing" :class="{selected:hasChoice&&answers[q.id]===null}" :aria-pressed="hasChoice&&answers[q.id]===null" @click="choose(null)">不适用 / 无相关经历</button><p class="choice-status" aria-live="polite">{{advancing?'已选择，正在保存并进入下一题…':hasChoice?`已选择：${answers[q.id]===null?'不适用 / 无相关经历':labels[answers[q.id]!+3]}`:'请选择最符合你的选项'}}</p><div class="question-actions"><button class="secondary" :disabled="index===0" @click="go(index-1)"><ArrowLeft :size="16"/>上一题</button><button class="primary" :disabled="!hasChoice||advancing" @click="next">{{index===qs.length-1?'检查并生成报告':'下一题'}}<ArrowRight :size="16"/></button></div></section>
        <div class="quiz-bottom"><span>所有偏好都值得理解，没有好坏排名。</span><div class="button-row"><button v-if="complete&&!showReview" class="text-button" @click="cancelAdvance();showReview=true;paused=false;breakAt=null;showGrid=false">生成报告</button><button class="text-button" @click="restart">重新开始</button></div></div>
      </template>
    </template>
    <dialog ref="shareDialog" class="share-dialog"><div class="panel-heading"><h2>换设备继续</h2><button class="icon-button" aria-label="关闭续答窗口" @click="shareDialog?.close()"><X :size="20"/></button></div><p>开启后，草稿会加密临时保存在服务器，有效期 7 天。仅在自己的设备打开，勿公开转发。</p><div v-if="sharing" class="loading-state"><LoaderCircle class="spin"/>正在准备续答链接…</div><template v-if="shareURL&&!syncError"><img v-if="qr" :src="qr" width="220" height="220" alt="在另一设备扫描续答二维码"><label class="field">续答链接<input readonly :value="shareURL" @focus="($event.target as HTMLInputElement).select()"></label><div class="button-row"><button class="primary" @click="copyURL"><Copy :size="16"/>复制链接</button><button class="secondary" @click="revoke">撤销链接</button></div><p class="fineprint" v-if="draft?.resume">到期：{{date(draft.resume.expires)}}。完成或撤销后删除服务器临时副本。</p></template><p v-if="error||syncError" class="danger" role="alert">{{syncError||error}}</p></dialog>
  </div>
</template>
