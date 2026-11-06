import fs from 'node:fs/promises';
import path from 'node:path';
import {constants} from 'node:fs';
import {createHmac,randomBytes,randomUUID,timingSafeEqual,createHash} from 'node:crypto';
import {HELP_APPS,knowledge,findArticle} from './customer-help.mjs';

export const FEEDBACK_REASONS=Object.freeze([
  {id:'unclear',label:'Hard to understand'},
  {id:'wrong_topic',label:'Wrong topic'},
  {id:'outdated',label:'Does not match the current screen'},
  {id:'missing_steps',label:'Missing a step'},
  {id:'not_documented',label:'My question is not covered'},
  {id:'technical_problem',label:'Help did not work correctly'},
]);
const apps=new Set(HELP_APPS.map(a=>a.id));
const statuses=new Set(['answered','clarify','not_documented']);
const reasons=new Set(FEEDBACK_REASONS.map(r=>r.id));
const TTL=2*60*60*1000,MAX_BYTES=25*1024*1024;
const day=now=>new Intl.DateTimeFormat('en-CA',{timeZone:'America/St_Lucia',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date(now));
const canonical=value=>JSON.stringify(value,(_key,v)=>v&&typeof v==='object'&&!Array.isArray(v)?Object.fromEntries(Object.keys(v).sort().map(k=>[k,v[k]])):v);
export class HelpFeedbackError extends Error {constructor(code,message){super(message);this.code=code;}}
export function validateFeedback(body){
  if(!body||typeof body!=='object'||Array.isArray(body)||Object.keys(body).some(k=>!['ticket','rating','reason'].includes(k)))return 'Use a feedback ticket, rating and fixed reason only.';
  if(typeof body.ticket!=='string'||body.ticket.length<50||body.ticket.length>1600)return 'This feedback ticket is unavailable. Ask a new question.';
  if(!['helpful','not_helpful'].includes(body.rating))return 'Choose Helpful or Not helpful.';
  if(body.rating==='not_helpful'&&!reasons.has(body.reason)||body.rating==='helpful'&&body.reason!==undefined)return 'Choose a supported feedback reason.';
  return null;
}
export function reportFilters(query={}){
  if(!query||Object.keys(query).some(k=>!['scope','days','app'].includes(k))||Object.values(query).some(v=>typeof v!=='string'))throw new HelpFeedbackError('INVALID','Use supported report filters.');
  const scope=query.scope||'workspace',days=query.days||'30',app=query.app||'all';
  if(!['workspace','all'].includes(scope)||!['7','30','90'].includes(days)||app!=='all'&&!apps.has(app))throw new HelpFeedbackError('INVALID','Choose a supported scope, app and period.');
  return {scope,days:Number(days),app};
}
export function createHelpFeedback({file='',secret='',clock=Date.now,beginWrite=()=>()=>{}}={}){
  const enabled=typeof secret==='string'&&secret.length>=24&&typeof file==='string'&&file.length>0;
  const mac=value=>createHmac('sha256',secret).update('v79-help-feedback:v1:'+value).digest('hex');
  const equal=(a,b)=>typeof a==='string'&&typeof b==='string'&&a.length===64&&b.length===64&&/^[a-f0-9]+$/.test(a)&&timingSafeEqual(Buffer.from(a),Buffer.from(b));
  const scope=actor=>mac('actor:'+JSON.stringify([actor.organizationId,actor.userId]));
  const empty=()=>({version:1,buckets:[],receipts:[]});
  function issue(answer,actor){
    if(!enabled||!statuses.has(answer.status)||answer.version!==knowledge.version)return null;
    const article=findArticle(answer.articles?.[0]?.id);
    const payload={n:randomBytes(18).toString('base64url'),e:clock()+TTL,s:scope(actor),a:article?.app||(apps.has(answer.app)?answer.app:'unknown'),i:article?.id||null,v:knowledge.version,t:answer.status};
    const encoded=Buffer.from(JSON.stringify(payload)).toString('base64url');
    return {ticket:encoded+'.'+mac('ticket:'+encoded),expiresAt:payload.e,reasons:FEEDBACK_REASONS};
  }
  function verify(ticket,actor){
    const parts=ticket.split('.');
    if(parts.length!==2||!equal(parts[1],mac('ticket:'+parts[0])))throw new HelpFeedbackError('INVALID','This feedback ticket is invalid. Ask a new question.');
    let payload;try{payload=JSON.parse(Buffer.from(parts[0],'base64url').toString('utf8'));}catch{throw new HelpFeedbackError('INVALID','This feedback ticket is invalid.');}
    if(!payload||payload.s!==scope(actor))throw new HelpFeedbackError('FORBIDDEN','This feedback belongs to a different signed-in session.');
    if(!Number.isSafeInteger(payload.e)||payload.e<=clock())throw new HelpFeedbackError('EXPIRED','Feedback has expired. Ask a new question to leave feedback.');
    if(!statuses.has(payload.t)||!apps.has(payload.a)&&payload.a!=='unknown'||payload.i!==null&&!findArticle(payload.i)||typeof payload.v!=='string'||payload.v.length>100)throw new HelpFeedbackError('INVALID','This feedback ticket is invalid.');
    return payload;
  }
  function prune(state){
    const oldest=day(clock()-89*86400000);
    state.buckets=state.buckets.filter(r=>r.day>=oldest);
    state.receipts=state.receipts.filter(r=>r.expiresAt>clock());
    return state;
  }
  async function read(){
    if(!enabled)throw new HelpFeedbackError('UNAVAILABLE','Feedback is not configured.');
    let handle;
    try{
      handle=await fs.open(file,constants.O_RDONLY|constants.O_NOFOLLOW);const stat=await handle.stat();
      if(!stat.isFile()||stat.size>MAX_BYTES||(stat.mode&0o077))throw Error('Invalid ledger metadata');
      const envelope=JSON.parse(await handle.readFile('utf8')),state=envelope.state;
      if(!state||state.version!==1||!Array.isArray(state.buckets)||!Array.isArray(state.receipts)||state.buckets.length>50000||state.receipts.length>50000||!equal(envelope.mac,mac('state:'+canonical(state))))throw Error('Invalid ledger integrity');
      return prune(state);
    }catch(e){if(e.code==='ENOENT')return empty();throw new HelpFeedbackError('UNAVAILABLE','Feedback storage is unavailable. Please try again later.');}
    finally{await handle?.close();}
  }
  async function transact(mutator){
    if(!enabled)throw new HelpFeedbackError('UNAVAILABLE','Feedback is not configured.');
    await fs.mkdir(path.dirname(file),{recursive:true,mode:0o700});let locked=false,temp,endWrite;
    for(let n=0;n<20;n++){
      try{await fs.mkdir(file+'.lock',{mode:0o700});locked=true;break;}
      catch(e){if(e.code!=='EEXIST')throw e;await new Promise(r=>setTimeout(r,25));}
    }
    if(!locked)throw new HelpFeedbackError('UNAVAILABLE','Feedback is busy. Please try again shortly.');
    try{
      endWrite=beginWrite();const state=await read(),result=mutator(state);
      if(state.buckets.length>50000||state.receipts.length>50000)throw new HelpFeedbackError('UNAVAILABLE','Feedback storage has reached its limit.');
      const content=JSON.stringify({state,mac:mac('state:'+canonical(state))});
      if(Buffer.byteLength(content)>MAX_BYTES)throw new HelpFeedbackError('UNAVAILABLE','Feedback storage has reached its limit.');
      temp=file+'.'+randomUUID()+'.tmp';const handle=await fs.open(temp,constants.O_CREAT|constants.O_EXCL|constants.O_WRONLY|constants.O_NOFOLLOW,0o600);
      try{await handle.writeFile(content);await handle.sync();}finally{await handle.close();}
      await fs.rename(temp,file);temp=null;const directory=await fs.open(path.dirname(file),'r');try{await directory.sync();}finally{await directory.close();}
      return result;
    }finally{try{if(temp)await fs.unlink(temp).catch(()=>{});await fs.rmdir(file+'.lock');}finally{endWrite?.();}}
  }
  async function vote(body,actor){
    if(!enabled)throw new HelpFeedbackError('UNAVAILABLE','Feedback is not configured.');
    const invalid=validateFeedback(body);if(invalid)throw new HelpFeedbackError('INVALID',invalid);
    const ticket=verify(body.ticket,actor),digest=createHash('sha256').update(body.ticket).digest('hex');
    return transact(state=>{
      if(state.receipts.some(r=>r.digest===digest))return {saved:true,duplicate:true};
      const key={day:day(clock()),organizationId:actor.organizationId,app:ticket.a,articleId:ticket.i,version:ticket.v,status:ticket.t};
      let bucket=state.buckets.find(r=>Object.entries(key).every(([k,v])=>r[k]===v));
      if(!bucket){bucket={...key,helpful:0,notHelpful:0,reasons:Object.fromEntries(FEEDBACK_REASONS.map(r=>[r.id,0]))};state.buckets.push(bucket);}
      if(body.rating==='helpful')bucket.helpful++;else{bucket.notHelpful++;bucket.reasons[body.reason]++;}
      state.receipts.push({digest,expiresAt:ticket.e});return {saved:true,duplicate:false};
    });
  }
  async function report(actor,filters){
    const state=await read(),fromDay=day(clock()-(filters.days-1)*86400000),throughDay=day(clock());
    const selected=state.buckets.filter(r=>r.day>=fromDay&&r.day<=throughDay&&(filters.scope==='all'||r.organizationId===actor.organizationId)&&(filters.app==='all'||r.app===filters.app));
    const groups=new Map();
    for(const r of selected){
      const key=JSON.stringify([r.app,r.articleId,r.version,r.status]);let row=groups.get(key);
      if(!row){row={app:r.app,articleId:r.articleId,title:findArticle(r.articleId)?.title||'General or undocumented help',version:r.version,status:r.status,helpful:0,notHelpful:0,reasons:Object.fromEntries(FEEDBACK_REASONS.map(r=>[r.id,0]))};groups.set(key,row);}
      row.helpful+=r.helpful;row.notHelpful+=r.notHelpful;for(const k of reasons)row.reasons[k]+=r.reasons[k];
    }
    const rows=[...groups.values()].map(r=>({...r,votes:r.helpful+r.notHelpful})).sort((a,b)=>b.notHelpful-a.notHelpful||b.votes-a.votes||a.title.localeCompare(b.title));
    const helpful=rows.reduce((n,r)=>n+r.helpful,0),notHelpful=rows.reduce((n,r)=>n+r.notHelpful,0),votes=helpful+notHelpful;
    return {scope:filters.scope,app:filters.app,days:filters.days,fromDay,throughDay,timeZone:'America/St_Lucia',totals:{votes,helpful,notHelpful,helpfulnessPercent:votes?Math.round(helpful/votes*100):null,undocumentedFeedback:rows.filter(r=>r.status==='not_documented').reduce((n,r)=>n+r.votes,0)},rows,
      note:'Counts reflect optional feedback submissions, not all questions or unique customers. No conversation text is collected.'};
  }
  return {enabled,issue,vote,report};
}
