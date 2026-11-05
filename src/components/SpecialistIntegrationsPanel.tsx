import {useEffect,useRef,useState} from 'react';
type Source={system:string;name:string;state:string;reportedAt:string|null;metricKeys:string[]};
type Role={id:string;name:string;status:string;systems:string[];sources:Source[];limitations:string[];skillSha:string};
type Report={kind:string;mode:string;collectedAt:string;receiptSha256:string;roles:Role[]};
export function SpecialistIntegrationsPanel({active=true}:{active?:boolean}){
 const [report,setReport]=useState<Report|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);const serial=useRef(0);
 async function refresh(){const id=++serial.current;setBusy(true);setError('');try{
  const response=await fetch('/api/agent/specialist-integrations',{credentials:'same-origin',cache:'no-store'});const data=await response.json();
  if(!response.ok)throw Error(response.status===403?'Sign in with your MFA-verified owner account.':data.error||'Integration evidence unavailable.');
  if(data.kind!=='specialist-integration-report'||data.mode!=='read-only'||!Array.isArray(data.roles)||data.roles.length!==8||data.roles.some((r:Role)=>!Array.isArray(r.sources)||!Array.isArray(r.limitations)))throw Error('Unexpected integration report.');
  if(id===serial.current)setReport(data);
 }catch(e){if(id===serial.current){setReport(null);setError(e instanceof Error?e.message:'Integration evidence unavailable.');}}
 finally{if(id===serial.current)setBusy(false);}}
 useEffect(()=>{if(active)void refresh();return()=>{serial.current++;};},[active]);
 return <section aria-label="Specialist integrations" className="space-y-4 p-4 sm:p-6">
  <div className="flex flex-wrap items-start justify-between gap-3"><div><h3 className="text-lg font-semibold">Specialist integrations</h3><p className="mt-1 text-sm">See which apps each specialist can read and when the source reported its data.</p></div><button type="button" disabled={busy} onClick={()=>void refresh()} className="min-h-11 rounded-lg border px-4 py-2 disabled:opacity-50">{busy?'Checking sources…':'Refresh sources'}</button></div>
  <p className="text-sm">Read-only aggregate data. Task reviews and acceptance keep their existing owner approvals.</p>
  {error&&<p role="alert" className="rounded-lg border border-red-300 bg-red-50 p-3 text-red-800">{error}</p>}
  {report&&<><p role="status" className="text-sm">{report.roles.filter(r=>r.status==='available').length} of {report.roles.length} specialists have fresh data across their configured app scope. Checked {new Date(report.collectedAt).toLocaleString('en-GB',{timeZone:'America/St_Lucia'})} Saint Lucia time.</p>
   <div className="grid gap-4 lg:grid-cols-2">{report.roles.map(role=><article key={role.id} className="min-w-0 rounded-xl border p-4"><div className="flex flex-wrap justify-between gap-2"><h4 className="font-semibold">{role.name}</h4><span className="text-sm">{role.status==='available'?'Fresh data':role.status==='partial'?'Some sources unavailable':'Evidence unavailable'}</span></div><p className="mt-2 text-sm">App scope: {role.systems.join(', ')}</p>
    <ul className="mt-3 space-y-2 text-sm">{role.sources.map(source=><li key={source.system} className="border-t pt-2"><strong>{source.name}</strong> · {source.state} · {source.metricKeys.length} approved metrics<br/><span>{source.reportedAt?'Source reported '+new Date(source.reportedAt).toLocaleString('en-GB',{timeZone:'America/St_Lucia'}):'Source timestamp unavailable'}</span></li>)}</ul>
    <p className="mt-3 text-sm">{role.limitations.join(' ')}</p><details className="mt-3 text-xs"><summary>Protected skill version</summary><p className="break-all">{role.skillSha}</p></details>
   </article>)}</div><details className="text-xs"><summary>Evidence receipt</summary><p className="break-all">{report.receiptSha256}</p><p>Content digest of this report. It does not independently certify source measurements.</p></details></>}
  <a className="inline-flex min-h-11 items-center rounded-lg border px-4 py-2" href="/api/agent/evidence-gateway/access" target="_blank" rel="noopener noreferrer">Manage Evidence Gateway access</a>
  <p className="text-sm">The Evidence Gateway uses a separate owner-approved connection. Sentinel integration is reserved for the next phase.</p>
 </section>;
}
