import {useEffect,useRef,useState} from 'react';
import {Check,ThumbsDown,ThumbsUp} from 'lucide-react';
export type FeedbackReason={id:string;label:string};
export type FeedbackTicket={ticket:string;expiresAt:number;reasons:FeedbackReason[]};

export function HelpFeedback({feedback,disabled,onExpired}:{feedback:FeedbackTicket;disabled:boolean;onExpired:(message:string)=>void}){
  const [negative,setNegative]=useState(false),[reason,setReason]=useState(''),[pending,setPending]=useState(false),[saved,setSaved]=useState(false),[error,setError]=useState(''),[expired,setExpired]=useState(false);
  const controller=useRef<AbortController|null>(null),busy=useRef(false),mounted=useRef(true);
  useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;controller.current?.abort();};},[]);
  async function submit(rating:'helpful'|'not_helpful'){
    if(disabled||busy.current||saved||expired||rating==='not_helpful'&&!reason)return;
    busy.current=true;setPending(true);setError('');const request=new AbortController();controller.current=request;
    const timer=setTimeout(()=>request.abort(),10000);
    try{
      const response=await fetch('/api/help/feedback',{method:'POST',credentials:'same-origin',headers:{'content-type':'application/json'},signal:request.signal,body:JSON.stringify({ticket:feedback.ticket,rating,...(rating==='not_helpful'?{reason}:{})})});
      if(request.signal.aborted)return;
      if(response.status===401){onExpired('Your session has expired. Sign in to Hub to continue.');throw Error('Sign in again to send feedback.');}
      if(response.status===410)setExpired(true);
      const data=await response.json();if(!response.ok||data.saved!==true)throw Error(data.error||'Feedback could not be saved. Please try again.');
      setSaved(true);
    }catch(e){if(mounted.current)setError(request.signal.aborted?'Feedback took too long. Please try again.':e instanceof Error?e.message:'Feedback could not be saved.');}
    finally{clearTimeout(timer);busy.current=false;if(mounted.current)setPending(false);}
  }
  if(saved)return <p className="help-feedback-saved" role="status"><Check size={16} aria-hidden="true"/>Thanks. Feedback saved.</p>;
  return <fieldset className="help-feedback" disabled={disabled||pending||expired}>
    <legend>Was this answer helpful?</legend>
    <div className="help-feedback-actions">
      <button type="button" className="help-secondary" onClick={()=>void submit('helpful')}><ThumbsUp size={15} aria-hidden="true"/>Helpful</button>
      <button type="button" className="help-secondary" aria-pressed={negative} onClick={()=>setNegative(v=>!v)}><ThumbsDown size={15} aria-hidden="true"/>Not helpful</button>
    </div>
    {negative&&<div className="help-feedback-reason"><label>What needs improving?<select aria-label="Feedback reason" value={reason} onChange={e=>setReason(e.target.value)}><option value="">Choose a reason</option>{feedback.reasons.map(r=><option key={r.id} value={r.id}>{r.label}</option>)}</select></label><button type="button" className="help-primary" disabled={!reason} onClick={()=>void submit('not_helpful')}>Send feedback</button></div>}
    <p className="help-feedback-privacy">Optional. Saves your rating, topic and selected reason for owner reports. Your question and conversation are not saved.</p>
    {pending&&<p role="status">Saving feedback…</p>}{error&&<p role="alert">{error}</p>}
  </fieldset>;
}

type ReportRow={app:string;articleId:string|null;title:string;version:string;status:string;helpful:number;notHelpful:number;votes:number;reasons:Record<string,number>};
type Report={scope:string;fromDay:string;throughDay:string;timeZone:string;totals:{votes:number;helpful:number;notHelpful:number;helpfulnessPercent:number|null;undocumentedFeedback:number};rows:ReportRow[];note:string};
export function HelpFeedbackReport({apps,reasons,canReadAll,onExpired,onClose}:{apps:{id:string;name:string}[];reasons:FeedbackReason[];canReadAll:boolean;onExpired:(message:string)=>void;onClose:()=>void}){
  const [scope,setScope]=useState('workspace'),[days,setDays]=useState('30'),[app,setApp]=useState('all'),[reload,setReload]=useState(0),[report,setReport]=useState<Report|null>(null),[error,setError]=useState(''),[loading,setLoading]=useState(true);
  const title=useRef<HTMLHeadingElement>(null);
  useEffect(()=>{title.current?.focus({preventScroll:true});title.current?.scrollIntoView?.({block:'nearest'});},[]);
  useEffect(()=>{
    const controller=new AbortController();setLoading(true);setError('');setReport(null);
    const timeout=setTimeout(()=>controller.abort(),10000);
    fetch('/api/help/feedback/report?'+new URLSearchParams({scope,days,app}),{credentials:'same-origin',signal:controller.signal}).then(async response=>{
      if(response.status===401)onExpired('Your session has expired. Sign in to Hub to continue.');
      const data=await response.json();if(!response.ok)throw Error(data.error||'The report could not load.');
      if(!data.totals||typeof data.totals.votes!=='number'||!Array.isArray(data.rows)||data.rows.some((r:ReportRow)=>typeof r.title!=='string'||typeof r.votes!=='number'||!r.reasons||typeof r.reasons!=='object'))throw Error('The report could not be read.');
      if(!controller.signal.aborted)setReport(data);
    }).catch(e=>{if(!controller.signal.aborted)setError(e instanceof Error?e.message:'The report could not load.');}).finally(()=>{clearTimeout(timeout);if(!controller.signal.aborted)setLoading(false);});
    controller.signal.addEventListener('abort',()=>{if(!controller.signal.reason?.message?.includes('unmounted')){setError('The report took too long. Try again.');setLoading(false);}});
    return()=>{clearTimeout(timeout);controller.abort(new DOMException('unmounted','AbortError'));};
  },[scope,days,app,reload]);
  return <section className="help-feedback-report" aria-labelledby="help-feedback-report-title">
    <div className="help-report-heading"><div><h2 id="help-feedback-report-title" ref={title} tabIndex={-1}>Help feedback report</h2><p>Find the guide topics that need attention. Reports contain no conversation text.</p></div><button type="button" className="help-secondary" onClick={onClose}>Close report</button></div>
    <div className="help-report-filters">
      <label>Scope<select aria-label="Feedback report scope" value={scope} onChange={e=>setScope(e.target.value)}><option value="workspace">This workspace</option>{canReadAll&&<option value="all">All workspaces, aggregated</option>}</select></label>
      <label>Period<select aria-label="Feedback report period" value={days} onChange={e=>setDays(e.target.value)}>{['7','30','90'].map(n=><option key={n} value={n}>Last {n} days</option>)}</select></label>
      <label>App<select aria-label="Feedback report app" value={app} onChange={e=>setApp(e.target.value)}><option value="all">All apps</option>{apps.map(a=><option key={a.id} value={a.id}>{a.name}</option>)}</select></label>
      <button type="button" className="help-secondary" disabled={loading} onClick={()=>setReload(n=>n+1)}>Refresh report</button>
    </div>
    {loading&&<p role="status">Loading feedback…</p>}{error&&<div className="help-report-error" role="alert"><p>{error}</p><button type="button" className="help-secondary" onClick={()=>setReload(n=>n+1)}>Try report again</button></div>}
    {report&&<>
      <p className="help-note">{report.fromDay} to {report.throughDay} · Saint Lucia time</p>
      <dl className="help-report-totals"><div><dt>Feedback submitted</dt><dd>{report.totals.votes}</dd></div><div><dt>Rated helpful</dt><dd>{report.totals.helpfulnessPercent===null?'No ratings':report.totals.helpfulnessPercent+'%'}</dd></div><div><dt>Feedback on missing answers</dt><dd>{report.totals.undocumentedFeedback}</dd></div></dl>
      {!report.rows.length?<p className="help-empty">No feedback for these filters yet. Optional ratings will appear here after customers submit them.</p>:<div className="help-report-table" tabIndex={0} role="region" aria-label="Feedback by help topic"><table><caption>Topics needing attention, ordered by Not helpful ratings</caption><thead><tr><th scope="col">Topic</th><th scope="col">Helpful</th><th scope="col">Not helpful</th><th scope="col">Reasons</th></tr></thead><tbody>{report.rows.map((r,i)=><tr key={i}><th scope="row"><strong>{r.title}</strong><small>{apps.find(a=>a.id===r.app)?.name||'App not specified'} · {r.status==='not_documented'?'No documented answer':r.status==='clarify'?'Clarification':'Guide answer'}</small><small>{r.version}</small></th><td>{r.helpful}</td><td>{r.notHelpful}</td><td>{Object.entries(r.reasons).filter(([,n])=>n>0).map(([id,n])=>`${reasons.find(r=>r.id===id)?.label||id}: ${n}`).join('; ')||'None selected'}</td></tr>)}</tbody></table></div>}
      <p className="help-feedback-privacy">{report.note}</p>
    </>}
  </section>;
}
