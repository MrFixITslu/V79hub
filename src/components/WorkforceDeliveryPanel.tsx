import { useEffect, useState } from 'react';

type Row = {jobId:string;taskId:string|null;system:string;state:string;created:boolean;delivered:boolean};
type Board = {mode:'read-only';state:'verified_queue_projection'|'unavailable';totals:{awaiting:number;created:number;delivered:number;blocked:number};rows:Row[];independentDeliveryVerification:'not_configured';window:'latest-200-work-items'};
const labels:Record<string,string> = {awaiting_approval:'Awaiting your approval',awaiting_execution:'Approved · awaiting worker',execution_unconfirmed:'Waiting for execution receipt',work_item_created:'Task created · delivery unverified',blocked_uncertain:'Reconcile before retry',failed:'Failed',rejected:'Rejected',cancelled:'Cancelled',delivery_unverified:'Delivery proof unverified',delivery_verified:'Delivery verified'};
function valid(b:Board) {
  return b?.mode==='read-only' && ['verified_queue_projection','unavailable'].includes(b.state) &&
    b.independentDeliveryVerification==='not_configured' && b.window==='latest-200-work-items' &&
    b.totals && ['awaiting','created','delivered','blocked'].every(k=>Number.isInteger(b.totals[k as keyof Board['totals']]) && b.totals[k as keyof Board['totals']]>=0) &&
    b.totals.delivered===0 && Array.isArray(b.rows) && b.rows.length<=200 && b.rows.every(r=>r &&
      typeof r.jobId==='string' && typeof r.system==='string' && Object.hasOwn(labels,r.state) && r.delivered===false && typeof r.created==='boolean');
}
export function WorkforceDeliveryPanel({active=true}:{active?:boolean}) {
  const [board,setBoard]=useState<Board|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[revision,setRevision]=useState(0);
  useEffect(()=>{
    if(!active)return;
    const controller=new AbortController();setBoard(null);setError('');setBusy(true);
    void(async()=>{
      try{
        const res=await fetch('/api/agent/work-actions',{method:'GET',credentials:'same-origin',cache:'no-store',signal:controller.signal});
        if(!res.ok)throw Error(res.status===401||res.status===403?'An MFA-verified owner session is required.':'Task lifecycle unavailable.');
        const data=await res.json();
        if(data?.mode!=='owner-approved-actions'||!valid(data.delivery))throw Error('Verified task lifecycle is unavailable on this release.');
        if(!controller.signal.aborted)setBoard(data.delivery);
      }catch(e){if(!controller.signal.aborted)setError(e instanceof Error?e.message:'Task lifecycle unavailable.');}
      finally{if(!controller.signal.aborted)setBusy(false);}
    })();return()=>controller.abort();
  },[active,revision]);
  return <section aria-label="Verified task lifecycle" className="border-b border-slate-800 px-5 py-4 text-sm">
    <div className="flex flex-wrap items-center justify-between gap-3"><h3 className="font-semibold text-cyan-200">Verified task lifecycle</h3><button disabled={busy} onClick={()=>setRevision(n=>n+1)} className="min-h-11 rounded border border-slate-600 px-3 py-2 disabled:opacity-50">{busy?'Checking tasks…':'Refresh task evidence'}</button></div>
    <p className="mt-2 text-slate-400">Latest 200 work items · Approval, task creation and accepted delivery are separate stages.</p>
    {error&&<p role="alert" className="mt-3 text-amber-200">{error}</p>}
    {board?.state==='unavailable'&&<p className="mt-3 text-amber-200">The ledger could not establish a consistent task lifecycle. Counts are unavailable; reconcile the queue before retrying.</p>}
    {board?.state==='verified_queue_projection'&&<>
      <dl className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">{Object.entries({awaiting:'Awaiting action',created:'Created · delivery unverified',blocked:'Needs reconciliation',delivered:'Verified deliveries'}).map(([k,label])=><div key={k} className="rounded border border-slate-700 p-3"><dt className="text-xs text-slate-400">{label}</dt><dd className="mt-1 text-xl font-semibold">{board.totals[k as keyof Board['totals']]}</dd></div>)}</dl>
      <p className="mt-3 text-xs text-amber-200">Independent delivery verification is not connected. Task creation does not confirm that engineering or specialist work has been completed.</p>
      {!board.rows.length&&<p className="mt-3 text-slate-400">No work items in this queue window.</p>}
      <ul className="mt-3 space-y-2">{board.rows.slice().reverse().map(r=><li key={r.jobId} className="rounded border border-slate-800 p-3"><p>{r.system} · {labels[r.state]}</p><p className="mt-1 break-all font-mono text-xs text-slate-400">{r.taskId||r.jobId}</p></li>)}</ul>
    </>}
  </section>;
}
