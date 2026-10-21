import { useEffect, useRef, useState } from 'react';

type Mail = {id:string;threadId:string;subject:string;from:string};
type Thread = {id:string;partial:boolean;messages:{id:string;threadId:string;from:string;replyTo:string;subject:string;text:string;date:string}[]};
type Appointment = {id:string;etag:string;summary:string;start:{dateTime?:string;date?:string};end:{dateTime?:string;date?:string};attendees:{email:string}[];organizer:string;recurring:boolean};
type GoogleJob = {id:string;operation:string;system:string;summary:string;payload:Record<string,unknown>;digest:string;revision:number;status:string;approval?:{expiresAt:string}|null};
const googleActions:Record<string,string>={create_email_draft:'Save draft',create_calendar_event:'Create appointment',update_calendar_event:'Update appointment',delete_calendar_event:'Cancel appointment'};
const jobLabel=(job:GoogleJob)=>({pending:'Ready for your review',approved:'Approved — ready to finish',running:'In progress — do not retry',succeeded:job.operation==='create_email_draft'?'Draft saved — email not sent':'Appointment action completed',rejected:'Rejected',failed:'Failed — review before creating another action',uncertain:'Outcome needs checking — do not retry'}[job.status]||job.status);
const approvalExpired=(job:GoogleJob)=>job.status==='approved'&&!(Date.parse(job.approval?.expiresAt||'')>Date.now());
const owner='vision79slu@gmail.com';
const format=(value:string)=>new Intl.DateTimeFormat('en-LC',{timeZone:'America/St_Lucia',dateStyle:'medium',timeStyle:'short'}).format(new Date(value));
const localInput=(value:string)=>new Date(new Date(value).getTime()-4*3600000).toISOString().slice(0,16);
const utc=(value:string)=>new Date(value+':00-04:00').toISOString();
async function api(route:string,body?:unknown) {
  const response=await fetch(route,{credentials:'same-origin',cache:'no-store',...(body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})});
  const result=await response.json();
  if(!response.ok) throw Object.assign(new Error(response.status===403?'Sign in with fresh owner MFA to continue.':result.error||'Google connection unavailable'),{status:response.status});
  return result;
}

export function GoogleWorkforcePanel() {
  const [status,setStatus]=useState<{enabled:boolean;connected:boolean}|null>(null);
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
  const [mails,setMails]=useState<Mail[]>([]),[thread,setThread]=useState<Thread|null>(null);
  const [mailNext,setMailNext]=useState(''),[eventNext,setEventNext]=useState('');
  const [query,setQuery]=useState('in:inbox newer_than:7d'),[recipient,setRecipient]=useState(''),[reply,setReply]=useState('');
  const [appointments,setAppointments]=useState<Appointment[]>([]),[selected,setSelected]=useState<Appointment|null>(null);
  const [summary,setSummary]=useState(''),[start,setStart]=useState(''),[end,setEnd]=useState(''),[attendees,setAttendees]=useState('');
  const [rangeStart,setRangeStart]=useState(''),[rangeEnd,setRangeEnd]=useState('');
  const review=useRef<HTMLDivElement>(null);
  const retry=useRef<{signature:string;key:string;jobId?:string}|null>(null),mutating=useRef(false),serial=useRef(0);
  const [jobs,setJobs]=useState<GoogleJob[]>([]),[queueReady,setQueueReady]=useState(false),[queuePaused,setQueuePaused]=useState(false),[focused,setFocused]=useState('');
  const refreshJobs=async()=>{
    const version=++serial.current;
    try{
      const data=await api('/api/agent/work-actions');
      if(data.mode!=='owner-approved-actions'||!Array.isArray(data.jobs)||data.jobs.length>200||!data.jobs.every((j:GoogleJob)=>j&&typeof j.id==='string'&&typeof j.digest==='string'&&Number.isInteger(j.revision)&&typeof j.status==='string'&&typeof j.operation==='string'&&j.payload&&typeof j.payload==='object'))throw new Error('Action status unavailable. Refresh before continuing.');
      if(version===serial.current){setJobs(data.jobs.filter((j:GoogleJob)=>googleActions[j.operation]));setQueueReady(data.enabled===true);setQueuePaused(data.paused===true)}
      return data as {jobs:GoogleJob[];enabled:boolean;paused:boolean};
    }catch(e){if(version===serial.current){setJobs([]);setQueueReady(false)}throw e}
  };
  useEffect(()=>{
    if(!status?.connected)return;
    const timer=window.setInterval(()=>{if(!document.hidden&&!mutating.current)void refreshJobs().catch(()=>{})},15000);
    return ()=>{window.clearInterval(timer);serial.current++};
  },[status?.connected]);
  const work=async(fn:()=>Promise<void>)=>{
    if(mutating.current)return;mutating.current=true;setBusy(true);setError('');setNotice('');
    try{await fn()}catch(e){
      setError(e instanceof Error?e.message:'Request unavailable. Refresh action status before trying again.');
      if((e as {status?:number})?.status===403){serial.current++;setJobs([]);setQueueReady(false);setStatus(null)}
      else await refreshJobs().catch(()=>{});
    }finally{mutating.current=false;setBusy(false)}
  };
  const loadInbox=async(pageToken='')=>{
    const result=await api('/api/agent/google/inbox?'+new URLSearchParams({query,...(pageToken?{pageToken}:{})}));
    setMails(result.messages??[]);setMailNext(result.nextPageToken??'');setThread(null);
  };
  const loadAppointments=async(pageToken='')=>{
    const result=await api('/api/agent/google/appointments?'+new URLSearchParams({start:utc(rangeStart),end:utc(rangeEnd),...(pageToken?{pageToken}:{})}));
    setAppointments(result.items??[]);setEventNext(result.nextPageToken??'');
  };
  const queue=async(operation:string,payload:unknown,title:string)=>{
    const fresh=await refreshJobs();
    if(!fresh.enabled||fresh.paused)throw new Error('The action queue is unavailable or paused. Your text has not been submitted.');
    const proposal={operation,system:operation==='create_email_draft'?'gmail':'calendar',summary:title,payload};
    const signature=JSON.stringify(proposal);
    if(retry.current?.signature!==signature)retry.current={signature,key:'google-'+crypto.randomUUID()};
    const existing=retry.current.jobId;
    if(existing){setFocused(existing);await refreshJobs();return}
    const result=await api('/api/agent/work-actions',{...proposal,idempotencyKey:retry.current.key});
    if(!result.job?.id||result.job.operation!==operation)throw new Error('Proposal status needs checking. Refresh action status before trying again.');
    retry.current.jobId=result.job.id;setFocused(result.job.id);await refreshJobs();
    review.current?.focus({preventScroll:true});review.current?.scrollIntoView?.({behavior:'smooth',block:'nearest'});
    setNotice('Review the saved details below, then approve and finish here. Nothing has been executed yet.');
  };
  const finish=async(job:GoogleJob)=>{
    const fresh=await refreshJobs(),current=fresh.jobs.find(j=>j.id===job.id);
    if(!current||current.digest!==job.digest||current.revision!==job.revision||current.status!==job.status)throw new Error('This action changed. Review its refreshed details before continuing.');
    if(!fresh.enabled||fresh.paused)throw new Error('The action queue is unavailable or paused. No action was executed.');
    if(approvalExpired(current))throw new Error('Approval expired. Prepare a new proposal and review it again.');
    if(current.status==='pending'){
      const decision=await api('/api/agent/work-actions/'+encodeURIComponent(current.id)+'/decision',{decision:'approve',expectedRevision:current.revision,digest:current.digest});
      if(decision.job?.id!==current.id||decision.job?.digest!==current.digest||decision.job?.status!=='approved')throw new Error('Approval status needs checking. Refresh before continuing.');
    }else if(current.status!=='approved')throw new Error('This action cannot be executed. Check its current status.');
    const result=await api('/api/agent/google/run-once',{jobId:current.id});
    await refreshJobs();
    setNotice(result.status==='succeeded'?(current.operation==='create_email_draft'?'Draft saved in Gmail. Email was not sent.':'Appointment action completed. Check your Google Calendar.'):result.status==='idle'?'This action is no longer eligible. Its status has been refreshed.':'Outcome needs checking. Review the status below before taking another action.');
  };
  const draftReason=busy?'Another request is in progress.':!queueReady?'Refresh action status before preparing a proposal.':queuePaused?'The queue is paused. Resume it in Tasks & approvals before preparing an action.':!thread?'Open a message to prepare a reply.':thread.partial?'This thread is incomplete. Open another plain-text message or review it in Gmail.':!thread.messages.length?'This thread has no readable messages.':!recipient.trim()?'Enter the verified recipient email.':!reply.trim()?'Write the reply you want saved.':'';
  const choose=(event:Appointment)=>{
    setSelected(event);setSummary(event.summary);setStart(event.start.dateTime?localInput(event.start.dateTime):'');setEnd(event.end.dateTime?localInput(event.end.dateTime):'');setAttendees(event.attendees.map(a=>a.email).join(', '));
  };
  const eventPayload=()=>({summary,start:utc(start),end:utc(end),attendees:attendees.split(',').map(s=>s.trim()).filter(Boolean)});
  const field='mt-1 block min-h-11 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100';
  const button='min-h-11 rounded-lg border border-slate-600 px-3 py-2 disabled:opacity-40 hover:border-cyan-400';
  return <section aria-label="Email and appointments" className="space-y-5 rounded-xl border border-slate-700 bg-slate-900 p-4 text-sm text-slate-100">
    <div><h2 className="text-xl font-semibold">Email & appointments</h2><p className="mt-1 text-slate-400">{owner} · Saint Lucia time. You review and send every email.</p></div>
    <button className={button} disabled={busy} onClick={()=>void work(async()=>{const result=await api('/api/agent/google/status');setStatus(result);if(result.connected)await refreshJobs()})}>Check Google connection</button>
    {status&&!status.connected&&<p role="status">{status.enabled?'Google authorization needs attention.':'Google setup is pending. Ask your administrator to complete authorization.'}</p>}
    {error&&<p role="alert" className="text-red-300">{error}</p>}{notice&&<p role="status" className="text-cyan-200">{notice}</p>}
    {status?.connected&&<>
      <ol aria-label="Google action workflow" className="grid gap-2 sm:grid-cols-3">{['1. Prepare','2. Review & approve here','3. Confirm the result'].map(step=><li key={step} className="rounded-lg border border-slate-700 p-3">{step}</li>)}</ol>
      <div ref={review} tabIndex={-1} className="space-y-3" aria-label="Google action reviews">
        <div className="flex flex-wrap items-center justify-between gap-2"><h3 className="text-lg font-semibold">Review & finish</h3><button className={button} disabled={busy} onClick={()=>void work(async()=>{await refreshJobs()})}>Refresh action status</button></div>
        {!queueReady&&<p role="status">Action status is unverified or actions are disabled. Refresh status before continuing.</p>}
        {queuePaused&&<p role="status">The queue is paused. Approval and execution are unavailable here.</p>}
        {!jobs.length&&queueReady&&<p className="text-slate-400">Prepare a reply or appointment below. Its review and result will appear here.</p>}
        {[...jobs].reverse().sort((a,b)=>Number(b.id===focused)-Number(a.id===focused)).map(job=><article key={job.id} aria-label={job.summary} className="space-y-3 rounded-lg border border-slate-600 p-4">
          <h4 className="font-semibold">{job.summary}</h4><p role="status">{approvalExpired(job)?'Approval expired — prepare a new proposal':jobLabel(job)}</p>
          {job.operation==='create_email_draft'?<div className="space-y-2"><p><strong>To:</strong> {String(job.payload.to||'')}</p><p><strong>Subject:</strong> {String(job.payload.subject||'')}</p><p className="whitespace-pre-wrap break-words">{String(job.payload.body||'')}</p><p className="text-slate-400">Saves a Gmail draft only. You send it yourself in Gmail.</p></div>:<div className="space-y-2"><p>{String(job.payload.summary||job.summary)}</p>{typeof job.payload.start==='string'&&<p>Starts: {format(job.payload.start)}</p>}{typeof job.payload.end==='string'&&<p>Ends: {format(job.payload.end)}</p>}<p>Attendees: {Array.isArray(job.payload.attendees)&&job.payload.attendees.length?job.payload.attendees.join(', '):'None'}</p><p className="text-amber-200">Creating, changing or cancelling an appointment can notify its attendees.</p></div>}
          {['pending','approved'].includes(job.status)&&!approvalExpired(job)&&<div className="flex flex-wrap gap-2"><button className={button} disabled={busy||!queueReady||queuePaused} onClick={()=>void work(()=>finish(job))}>{job.status==='pending'?'Approve & ':''}{googleActions[job.operation].toLowerCase()}</button>{job.status==='pending'&&<button className={button} disabled={busy||!queueReady} onClick={()=>void work(async()=>{await api('/api/agent/work-actions/'+encodeURIComponent(job.id)+'/decision',{decision:'reject',expectedRevision:job.revision,digest:job.digest});await refreshJobs()})}>Reject</button>}</div>}
        </article>)}
      </div>
      <div className="space-y-3 border-t border-slate-700 pt-4"><h3 className="text-lg font-semibold">Inbox & reply drafts</h3>
        <label>Gmail search<input className={field} value={query} onChange={e=>setQuery(e.target.value)} /></label>
        <button className={button} disabled={busy} onClick={()=>void work(()=>loadInbox())}>Review inbox</button>
        {mails.map(mail=><button key={mail.id} className="block w-full rounded-lg border border-slate-700 p-3 text-left" disabled={busy} onClick={()=>void work(async()=>{
          const data=await api('/api/agent/google/threads/'+encodeURIComponent(mail.threadId));setThread(data);setRecipient('');setReply('');
        })}><strong>{mail.subject||'(No subject)'}</strong><span className="mt-1 block text-slate-400">{mail.from}</span></button>)}
        {mailNext&&<button className={button} disabled={busy} onClick={()=>void work(()=>loadInbox(mailNext))}>Next inbox page</button>}
        {thread&&<div className="space-y-3 rounded-lg border border-slate-700 p-3">
          {thread.messages.map(message=><div key={message.id} className="border-b border-slate-700 pb-3"><p className="font-medium">{message.from}</p>{message.replyTo&&<p className="text-amber-200">Reply-To: {message.replyTo} — verify the recipient below.</p>}<p className="mt-2 whitespace-pre-wrap break-words text-slate-300">{message.text||'Plain text is unavailable. Review this message in Gmail.'}</p></div>)}
          {thread.partial&&<p className="text-amber-200">This thread is incomplete here. Review it in Gmail before preparing a response.</p>}
          <label>Verified recipient email<input type="email" className={field} value={recipient} onChange={e=>setRecipient(e.target.value)} /></label>
          <label>Reply for your review<textarea rows={6} className={field} value={reply} onChange={e=>setReply(e.target.value)} /></label>
          <button className={button} disabled={Boolean(draftReason)} aria-describedby="gmail-draft-help" onClick={()=>void work(async()=>{
            const message=thread.messages.at(-1)!;
            await queue('create_email_draft',{threadId:thread.id,messageId:message.id,to:recipient.trim(),subject:(message.subject.startsWith('Re:')?message.subject:'Re: '+message.subject).slice(0,200),body:reply.trim()},('Gmail draft: '+message.subject).slice(0,180));
          })}>Review draft</button><p id="gmail-draft-help" role="status" className="text-slate-400">{draftReason||'Next: review the saved recipient and reply above, then approve and save.'}</p>
        </div>}
      </div>
      <div className="space-y-3 border-t border-slate-700 pt-4"><h3 className="text-lg font-semibold">Appointments</h3>
        <p className="text-slate-400">Primary calendar only. Invitations, changes and cancellations can notify attendees.</p>
        <div className="grid gap-3 sm:grid-cols-2"><label>Agenda from<input type="datetime-local" className={field} value={rangeStart} onChange={e=>setRangeStart(e.target.value)}/></label><label>Agenda until<input type="datetime-local" className={field} value={rangeEnd} onChange={e=>setRangeEnd(e.target.value)}/></label></div>
        <button className={button} disabled={busy||!rangeStart||!rangeEnd} onClick={()=>void work(()=>loadAppointments())}>Review appointments</button>
        {appointments.map(event=><button key={event.id} disabled={busy} className="block w-full rounded-lg border border-slate-700 p-3 text-left" onClick={()=>choose(event)}><strong>{event.summary||'(Untitled appointment)'}</strong><span className="block text-slate-400">{event.start.dateTime?format(event.start.dateTime):event.start.date} {event.recurring?'· Recurring':''}</span></button>)}
        {eventNext&&<button className={button} disabled={busy} onClick={()=>void work(()=>loadAppointments(eventNext))}>Next agenda page</button>}
        <button className={button} disabled={busy} onClick={()=>{setSelected(null);setSummary('');setStart('');setEnd('');setAttendees('')}}>New appointment</button>
        <label>Appointment title<input className={field} value={summary} onChange={e=>setSummary(e.target.value)}/></label>
        <div className="grid gap-3 sm:grid-cols-2"><label>Starts · Saint Lucia<input type="datetime-local" className={field} value={start} onChange={e=>setStart(e.target.value)}/></label><label>Ends · Saint Lucia<input type="datetime-local" className={field} value={end} onChange={e=>setEnd(e.target.value)}/></label></div>
        <label>Verified attendee emails, separated by commas<input className={field} value={attendees} onChange={e=>setAttendees(e.target.value)}/></label>
        {selected&&(selected.recurring||selected.organizer!==owner)&&<p className="text-amber-200">This event requires manual management in Google Calendar.</p>}
        <div className="flex flex-wrap gap-3"><button className={button} disabled={busy||!summary||!start||!end||Boolean(selected&&(selected.recurring||selected.organizer!==owner))} onClick={()=>void work(()=>queue(selected?'update_calendar_event':'create_calendar_event',selected?{...eventPayload(),eventId:selected.id,etag:selected.etag}:eventPayload(),selected?'Review appointment rescheduling':'Review new appointment'))}>Review {selected?'change':'appointment'}</button>
        {selected&&<button className={button} disabled={busy||selected.recurring||selected.organizer!==owner} onClick={()=>{
          if(window.confirm('Queue cancellation of '+selected.summary+'? Approved cancellation can notify its attendees.')) void work(()=>queue('delete_calendar_event',{eventId:selected.id,etag:selected.etag},('Cancel appointment: '+selected.summary).slice(0,180)));
        }}>Queue cancellation</button>}</div>
      </div>

    </>}
  </section>;
}

