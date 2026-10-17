import { useState } from 'react';

type Entry = {slot:string;ranAt:string;state:'available'|'incomplete';report:{priority:string;coverage:string;findings:Array<{id:string;system:string;metric:string;value:number;severity:string}>;missingSources:string[]}};
type History = {mode:'read-only';status:string;reports:Entry[]};
function valid(value: unknown): value is History {
  if (!value || typeof value !== 'object') return false;
  const v=value as History;
  return v.mode==='read-only' && ['disabled','report_available','incomplete','stale_or_unavailable','unavailable'].includes(v.status) &&
    Array.isArray(v.reports) && v.reports.length<=12 && v.reports.every(e=>e &&
      typeof e.slot==='string' && e.slot.length<=40 && typeof e.ranAt==='string' && Number.isFinite(Date.parse(e.ranAt)) &&
      ['available','incomplete'].includes(e.state) && e.report &&
      ['attention','watch','routine'].includes(e.report.priority) && ['available','incomplete'].includes(e.report.coverage) &&
      Array.isArray(e.report.findings) && e.report.findings.length<=50 && e.report.findings.every(f=>f &&
        typeof f.system==='string' && /^[a-zA-Z0-9_-]{1,90}$/.test(f.system) &&
        typeof f.metric==='string' && /^[a-zA-Z0-9_-]{1,90}$/.test(f.metric) &&
        typeof f.value==='number' && Number.isFinite(f.value) && ['attention','watch','information'].includes(f.severity)) &&
      Array.isArray(e.report.missingSources) && e.report.missingSources.length<=20 &&
      e.report.missingSources.every(s=>typeof s==='string' && /^[a-zA-Z0-9_-]{1,90}$/.test(s)));
}
const statusText: Record<string,string> = {disabled:'Report access is disabled',report_available:'Report available',incomplete:'Evidence is incomplete',stale_or_unavailable:'Reports are stale or unavailable',unavailable:'Reports are unavailable'};
export function WorkforceBriefingHistory() {
  const [history,setHistory]=useState<History|null>(null);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  async function refresh() {
    if(busy)return;
    setBusy(true);setHistory(null);setError('');
    try {
      const res=await fetch('/api/agent/workforce-briefings',{method:'GET',credentials:'same-origin',cache:'no-store'});
      if(!res.ok)throw Error(res.status===403?'An MFA-verified owner session is required.':'Briefing history is unavailable.');
      const data:unknown=await res.json();
      if(!valid(data))throw Error('Briefing history could not be verified.');
      setHistory(data);
    }catch(e){setError(e instanceof Error?e.message:'Briefing history is unavailable.');}
    finally{setBusy(false);}
  }
  return <section aria-label="CEO and COO briefing history" className="border-b border-slate-800 bg-slate-950 px-5 py-4 text-sm text-slate-200">
    <div className="flex flex-wrap items-center justify-between gap-3"><h2 className="font-semibold text-cyan-200">CEO / COO briefings</h2>
      <button type="button" disabled={busy} onClick={()=>void refresh()} className="rounded border border-slate-600 px-3 py-2 disabled:opacity-50">{busy?'Loading…':'Load briefing history'}</button></div>
    <p className="mt-2 text-slate-400">Read-only reports · 8:00 AM and 7:00 PM Saint Lucia. Viewing a report does not approve or execute tasks.</p>
    <div aria-live="polite">{error&&<p role="alert" className="mt-3 text-amber-300">{error}</p>}
      {history&&<><p className="mt-3 font-medium">{statusText[history.status]}</p>
        {!history.reports.length&&<p>No reports are available to display.</p>}
        <div className="mt-3 space-y-3">{history.reports.map(e=><details key={e.slot} className="rounded border border-slate-700 p-3">
          <summary className="cursor-pointer">{new Date(e.ranAt).toLocaleString('en-GB',{timeZone:'America/St_Lucia'})} AST · {e.report.priority} · {e.state}</summary>
          {history.status==='stale_or_unavailable'&&<p className="mt-2 text-amber-300">Historical evidence; current conditions are unverified.</p>}
          <ul className="mt-2 space-y-1">{e.report.findings.map((f,i)=><li key={i}>{f.system} · {f.metric}: {f.value} ({f.severity})</li>)}</ul>
          {!!e.report.missingSources.length&&<p className="mt-2 text-amber-300">Missing sources: {e.report.missingSources.join(', ')}</p>}
        </details>)}</div></>}
    </div>
  </section>;
}
