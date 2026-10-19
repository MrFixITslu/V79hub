import { useState } from 'react';

type Mail = {id:string;threadId:string;subject:string;from:string};
type Thread = {id:string;partial:boolean;messages:{id:string;threadId:string;from:string;replyTo:string;subject:string;text:string;date:string}[]};
type Appointment = {id:string;etag:string;summary:string;start:{dateTime?:string;date?:string};end:{dateTime?:string;date?:string};attendees:{email:string}[];organizer:string;recurring:boolean};
const owner='vision79slu@gmail.com';
const format=(value:string)=>new Intl.DateTimeFormat('en-LC',{timeZone:'America/St_Lucia',dateStyle:'medium',timeStyle:'short'}).format(new Date(value));
const localInput=(value:string)=>new Date(new Date(value).getTime()-4*3600000).toISOString().slice(0,16);
const utc=(value:string)=>new Date(value+':00-04:00').toISOString();
async function api(route:string,body?:unknown) {
  const response=await fetch(route,{credentials:'same-origin',cache:'no-store',...(body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})});
  const result=await response.json();
  if(!response.ok) throw new Error(response.status===403?'Sign in with fresh owner MFA to continue.':result.error||'Google connection unavailable');
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
  const [retry,setRetry]=useState<{signature:string;key:string}|null>(null);
  const work=async(fn:()=>Promise<void>)=>{if(busy)return;setBusy(true);setError('');setNotice('');try{await fn()}catch(e){setError(e instanceof Error?e.message:'Request unavailable')}finally{setBusy(false)}};
  const loadInbox=async(pageToken='')=>{
    const result=await api('/api/agent/google/inbox?'+new URLSearchParams({query,...(pageToken?{pageToken}:{})}));
    setMails(result.messages??[]);setMailNext(result.nextPageToken??'');setThread(null);
  };
  const loadAppointments=async(pageToken='')=>{
    const result=await api('/api/agent/google/appointments?'+new URLSearchParams({start:utc(rangeStart),end:utc(rangeEnd),...(pageToken?{pageToken}:{})}));
    setAppointments(result.items??[]);setEventNext(result.nextPageToken??'');
  };
  const queue=async(operation:string,payload:unknown,title:string)=>{
    const proposal={operation,system:operation==='create_email_draft'?'gmail':'calendar',summary:title,payload};
    const signature=JSON.stringify(proposal);
    const key=retry?.signature===signature?retry.key:'google-'+crypto.randomUUID();
    setRetry({signature,key});
    await api('/api/agent/work-actions',{...proposal,idempotencyKey:key});
    setRetry(null);setNotice('Proposal queued. Review its exact details in Tasks & approvals. Saving a draft or changing an appointment requires approval and execution.');
  };
  const choose=(event:Appointment)=>{
    setSelected(event);setSummary(event.summary);setStart(event.start.dateTime?localInput(event.start.dateTime):'');setEnd(event.end.dateTime?localInput(event.end.dateTime):'');setAttendees(event.attendees.map(a=>a.email).join(', '));
  };
  const eventPayload=()=>({summary,start:utc(start),end:utc(end),attendees:attendees.split(',').map(s=>s.trim()).filter(Boolean)});
  const field='mt-1 block min-h-11 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100';
  const button='min-h-11 rounded-lg border border-slate-600 px-3 py-2 disabled:opacity-40 hover:border-cyan-400';
  return <section aria-label="Email and appointments" className="space-y-5 rounded-xl border border-slate-700 bg-slate-900 p-4 text-sm text-slate-100">
    <div><h2 className="text-xl font-semibold">Email & appointments</h2><p className="mt-1 text-slate-400">{owner} · Saint Lucia time. You review and send every email.</p></div>
    <button className={button} disabled={busy} onClick={()=>void work(async()=>setStatus(await api('/api/agent/google/status')))}>Check Google connection</button>
    {status&&!status.connected&&<p role="status">{status.enabled?'Google authorization needs attention.':'Google setup is pending. Ask your administrator to complete authorization.'}</p>}
    {error&&<p role="alert" className="text-red-300">{error}</p>}{notice&&<p role="status" className="text-cyan-200">{notice}</p>}
    {status?.connected&&<>
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
          <button className={button} disabled={busy||thread.partial||!recipient||!reply||!thread.messages.length} onClick={()=>void work(async()=>{
            const message=thread.messages.at(-1)!;
            await queue('create_email_draft',{threadId:thread.id,messageId:message.id,to:recipient.trim(),subject:(message.subject.startsWith('Re:')?message.subject:'Re: '+message.subject).slice(0,200),body:reply.trim()},('Gmail draft: '+message.subject).slice(0,180));
          })}>Queue Gmail draft for approval</button>
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
        <div className="flex flex-wrap gap-3"><button className={button} disabled={busy||!summary||!start||!end||Boolean(selected&&(selected.recurring||selected.organizer!==owner))} onClick={()=>void work(()=>queue(selected?'update_calendar_event':'create_calendar_event',selected?{...eventPayload(),eventId:selected.id,etag:selected.etag}:eventPayload(),selected?'Review appointment rescheduling':'Review new appointment'))}>Queue {selected?'change':'appointment'} for approval</button>
        {selected&&<button className={button} disabled={busy||selected.recurring||selected.organizer!==owner} onClick={()=>{
          if(window.confirm('Queue cancellation of '+selected.summary+'? Approved cancellation can notify its attendees.')) void work(()=>queue('delete_calendar_event',{eventId:selected.id,etag:selected.etag},('Cancel appointment: '+selected.summary).slice(0,180)));
        }}>Queue cancellation</button>}</div>
      </div>
      <div className="space-y-3 border-t border-slate-700 pt-4"><p>After reviewing and approving a Google proposal in Tasks & approvals, execute it here. This processes the oldest eligible approved Google action.</p><button className={button} disabled={busy} onClick={()=>void work(async()=>{const result=await api('/api/agent/google/run-once',{});setNotice(result.status==='idle'?'No eligible approved Google action is waiting.':result.status==='succeeded'?'Approved action completed. Review the saved draft in Gmail or the appointment in Google Calendar. Email was not sent.':'Action needs review: '+result.status);})}>Execute next approved Google action</button></div>
    </>}
  </section>;
}
