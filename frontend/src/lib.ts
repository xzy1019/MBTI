export type Mode='basic'|'full'
export type Question={id:string;text:string;section:string;na:boolean}
export type Bank={id:string;title:string;mode:Mode;notice:string;questions:Question[]}
export type Draft={id:string;mode:Mode;version:string;answers:Record<string,number|null>;index:number;startedAt:string;updatedAt:string;studentId?:string;studentName?:string;resume?:{token:string;revision:number;expires:number}}
export type Dimension={strength:string;blindspot:string;scenario:string;key:string;title:string;left:string;right:string;score:number;letter:string;borderline:boolean;count:number;observation:string;advice:string}
export type Topic={key:string;section:string;title:string;left:string;right:string;score:number|null;valid:number;total:number;insufficient:boolean;balanced:boolean;observation:string;advice:string;evidence:{text:string;answer:number}[];review:string}
export type Report={template:{overview:string;reflection:string;review:string};templateVersion:string;id:string;schema:number;mode:Mode;version:string;algorithm:string;createdAt:string;type:string;name:string;candidates:string[];dimensions:Dimension[];baseline:Dimension[];baselineType:string;topics:Topic[];priorities:{title:string;text:string;source:string}[];coverage:{answered:number;valid:number;notApplicable:number};warnings:string[];notice:string;plan:{title:string;task:string;review:string}[];dailyAdvice:{title:string;text:string}[]}
export const sections:Record<string,string>={base:'基础人格',personality:'人格深化',career:'职业发展',social:'社交关系',romance:'恋爱关系'}
export const labels=['非常不符合','不符合','有点不符合','中立 / 视情况而定','有点符合','符合','非常符合']
export function uid(){const a=new Uint8Array(16);crypto.getRandomValues(a);return Array.from(a,b=>b.toString(16).padStart(2,'0')).join('')}
export function date(value:string|number){return new Date(typeof value==='number'?value*1000:value).toLocaleString('zh-CN',{year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'})}
export class ApiError extends Error{constructor(message:string,public status:number){super(message)}}
let csrf=''
export function setCsrf(value:string){csrf=value}
export async function api<T=any>(path:string,options:RequestInit={}):Promise<T>{
  const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),25000)
  try{
    const response=await fetch(import.meta.env.BASE_URL.replace(/\/$/,'')+path,{...options,signal:options.signal||controller.signal,credentials:'same-origin',cache:'no-store',headers:{'Content-Type':'application/json',...(csrf?{'X-CSRF-Token':csrf}:{}),...options.headers}})
    if(response.status===204)return undefined as T
    const data=await response.json().catch(()=>({detail:'服务暂时不可用，请稍后重试。'}))
    if(!response.ok)throw new ApiError(typeof data.detail==='string'?data.detail:'请求内容不正确，请检查后重试。',response.status)
    return data as T
  }catch(e){if(e instanceof ApiError)throw e;throw new ApiError(navigator.onLine?'连接暂时中断，答案仍保留在本机，请重试。':'当前处于离线状态。可以继续已加载的问卷，联网后再生成报告。',0)}finally{clearTimeout(timer)}
}
export const post=<T=any>(path:string,body:any)=>api<T>(path,{method:'POST',body:JSON.stringify(body)})
let opening:Promise<IDBDatabase>|null=null
function database(){return opening??=new Promise<IDBDatabase>((resolve,reject)=>{const req=indexedDB.open('self-atlas',1);req.onupgradeneeded=()=>req.result.createObjectStore('keyval');req.onsuccess=()=>resolve(req.result);req.onerror=()=>{opening=null;reject(new Error('浏览器无法保存数据，请允许网站存储后重试，并暂时不要关闭本页。'))}})}
export async function load<T>(key:string):Promise<T|undefined>{const db=await database();return new Promise((resolve,reject)=>{const req=db.transaction('keyval').objectStore('keyval').get(key);req.onsuccess=()=>resolve(req.result);req.onerror=()=>reject(req.error)})}
export async function save(key:string,value:any){const db=await database();return new Promise<void>((resolve,reject)=>{const tx=db.transaction('keyval','readwrite');tx.objectStore('keyval').put(JSON.parse(JSON.stringify(value)),key);tx.oncomplete=()=>{window.dispatchEvent(new Event('atlas-storage'));resolve()};tx.onerror=()=>reject(new Error('保存失败，请检查浏览器存储空间，并暂时不要关闭本页。'))})}
export async function remove(key:string){const db=await database();return new Promise<void>((resolve,reject)=>{const tx=db.transaction('keyval','readwrite');tx.objectStore('keyval').delete(key);tx.oncomplete=()=>{window.dispatchEvent(new Event('atlas-storage'));resolve()};tx.onerror=()=>reject(tx.error)})}
export async function keepReport(report:Report){const history=await load<Report[]>('reports')||[];await save('reports',[report,...history.filter(r=>r.id!==report.id)].slice(0,10))}
export async function fetchBank(mode:Mode,version?:string){
  try{const bank=await api<Bank>(version?`/api/questionnaires/${encodeURIComponent(version)}?mode=${mode}`:`/api/questionnaires/current?mode=${mode}`);await save(`bank:${bank.id}:${mode}`,bank);return bank}
  catch(e){if(version){const cached=await load<Bank>(`bank:${version}:${mode}`);if(cached)return cached}throw e}
}
export function download(name:string,blob:Blob){const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
