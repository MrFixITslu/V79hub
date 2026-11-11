import {useEffect,useState} from 'react';
import {ShieldCheck,LockKeyhole,RefreshCw,AlertTriangle} from 'lucide-react';
type Media={id:string;sha256:string;mime:string;kind:string};
type Package={packageId:string;campaignId:string;creatorUserId:string;exactDigest:string;
  caption:string;channel:string;scheduledAt:string;accountId:string;providerAccountId:string;
  assets:Media[]};
type Delivery={id:string;status:string;channel:string;scheduledAt:string;providerPostId?:string};
export function MarketingStudioApprovals(){
  const [items,setItems]=useState<Package[]>([]);
  const [receipts,setReceipts]=useState<Delivery[]>([]);
  const [enabled,setEnabled]=useState(false),[loading,setLoading]=useState(true),
    [busy,setBusy]=useState(false),[selected,setSelected]=useState<string|null>(null),
    [confirmed,setConfirmed]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
  const refresh=async()=>{
    const r=await fetch('/api/studio/marketing/inbox',{credentials:'same-origin',cache:'no-store'});
    const data=await r.json().catch(()=>({}));
    if(!r.ok)throw Error('Private reviews require current Hub membership and fresh MFA');
    setItems(Array.isArray(data.packages)?data.packages:[]);
    setEnabled(data.approvalEnabled===true);
    const history=await fetch('/api/studio/marketing/history',{credentials:'same-origin',cache:'no-store'});
    if(history.ok){const h=await history.json().catch(()=>({}));
      setReceipts(Array.isArray(h.deliveries)?h.deliveries:[]);}
  };
  useEffect(()=>{let alive=true;
    refresh().catch(e=>{if(alive)setError(e.message);})
      .finally(()=>{if(alive)setLoading(false);});
    return()=>{alive=false;};},[]);
  const approve=async(x:Package)=>{
    if(!confirmed||!enabled||busy)return;
    setBusy(true);setError('');setNotice('');
    try{
      const r=await fetch('/api/studio/marketing/approve',{method:'POST',credentials:'same-origin',
        headers:{'Content-Type':'application/json'},body:JSON.stringify({
          creatorUserId:x.creatorUserId,campaignId:x.campaignId,packageId:x.packageId,
          exactDigest:x.exactDigest,confirmExactPublication:true})});
      const body=await r.json().catch(()=>({}));
      if(!r.ok||!body.delivery?.id)throw Error('Exact Hub approval declined or uncertain. Check history before another attempt.');
      setNotice('Approval recorded for the exact reviewed content. Publishing is not yet confirmed.');
      setSelected(null);setConfirmed(false);await refresh();
    }catch(e){setError(e instanceof Error?e.message:'Exact publishing approval unavailable');}
    finally{setBusy(false);}
  };
  return <main className="mx-auto w-full max-w-6xl space-y-5 px-4 py-6 text-slate-100 sm:px-7">
    <header className="rounded-3xl border border-slate-700 bg-[#0b1b2c] p-6">
      <p className="text-sm font-semibold text-teal-300">V79 Hub · Signed publishing controls</p>
      <h1 className="mt-2 text-2xl font-bold sm:text-3xl">Review before anything goes live.</h1>
      <p className="mt-2 text-sm leading-6 text-slate-300">Review the creator's signed media, exact caption,
        original social account and proposed schedule. A private creative review never authorises publication.</p>
    </header>
    {error&&<p role="alert" className="rounded-xl border border-rose-700 bg-rose-950 p-4 text-sm">{error}</p>}
    {notice&&<p role="status" className="rounded-xl border border-teal-700 bg-teal-950 p-4 text-sm">{notice}</p>}
    {!enabled&&<p role="status" className="flex items-start gap-2 rounded-xl border border-amber-700 bg-amber-950/40 p-4 text-sm text-amber-100">
      <LockKeyhole size={19} className="shrink-0"/> Publishing remains disabled until paired release acceptance and owner authorisation.</p>}
    <section aria-label="Signed packages awaiting approval" className="space-y-4">
      <div className="flex items-center justify-between gap-3"><h2 className="font-bold">Awaiting exact approval</h2>
        <button type="button" className="flex min-h-11 items-center gap-2 rounded-xl border border-slate-500 px-4 text-sm"
          onClick={()=>void refresh().catch(e=>setError(e.message))}><RefreshCw size={16}/> Refresh</button></div>
      {loading?<p role="status">Loading signed review packages…</p>:
        items.length===0?<p className="rounded-xl border border-slate-700 bg-[#0b1b2c] p-5 text-sm text-slate-300">
          No current, reviewed packages require approval.</p>:
        items.map(item=><article key={item.packageId} className="rounded-2xl border border-slate-700 bg-[#0b1b2c] p-5">
          <div className="grid gap-5 md:grid-cols-2">
            <div className="space-y-3">{item.assets.map(asset=><div key={asset.id} className="rounded-xl bg-slate-950 p-2">
              {asset.mime.startsWith('image/')?<img loading="lazy" className="max-h-[420px] w-full object-contain"
                alt={'Creator-reviewed image '+asset.sha256.slice(0,12)}
                src={'/api/studio/marketing/media/'+item.packageId+'/'+asset.id}/>:
                <video controls playsInline preload="metadata" className="max-h-[420px] w-full"
                  aria-label="Creator-reviewed video" src={'/api/studio/marketing/media/'+item.packageId+'/'+asset.id}/>}
              <p className="mt-2 break-all font-mono text-xs text-slate-400">
                {asset.kind} · SHA-256 {asset.sha256.slice(0,20)}…</p>
            </div>)}</div>
            <div className="space-y-4 text-sm">
              <p className="font-bold uppercase text-teal-300">{item.channel}</p>
              <h3 className="text-lg font-bold">Exact signed creative</h3>
              <p className="whitespace-pre-wrap rounded-xl bg-[#07111f] p-4 leading-6">{item.caption}</p>
              <p><strong>Destination:</strong> <span className="break-all">{item.providerAccountId}</span></p>
              <p><strong>Schedule:</strong> {new Date(item.scheduledAt).toLocaleString()}</p>
              <p className="break-all font-mono text-xs text-slate-400">{item.exactDigest}</p>
              <button type="button" aria-expanded={selected===item.packageId}
                onClick={()=>{setSelected(v=>v===item.packageId?null:item.packageId);setConfirmed(false);}}
                className="min-h-11 w-full rounded-xl border border-slate-500 px-3 font-semibold">
                {selected===item.packageId?'Close approval details':'Review exact publishing consent'}</button>
              {selected===item.packageId&&<div className="space-y-3 rounded-xl bg-[#07111f] p-4">
                <p className="flex gap-2 text-xs text-amber-200"><AlertTriangle size={16} className="shrink-0"/>
                  Check claims, media, destination and schedule. Edits or changed OAuth consent invalidate approval.</p>
                <label className="flex items-start gap-2"><input type="checkbox" className="mt-1" checked={confirmed}
                  onChange={e=>setConfirmed(e.target.checked)}/>
                  I authorise this exact reviewed package to this account at this time.</label>
                <button type="button" disabled={!enabled||!confirmed||busy}
                  onClick={()=>void approve(item)}
                  className="flex min-h-12 w-full items-center justify-center gap-2 rounded-xl bg-teal-600 px-4 font-bold disabled:opacity-40">
                  <ShieldCheck size={18}/>{busy?'Sending once…':'Approve with fresh Hub MFA'}</button>
              </div>}
            </div>
          </div>
        </article>)}
    </section>
    <section aria-label="Provider receipts" className="rounded-2xl border border-slate-700 bg-[#0b1b2c] p-5">
      <h2 className="font-semibold">Publishing status and provider receipts</h2>
      {receipts.length===0?<p className="mt-2 text-sm text-slate-400">No publication receipts yet.</p>:
      <div className="mt-3 space-y-2">{receipts.map(r=><p key={r.id} className="rounded-xl border border-slate-700 p-3 text-sm">
        <strong>{r.status}</strong> · {r.channel} · {new Date(r.scheduledAt).toLocaleString()}
        {r.status==='UNKNOWN'&&<span className="block text-amber-200">Provider outcome uncertain. No automatic retry.</span>}
        {r.providerPostId&&<span className="block break-all font-mono text-xs">Receipt: {r.providerPostId}</span>}
      </p>)}</div>}
    </section>
  </main>;
}
