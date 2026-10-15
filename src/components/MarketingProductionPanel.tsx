import { useCallback, useEffect, useRef, useState } from 'react';

type Brand={name:string;tagline:string;audience:string;tone:string;website:string;cta:string;primaryColor:string;accentColor:string;
  logoPng:string|null;mailingAddress:string|null;facts:{id:string;service:string;statement:string}[]};
type Plan={automaticDrafts:boolean;cadenceDays:number;channels:string[];publishDelayHours:number;newsletterSegmentId:string|null;
  newsletterFrom:string|null;newsletterConsentConfirmed:boolean;tiktokPrivacy?:string|null;tiktokMusicConfirmed?:boolean;youtubePrivacy:'private'|'unlisted'|'public'};
type Delivery={id:string;digest:string;channel:string;providerAccountId:string;scheduledAt:string;status:string;blocker?:string;
  audienceCount?:number;payload?:{audiencePolicy?:string};result?:{providerPostId:string;at:string}};
type Job={id:string;status:string;factId:string;angle:string;failure?:string;deliveries:Delivery[];bundle?:{
  source:string;brand?:Brand;materials:{channel:string;title:string;caption:string;videoScript:string;altText:string}[];
  assets:{name:string;sha256:string;mime:string}[];review:{method:string;blockers:string[];warnings:string[]}}};
type Status={mode:string;paused:boolean;configRevision:number;brand:Brand|null;plan:Plan|null;publishEnabled:boolean;jobs:Job[]};
const initialBrand:Brand={name:'V79 Digital',tagline:'From Idea to Advantage.',audience:'Caribbean small and medium businesses',
  tone:'Clear, practical, professional and approachable',website:'https://v79sl.com',cta:'Visit our website to discuss your business needs',
  primaryColor:'#081827',accentColor:'#00D5C9',logoPng:null,mailingAddress:null,
  facts:[{id:'ict-support',service:'ICT support',statement:'V79 Digital provides ICT support and business software services.'}]};
const initialPlan:Plan={automaticDrafts:false,cadenceDays:7,channels:['linkedin','facebook','instagram','youtube','newsletter'],
  publishDelayHours:24,newsletterSegmentId:null,newsletterFrom:null,newsletterConsentConfirmed:false,youtubePrivacy:'private'};
export function MarketingProductionPanel(){
  const [open,setOpen]=useState(false),[status,setStatus]=useState<Status|null>(null),[brand,setBrand]=useState(initialBrand),[plan,setPlan]=useState(initialPlan);
  const [editing,setEditing]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
  const [factId,setFactId]=useState('ict-support'),[angle,setAngle]=useState('One everyday business problem and a practical next step');
  const [confirmed,setConfirmed]=useState(false),[preview,setPreview]=useState<{url:string;mime:string;name:string}|null>(null);
  const [logoLoading,setLogoLoading]=useState(false),[logoError,setLogoError]=useState(''),[syncError,setSyncError]=useState('');
  const busyRef=useRef(false),editingRef=useRef(false),dirtyRef=useRef(false),logoRead=useRef(0),statusVersion=useRef(0);
  const statusRequest=useRef<AbortController|null>(null),draftRevision=useRef(0);
  useEffect(()=>()=>{if(preview)URL.revokeObjectURL(preview.url);},[preview]);
  useEffect(()=>()=>{logoRead.current++;statusRequest.current?.abort();},[]);
  const request=useCallback(async(body:unknown,signal?:AbortSignal)=>{const r=await fetch('/api/agent/marketing-production',{method:'POST',credentials:'same-origin',
    headers:{'content-type':'application/json'},body:JSON.stringify(body),signal});const b=await r.json();if(!r.ok)throw Error(b.error||'Marketing production unavailable');return b;},[]);
  const load=useCallback(async(hydrate=false)=>{
    const version=++statusVersion.current;statusRequest.current?.abort();
    const controller=new AbortController();statusRequest.current=controller;
    const timeout=window.setTimeout(()=>controller.abort(new Error('Status update timed out')),15000);
    try{
      const s=await request({action:'list'},controller.signal) as Status;
      if(version!==statusVersion.current)return;
      if(s.mode!=='owner-approved-marketing-production')throw Error('Unexpected production response');
      setStatus(s);setSyncError('');
      setFactId(current=>s.brand?.facts.some(f=>f.id===current)?current:s.brand?.facts[0]?.id||current);
      // Worker updates must never replace a logo or other unapproved form edits.
      if(hydrate&&!editingRef.current&&!dirtyRef.current){draftRevision.current=s.configRevision;if(s.brand)setBrand(s.brand);if(s.plan)setPlan(s.plan);}
    }finally{window.clearTimeout(timeout);if(statusRequest.current===controller)statusRequest.current=null;}
  },[request]);
  useEffect(()=>{
    if(!open)return;
    let stopped=false,cycle=0,timer:number|undefined;
    const poll=async(hydrate=false)=>{
      if(stopped||document.visibilityState==='hidden')return;
      const currentCycle=cycle;
      if(!busyRef.current){try{await load(hydrate);}catch(e){if(!stopped&&!(e instanceof DOMException&&e.name==='AbortError'))setSyncError('Status update failed. Retrying automatically. '+(e instanceof Error?e.message:''));}}
      if(!stopped&&cycle===currentCycle&&String(document.visibilityState)!=='hidden')timer=window.setTimeout(()=>void poll(),10000);
    };
    const visibility=()=>{cycle++;window.clearTimeout(timer);if(document.visibilityState==='hidden'){statusVersion.current++;statusRequest.current?.abort();}else void poll();};
    document.addEventListener('visibilitychange',visibility);void poll(true);
    return()=>{stopped=true;window.clearTimeout(timer);statusVersion.current++;statusRequest.current?.abort();document.removeEventListener('visibilitychange',visibility);};
  },[open,load]);
  async function perform(fn:()=>Promise<void>){if(busyRef.current)return;busyRef.current=true;setBusy(true);setError('');setNotice('');
    statusVersion.current++;statusRequest.current?.abort();
    try{await fn();await load(true);}catch(e){setError(e instanceof Error?e.message:'Request failed');}finally{busyRef.current=false;setBusy(false);}}
  function editBrand(update:(current:Brand)=>Brand){dirtyRef.current=true;setConfirmed(false);setBrand(update);}
  function editPlan(update:(current:Plan)=>Plan){dirtyRef.current=true;setConfirmed(false);setPlan(update);}
  async function selectLogo(file?:File){
    const version=++logoRead.current;setLogoError('');setLogoLoading(false);setConfirmed(false);
    if(!file)return;
    try{
      if(file.size>1048576)throw Error('Logo must be no larger than 1 MB. The previous logo was kept.');
      if(file.type!=='image/png')throw Error('Choose a PNG logo. The previous logo was kept.');
      setLogoLoading(true);
      const value=await new Promise<string>((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result));reader.onerror=reader.onabort=()=>reject(Error('Logo could not be read. Choose the file again.'));reader.readAsDataURL(file);});
      if(!/^data:image\/png;base64,iVBORw0KGgo/.test(value))throw Error('Logo is not a readable PNG. Choose another file.');
      const image=new Image();await new Promise<void>((resolve,reject)=>{image.onload=()=>resolve();image.onerror=()=>reject(Error('Logo is not a readable PNG. Choose another file.'));image.src=value;});
      if(image.naturalWidth>2048||image.naturalHeight>2048)throw Error('Logo must be at most 2048 × 2048 pixels. The previous logo was kept.');
      if(version===logoRead.current)editBrand(current=>({...current,logoPng:value}));
    }catch(e){if(version===logoRead.current)setLogoError(e instanceof Error?e.message:'Logo could not be read');}
    finally{if(version===logoRead.current)setLogoLoading(false);}
  }
  const save=()=>perform(async()=>{
    if(logoLoading||logoError)throw Error('Finish selecting a valid logo before approving the draft plan');
    if(!confirmed)throw Error('Confirm the brand and service facts before approving the draft plan');
    if(!window.confirm('Approve these brand facts and this standing draft-production plan?\n\nAutomatic drafts never approve publication. Changing this configuration cancels outstanding publication approvals.'))return;
    await request({action:'configure',config:{brand,plan,expectedRevision:draftRevision.current}});dirtyRef.current=false;editingRef.current=false;setEditing(false);setConfirmed(false);setNotice('Brand and draft plan approved. Publication still requires your exact approval.');
  });
  const decide=(job:Job,d:Delivery,decision:'approve'|'reject')=>perform(async()=>{
    const material=job.bundle?.materials.find(m=>m.channel===d.channel);
    const audience=d.channel==='newsletter'?`\nAudience: current opted-in members of this exact segment at send time (${d.audienceCount||0} in latest snapshot).`:'';
    if(decision==='approve'&&!window.confirm(`Approve this exact ${d.channel} publication?\n\nDestination: ${d.providerAccountId}${audience}\nWhen: ${new Date(d.scheduledAt).toLocaleString()}\n\n${material?.caption}\n\nReview the rendered assets before confirming. This approval covers only this package, account/segment and schedule. Image/video source files may be publicly reachable briefly for provider ingestion, including private YouTube uploads.`))return;
    await request({action:'decision',jobId:job.id,deliveryId:d.id,decision,digest:d.digest});setNotice(decision==='approve'?'Exact publication approved and waiting for its scheduled time.':'Publication rejected.');
  });
  async function asset(job:Job,name:string,download=false){setError('');try{
    const a=await request({action:'asset',jobId:job.id,name});const bytes=Uint8Array.from(atob(a.base64),(c:string)=>c.charCodeAt(0));
    const url=URL.createObjectURL(new Blob([bytes],{type:a.mime}));
    if(download){const link=document.createElement('a');link.href=url;link.download=name;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
    else setPreview({url,mime:a.mime,name});
  }catch(e){setError(e instanceof Error?e.message:'Asset unavailable');}}
  const field=(key:keyof Brand,label:string)=> <label className="block text-xs">{label}<input value={String(brand[key]||'')}
    onChange={e=>editBrand(current=>({...current,[key]:e.target.value}))} className="mt-1 w-full rounded bg-slate-800 p-2"/></label>;
  return <section className="border-b border-slate-800 bg-slate-900/80 px-5 py-3 text-sm">
    <button className="font-semibold text-cyan-200" aria-expanded={open} onClick={()=>setOpen(!open)}>V79 marketing · Production and approvals</button>
    {open&&<div className="mt-3 space-y-4">
      <p className="text-xs text-slate-300">COO prepares campaign packages. CEO checks brand, claims, links and accessibility. You review the actual materials and approve each destination and schedule.</p>
      {syncError&&<p role="status" className="text-amber-200">{syncError}</p>}
      {error&&<p role="alert" className="text-red-300">{error}</p>}{notice&&<p role="status" className="text-emerald-300">{notice}</p>}
      <div className="flex flex-wrap gap-2"><button disabled={busy} onClick={()=>perform(async()=>{})} className="rounded border border-slate-600 px-3 py-1">Refresh</button>
        {status&&<><button disabled={busy} onClick={()=>perform(async()=>{await request({action:'pause',paused:!status.paused});})} className="rounded border border-amber-600 px-3 py-1">{status.paused?'Resume production':'Pause production'}</button>
          <button disabled={busy} onClick={()=>{if(!editing){draftRevision.current=status.configRevision;if(status.brand)setBrand(status.brand);if(status.plan)setPlan(status.plan);dirtyRef.current=false;}else{logoRead.current++;setLogoLoading(false);setLogoError('');dirtyRef.current=false;}editingRef.current=!editing;setEditing(!editing);setConfirmed(false);}} className="rounded border border-slate-600 px-3 py-1">Review brand and draft plan</button>
          <span className="text-xs text-slate-400">Updates automatically · {status.paused?'Paused':status.plan?.automaticDrafts?'Automatic drafts active':'Drafts on request'} · {status.publishEnabled?'Exact approval required for publication':'Provider publication disabled'}</span></>}
      </div>
      {status&&(editing||!status.brand)&&<fieldset disabled={busy} className="space-y-3 rounded-lg border border-slate-700 p-3">
        <h3 className="font-semibold">Approve your brand and verified service facts</h3>
        <div className="grid gap-3 sm:grid-cols-2">{field('name','Business name')}{field('tagline','Tagline')}{field('audience','Audience')}{field('tone','Tone')}{field('website','Website')}{field('cta','Primary call to action')}
          <label className="text-xs">Primary colour<input type="color" value={brand.primaryColor} onChange={e=>editBrand(current=>({...current,primaryColor:e.target.value}))}/></label>
          <label className="text-xs">Accent colour<input type="color" value={brand.accentColor} onChange={e=>editBrand(current=>({...current,accentColor:e.target.value}))}/></label>
        </div>
        <label className="block text-xs">Original logo (PNG, up to 1 MB, at most 2048 × 2048 pixels)<input type="file" accept="image/png" disabled={busy} onChange={e=>void selectLogo(e.target.files?.[0])}/></label>
        {logoLoading&&<p role="status">Reading and checking your logo…</p>}
        {logoError&&<p role="alert" className="text-red-300">{logoError}</p>}
        {brand.logoPng&&<div className="space-y-2"><img src={brand.logoPng} alt="Selected brand logo" className="h-24 max-w-48 rounded bg-slate-800 object-contain p-2"/>
          <p role="status" className="text-xs text-slate-300">{brand.logoPng===status.brand?.logoPng?'Logo saved in your approved brand.':'Logo selected. Approve the brand and draft plan to save it for new campaign packages.'}</p>
          <button disabled={busy||logoLoading} onClick={()=>{logoRead.current++;editBrand(current=>({...current,logoPng:null}));setLogoError('');}} className="rounded border border-slate-600 px-3 py-1">Remove logo</button></div>}
        {!brand.logoPng&&!logoLoading&&<p className="text-xs text-slate-400">No logo selected. New packages will use a text wordmark.</p>}
        {brand.facts.map((f,i)=><div key={i} className="grid gap-2 sm:grid-cols-2"><label className="text-xs">Service name<input className="mt-1 w-full rounded bg-slate-800 p-2" value={f.service} onChange={e=>editBrand(current=>({...current,facts:current.facts.map((v,n)=>n===i?{...v,service:e.target.value}:v)}))}/></label>
          <label className="text-xs">Verified statement<textarea className="mt-1 w-full rounded bg-slate-800 p-2" value={f.statement} onChange={e=>editBrand(current=>({...current,facts:current.facts.map((v,n)=>n===i?{...v,statement:e.target.value}:v)}))}/></label></div>)}
        <button onClick={()=>editBrand(current=>({...current,facts:[...current.facts,{id:'service-'+crypto.randomUUID().slice(0,8),service:'',statement:''}]}))} className="rounded border border-slate-600 px-3 py-1">Add verified service</button>
        <label className="block"><input type="checkbox" checked={plan.automaticDrafts} onChange={e=>editPlan(current=>({...current,automaticDrafts:e.target.checked}))}/> Produce drafts automatically</label>
        <label className="block text-xs">Days between packages<input type="number" min="3" max="30" value={plan.cadenceDays} onChange={e=>editPlan(current=>({...current,cadenceDays:Number(e.target.value)}))} className="ml-2 w-16 rounded bg-slate-800 p-2"/></label>
        <div className="flex flex-wrap gap-3">{['facebook','instagram','linkedin','youtube','tiktok','newsletter'].map(c=><label key={c}><input type="checkbox" checked={plan.channels.includes(c)} onChange={e=>editPlan(current=>({...current,channels:e.target.checked?[...current.channels,c]:current.channels.filter(v=>v!==c)}))}/>{c}</label>)}</div>
        <label className="block text-xs">Proposed publication delay (hours)<input type="number" min="1" max="168" value={plan.publishDelayHours} onChange={e=>editPlan(current=>({...current,publishDelayHours:Number(e.target.value)}))} className="ml-2 w-20 rounded bg-slate-800 p-2"/></label>
        <label className="block text-xs">YouTube visibility<select value={plan.youtubePrivacy} onChange={e=>editPlan(current=>({...current,youtubePrivacy:e.target.value as Plan['youtubePrivacy']}))} className="ml-2 rounded bg-slate-800 p-2"><option>private</option><option>unlisted</option><option>public</option></select></label>
        {field('mailingAddress','Newsletter mailing address (needed before sending)')}
        {plan.channels.includes('newsletter')&&<div className="space-y-2">
          <label className="block text-xs">Newsletter sender email<input type="email" value={plan.newsletterFrom||''} onChange={e=>editPlan(current=>({...current,newsletterFrom:e.target.value||null}))} className="mt-1 w-full rounded bg-slate-800 p-2"/></label>
          <label className="block text-xs">Connected newsletter segment identifier<input value={plan.newsletterSegmentId||''} onChange={e=>editPlan(current=>({...current,newsletterSegmentId:e.target.value||null}))} className="mt-1 w-full rounded bg-slate-800 p-2"/></label>
          <label className="block"><input type="checkbox" checked={plan.newsletterConsentConfirmed} onChange={e=>editPlan(current=>({...current,newsletterConsentConfirmed:e.target.checked}))}/> This segment contains verified opt-in subscribers; it is not a list of leads or customers assumed to consent.</label>
        </div>}
        {plan.channels.includes('tiktok')&&<div className="space-y-2">
          <label className="block text-xs">TikTok privacy<select value={plan.tiktokPrivacy||''} onChange={e=>editPlan(current=>({...current,tiktokPrivacy:e.target.value||null}))} className="ml-2 rounded bg-slate-800 p-2"><option value="">Choose privacy</option><option value="SELF_ONLY">Only me</option><option value="PUBLIC_TO_EVERYONE">Everyone</option><option value="MUTUAL_FOLLOW_FRIENDS">Friends</option><option value="FOLLOWER_OF_CREATOR">Followers</option></select></label>
          <label className="block"><input type="checkbox" checked={plan.tiktokMusicConfirmed===true} onChange={e=>editPlan(current=>({...current,tiktokMusicConfirmed:e.target.checked}))}/> I confirm music usage rights. Generated photo posts add no music and disclose promotion of my own brand.</label>
        </div>}

        <p className="text-xs text-slate-400">Unconnected or incomplete channels remain exportable drafts. Newsletter publication uses the exact connected segment and its current opt-in members; each issue still requires approval. TikTok publishes the approved branded photo, with no added music.</p>
        <label className="block"><input type="checkbox" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/> I verified these facts, brand assets, and the draft-production scope.</label>
        <button disabled={busy||logoLoading||!!logoError||!confirmed} onClick={save} className="rounded bg-cyan-300 px-3 py-2 font-semibold text-slate-950 disabled:opacity-40">Approve brand and draft plan</button>
      </fieldset>}
      {status?.brand&&<div className="space-y-2 rounded-lg border border-slate-700 p-3"><p className="text-xs text-slate-300">{status.brand.logoPng?'Approved brand includes your uploaded logo.':'Approved brand has no logo; packages use a text wordmark.'} New packages use the approved brand and plan.</p>
        <label className="block text-xs">Service<select value={factId} onChange={e=>setFactId(e.target.value)} className="ml-2 rounded bg-slate-800 p-2">{status.brand.facts.map(f=><option key={f.id} value={f.id}>{f.service}</option>)}</select></label>
        <label className="block text-xs">Campaign angle<input value={angle} maxLength={200} onChange={e=>setAngle(e.target.value)} className="mt-1 w-full rounded bg-slate-800 p-2"/></label>
        {dirtyRef.current&&<p className="text-xs text-amber-200">Approve your edited brand and plan before producing a package.</p>}
        <button disabled={busy||status.paused||logoLoading||dirtyRef.current} onClick={()=>perform(async()=>{await request({action:'queue',request:{factId,angle,idempotencyKey:'package_'+crypto.randomUUID().replaceAll('-','')}});setNotice('Queued for the production worker. This panel updates automatically when the materials are ready.');})} className="rounded bg-cyan-300 px-3 py-2 font-semibold text-slate-950">Produce a campaign package</button></div>}
      {preview&&<div className="rounded border border-slate-700 p-3"><button onClick={()=>setPreview(null)} className="mb-2 underline">Close preview</button>{preview.mime==='video/mp4'?<video controls src={preview.url} className="max-h-96 w-full"/>:<img src={preview.url} alt={preview.name} className="max-h-96 w-full object-contain"/>}</div>}
      <div className="space-y-4">{status?.jobs.map(job=><article key={job.id} className="space-y-3 rounded-lg border border-slate-700 bg-slate-950 p-3">
        <div className="flex justify-between gap-3"><strong>{job.angle}</strong><span aria-live="polite">{job.status}</span></div>{job.failure&&<p className="text-red-300">{job.failure}</p>}
        {job.bundle&&<>{!job.bundle.brand?.logoPng&&job.bundle.review.warnings.some(w=>w.includes('original brand logo'))&&<p className="text-xs text-amber-200">This package was created without a saved logo. To include your logo, approve the updated brand and produce a new package; existing materials keep their original brand.</p>}<p className="text-xs text-slate-400">Copy source: {job.bundle.source} · Review: automated rule checks, followed by your review</p>
          {[...job.bundle.review.blockers,...job.bundle.review.warnings].map((v,i)=><p className="text-xs text-amber-200" key={i}>{v}</p>)}
          <div className="flex flex-wrap gap-2">{job.bundle.assets.map(a=><button key={a.name} onClick={()=>void asset(job,a.name,!['image/png','video/mp4'].includes(a.mime))} className="rounded border border-slate-600 px-2 py-1">{['image/png','video/mp4'].includes(a.mime)?'Preview':'Download'} {a.name}</button>)}</div>
          {job.bundle.materials.map(m=><details key={m.channel} className="rounded border border-slate-800 p-2"><summary>{m.channel}: {m.title}</summary><pre className="mt-2 whitespace-pre-wrap font-sans">{m.caption}</pre><p className="mt-2 text-xs text-slate-400">Alt text: {m.altText}</p></details>)}
          {job.deliveries.map(d=><div key={d.id} className="rounded border border-slate-800 p-2"><p>{d.channel} · {d.status}</p><p className="text-xs text-slate-400">Destination: {d.providerAccountId} · {new Date(d.scheduledAt).toLocaleString()}</p>
            {d.channel==='newsletter'&&<p className="text-xs text-slate-400">Audience: current opt-in members of the approved segment · {d.audienceCount||0} at preparation</p>}{d.blocker&&<p className="text-xs text-amber-200">{d.blocker}</p>}{d.result&&<p className="text-xs text-emerald-200">Provider accepted: {d.result.providerPostId}</p>}
            {d.status==='awaiting_owner'&&<div className="mt-2 flex gap-2"><button disabled={busy||status.paused||!status.publishEnabled} onClick={()=>decide(job,d,'approve')} className="rounded border border-emerald-600 px-3 py-1">Approve exact publication</button><button disabled={busy} onClick={()=>decide(job,d,'reject')} className="rounded border border-slate-600 px-3 py-1">Reject</button></div>}</div>)}
        </>}
        <button disabled={busy} onClick={()=>perform(async()=>{await request({action:'cancel',jobId:job.id});})} className="rounded border border-slate-600 px-3 py-1">Cancel unstarted package</button>
      </article>)}</div>
    </div>}
  </section>;
}
