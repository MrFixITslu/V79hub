import {useEffect,useRef,useState} from 'react';
import {ArrowUpRight,Check,Copy} from 'lucide-react';

export type GuideAction='start'|'next'|'back'|'blocked'|'solved'|'retry'|'restart';
export type GuideStage='before'|'step'|'check'|'blocked'|'solved';
export type Guide={articleId:string;version:string;stage:GuideStage;index:number;total:number;heading:string;text:string;question:string;changed:boolean;link:{href:string;label:string};actions:{action:GuideAction;label:string}[]};
export type GuideRequest={articleId:string;version:string;action:GuideAction;stage?:GuideStage;index?:number};
export type SupportTurn={question:string;response:{answer:string;version:string;articles:{title:string;route:string;steps:string[]}[];guide?:Guide}};

export function GuidedSteps({guide,active,pending,expired,onAction,onSupport}:{guide:Guide;active:boolean;pending:boolean;expired:boolean;onAction:(label:string,request:GuideRequest)=>void;onSupport:()=>void}) {
  // Do not accept arbitrary URLs even if a response is malformed.
  const link=/^\/\?view=(?:overview|connections|team|security|billing)$/.test(guide.link.href)?guide.link:null;
  return <div className={`help-walkthrough help-walkthrough-${guide.stage}`}>
    <div className="help-step-heading"><strong>{guide.heading}</strong><span>Guided support</span></div>
    {guide.changed&&<p role="status" className="help-note">The guide has changed. Start from the current prerequisites before continuing.</p>}
    <div className="help-step-track" aria-label={`Guide progress: ${guide.heading}`}>
      {Array.from({length:guide.total},(_,i)=><span key={i} className={guide.stage==='solved'||guide.stage==='check'||guide.stage!=='before'&&i<=guide.index?'is-reached':''}/>)}</div>
    <p className="help-step-instruction">{guide.text}</p><p className="help-note">{guide.question}</p>
    {active&&<div className="help-step-actions">
      {guide.actions.map(({label,action})=><button type="button" key={action} disabled={pending||expired} className={action==='next'||action==='solved'?'help-primary':'help-secondary'} onClick={()=>onAction(label,{articleId:guide.articleId,version:guide.version,stage:guide.stage,index:guide.index,action})}>{label}</button>)}
      {guide.stage==='blocked'&&<button type="button" className="help-primary" disabled={pending||expired} onClick={onSupport}>Prepare support summary</button>}
    </div>}
    {active&&link&&<a className="help-app-link" href={link.href} target="_blank" rel="noreferrer">{link.label}<ArrowUpRight size={15} aria-hidden="true"/></a>}
  </div>;
}

export function redactSupportText(value:string) {
  return value
    .replace(/\b(password|passphrase|api[ _-]?key|access[ _-]?token|token|secret|mfa[ _-]?code|recovery[ _-]?code)\s*[:=]\s*[^\s,;]+/gi,'$1: [removed]')
    .replace(/\bBearer\s+[a-z0-9._~+\/-]+/gi,'Bearer [removed]')
    .replace(/\b(?:\d[ -]?){13,19}\b/g,'[number removed]');
}
export function supportEvidence(turns:SupportTurn[]) {
  const last=turns.at(-1)?.response;
  const article=last?.articles[0];
  const guide=last?.guide;
  const sameGuide=guide?turns.filter(t=>t.response.guide?.articleId===guide.articleId&&t.response.guide?.version===guide.version):[];
  const displayed=[...new Set(sameGuide.filter(t=>t.response.guide?.stage==='step').map(t=>t.response.guide!.index+1))];
  const initial=[...turns].reverse().find(t=>!t.response.guide)?.question||'';
  return {issue:initial,screen:article?.route||'',evidence:[
    article?`Guide: ${article.title}`:'',last?`Knowledge version: ${last.version}`:'',
    guide?`Guide steps displayed: ${displayed.join(', ')||'none'}. Displayed does not mean completed.`:'',
    guide?.stage==='blocked'?`Customer reported: ${guide.index===-1?'cannot meet the prerequisites':guide.index===guide.total?'result does not match':`blocked at step ${guide.index+1}`}.`:'',
    guide?.stage==='solved'?'Customer marked the issue as resolved; no live verification.':'',
  ].filter(Boolean).join('\n')};
}

export function SupportSummary({appName,screenName,turns,open,onOpen,onClose,onCopy,copied,disabled,onTiquet,tickets}:{tickets?:{enabled:boolean;app:string;onExpired:()=>void;onBusy:(busy:boolean)=>void};appName:string;screenName?:string;turns:SupportTurn[];open:boolean;onOpen:()=>void;onClose:()=>void;onCopy:(text:string)=>void;copied:boolean;disabled:boolean;onTiquet:()=>void}) {
  const [issue,setIssue]=useState(''),[screen,setScreen]=useState(''),[expected,setExpected]=useState(''),[actual,setActual]=useState(''),[evidence,setEvidence]=useState(''),[transcript,setTranscript]=useState(false),[time,setTime]=useState('');
  const title=useRef<HTMLHeadingElement>(null);
  const [kind,setKind]=useState<'unresolved'|'error'>('unresolved'),[reviewed,setReviewed]=useState(false),[sending,setSending]=useState(false),[submitError,setSubmitError]=useState(''),[receipt,setReceipt]=useState('');
  const [attempt,setAttempt]=useState<{idempotencyKey:string;app:string;kind:string;summary:string}|null>(null);
  const flight=useRef(false),request=useRef<AbortController|null>(null),mounted=useRef(true),receiptHeading=useRef<HTMLHeadingElement>(null);
  const locked=Boolean(attempt)&&!receipt;
  useEffect(()=>{mounted.current=true;return ()=>{mounted.current=false;request.current?.abort();};},[]);
  useEffect(()=>{
    const warn=(event:BeforeUnloadEvent)=>{event.preventDefault();event.returnValue='';};
    if(locked)window.addEventListener('beforeunload',warn);
    tickets?.onBusy(locked);
    return ()=>{window.removeEventListener('beforeunload',warn);tickets?.onBusy(false);};
  },[locked]);
  useEffect(()=>{if(receipt)receiptHeading.current?.focus();},[receipt]);
  const [snapshot,setSnapshot]=useState<SupportTurn[]>([]);
  useEffect(()=>{
    if(!open)return;
    const prepared=supportEvidence(turns);
    setSnapshot(turns);setIssue(prepared.issue);setScreen(prepared.screen||screenName||'');setExpected('');setActual('');setEvidence(prepared.evidence);setTranscript(false);
    setTime(new Intl.DateTimeFormat('en-GB',{timeZone:'America/St_Lucia',dateStyle:'medium',timeStyle:'short'}).format(new Date()));
    title.current?.focus({preventScroll:true});title.current?.scrollIntoView?.({block:'nearest'});
  },[open]); // Opening deliberately creates a fresh snapshot, never a live transcript.
  const summary=redactSupportText([
    `App: ${appName}`,`Screen: ${screen}`,`Time (Saint Lucia): ${time}`,`Issue: ${issue}`,
    `Expected result: ${expected}`,`Actual result / error: ${actual}`,evidence,
    transcript?`Conversation (customer chose to include):\n${snapshot.slice(-12).map(t=>`Customer: ${t.question}\nHelp: ${t.response.guide?`${t.response.guide.heading}: ${t.response.guide.text}`:t.response.answer}`).join('\n\n')}`:'Conversation: not included.',
    'Customer-reviewed support summary.',
  ].filter(Boolean).join('\n\n'));
  async function submitTicket(){
    if(flight.current||disabled||!tickets?.enabled||receipt||!attempt&&(!reviewed||issue.trim().length<5))return;
    flight.current=true;setSending(true);setSubmitError('');
    const controller=new AbortController();request.current=controller;
    const timer=setTimeout(()=>controller.abort(),15000);
    try{
      const payload=attempt||{idempotencyKey:crypto.randomUUID(),app:tickets.app,kind,summary};
      setAttempt(payload);
      const response=await fetch('/api/help/support/tickets',{method:'POST',credentials:'same-origin',headers:{'content-type':'application/json'},signal:controller.signal,body:JSON.stringify(payload)});
      const data=await response.json();if(!mounted.current)return;
      if(response.status===401){tickets.onExpired();throw Error('Your session has expired. Copy the summary, sign in to Hub and contact V79 support if receipt is uncertain.');}
      if(response.status===400){setAttempt(null);throw Error(data.error||'Review your request and try again.');}
      if(!response.ok)throw Error(data.error||'Receipt is uncertain. Keep this page open and retry the same request.');
      if(data.submitted!==true||typeof data.reference!=='string'||!/^HELP-[a-f0-9-]{36}$/i.test(data.reference)||data.priority!=='high')throw Error('Receipt could not be confirmed. Retry the same request.');
      setReceipt(data.reference);
    }catch(error){if(mounted.current)setSubmitError(controller.signal.aborted?'Receipt is uncertain. Keep this page open and retry the same request.':error instanceof Error?error.message:'Receipt could not be confirmed. Retry the same request.');}
    finally{clearTimeout(timer);flight.current=false;if(mounted.current)setSending(false);}
  }
  return <div className={`help-support ${open?'help-support-expanded':''}`}>
    <h3>Still need a hand?</h3><p>Report an error or an issue that the guide has not resolved.</p>
    {!open?<button type="button" className="help-secondary" onClick={onOpen} disabled={disabled}>Prepare support summary</button>:<div className="help-support-draft">
      <h3 ref={title} tabIndex={-1}>Review your support summary</h3>
      <p>{receipt?'This reviewed summary was submitted to V79 support.':'Review the details and remove private information. Nothing is sent until you submit. This draft stays in this page; leaving or reloading can lose it.'}</p>
      <fieldset disabled={disabled||locked||Boolean(receipt)} className="help-support-fields"><legend className="help-sr">Support issue details</legend>
      <label htmlFor="help-support-kind">Issue type<select id="help-support-kind" value={kind} onChange={e=>setKind(e.target.value as typeof kind)}><option value="unresolved">I am still having issues</option><option value="error">I found an error</option></select></label>
      <label htmlFor="help-support-issue">What went wrong?<textarea id="help-support-issue" rows={2} value={issue} maxLength={1200} onChange={e=>setIssue(e.target.value)} disabled={disabled||locked||Boolean(receipt)}/></label>
      <label htmlFor="help-support-screen">Screen<input id="help-support-screen" value={screen} maxLength={250} onChange={e=>setScreen(e.target.value)} disabled={disabled||locked||Boolean(receipt)}/></label>
      <label htmlFor="help-support-expected">Expected result<textarea id="help-support-expected" rows={2} value={expected} maxLength={1000} onChange={e=>setExpected(e.target.value)} disabled={disabled||locked||Boolean(receipt)}/></label>
      <label htmlFor="help-support-actual">Actual result or error<textarea id="help-support-actual" rows={2} value={actual} maxLength={1000} onChange={e=>setActual(e.target.value)} disabled={disabled||locked||Boolean(receipt)}/></label>
      <label htmlFor="help-support-evidence">Guide steps and outcome<textarea id="help-support-evidence" rows={4} value={evidence} maxLength={2000} onChange={e=>setEvidence(e.target.value)} disabled={disabled||locked||Boolean(receipt)}/></label>
      <label className="help-transcript"><input type="checkbox" checked={transcript} onChange={e=>setTranscript(e.target.checked)} disabled={disabled}/>Include the recent conversation</label>
      </fieldset>
      <p>Obvious credential labels and long card-like numbers are removed from the preview. Review it yourself; automatic removal cannot find every private detail.</p>
      <label htmlFor="help-support-preview">Reviewed summary<textarea id="help-support-preview" rows={9} value={summary} readOnly/></label>
      <button type="button" className="help-secondary" disabled={sending} onClick={()=>onCopy(summary)}>{copied?<Check size={15}/>:<Copy size={15}/>} {copied?'Summary copied':'Copy reviewed summary'}</button>
      {receipt?<div className="help-ticket-receipt" role="status"><h3 ref={receiptHeading} tabIndex={-1}>Ticket submitted to V79 support</h3><p>Priority: <strong>High</strong></p><p>Reference: <strong>{receipt}</strong></p><p>Your request is in the V79 support queue. Keep this reference when following up.</p></div>:tickets?.enabled?<div className="help-ticket-submit">
        <p>Your reviewed summary, Hub name, contact email and workspace will be shared with V79 support. Priority is High. A Tiquet subscription is not required.</p>
        <label className="help-transcript"><input type="checkbox" checked={reviewed} onChange={e=>setReviewed(e.target.checked)} disabled={disabled||locked}/>I have reviewed the summary and agree to share it with V79 support.</label>
        {issue.trim().length<5&&<p>Describe what went wrong before submitting.</p>}
        {submitError&&<p role="alert">{submitError}</p>}
        <button type="button" className="help-primary" disabled={disabled||sending||!attempt&&(!reviewed||issue.trim().length<5)} onClick={()=>void submitTicket()}>{sending?'Submitting ticket…':attempt?'Retry the same request':'Submit high-priority ticket'}</button>
        {locked&&<p role="status">Keep this page open until receipt is confirmed. Editing and closing are paused so retries cannot create a different request.</p>}
      </div>:<p>Ticket submission is currently unavailable. Copy your reviewed summary and contact V79 support below.</p>}
      <button type="button" onClick={onClose} disabled={sending||locked}>Close draft</button>
    </div>}
    <a href="https://v79sl.com/contact" target="_blank" rel="noreferrer">Contact V79 support<ArrowUpRight size={14} aria-hidden="true"/></a>
    {!open?<button type="button" disabled={disabled} onClick={onTiquet}>How to create a Tiquet service request</button>:<p>Copy your summary before closing this draft. You can then open the Tiquet service-request instructions.</p>}
  </div>;
}
