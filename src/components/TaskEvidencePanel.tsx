import {useState} from "react";
export type TaskDeliverable={id:string;summary:string;content:string;links:string[];sha256:string;accepted:boolean;createdAt:string};
export type EvidenceTask={id:string;title:string;detail?:string;status:string;system:string;taskDigest:string;createdAt?:string;deliverables?:TaskDeliverable[];currentDeliverableId?:string;completion?:{kind?:string;reason?:string;relatedTaskId?:string};reconciliationOptions?:{creationTest:boolean;duplicateTaskIds:string[]}};
export function TaskEvidencePanel({task,tasks,disabled,run,send,notice}:{task:EvidenceTask;tasks:EvidenceTask[];disabled:boolean;run:(fn:()=>Promise<void>)=>Promise<void>;send:(path:string,body:unknown)=>Promise<unknown>;notice:(value:string)=>void}){
 const [summary,setSummary]=useState(""),[content,setContent]=useState(""),[links,setLinks]=useState("");
 const [decision,setDecision]=useState(task.reconciliationOptions?.creationTest?"verify_creation_test":task.reconciliationOptions?.duplicateTaskIds.length?"supersede_duplicate":"cancel");
 const [reason,setReason]=useState(""),[related,setRelated]=useState(task.reconciliationOptions?.duplicateTaskIds[0]||"");
 const field="mt-1 block min-h-11 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-300";
 const selected=task.deliverables?.find(d=>d.id===task.currentDeliverableId);
 const base="/tasks/"+encodeURIComponent(task.id);
 return <details className="w-full border-t border-slate-800 pt-2">
  <summary className="min-h-11 cursor-pointer py-3 text-sm font-medium text-cyan-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-300">Evidence and closure</summary>
  <div className="space-y-5 pb-3">
   {task.detail&&<p className="max-w-prose whitespace-pre-wrap text-sm leading-6 text-slate-300">{task.detail}</p>}
   {task.completion&&<p className="text-sm text-slate-300">{task.completion.reason||"This task has a recorded owner decision."}</p>}
   {selected&&<section aria-label={"Saved deliverable for "+task.title} className="space-y-3">
    <h5 className="font-semibold">{selected.summary}</h5>
    <p className="max-h-96 max-w-prose overflow-auto whitespace-pre-wrap break-words text-sm leading-6 text-slate-300">{selected.content}</p>
    {!!selected.links.length&&<ul className="space-y-2">{selected.links.map((link,i)=><li key={link}><a href={link} target="_blank" rel="noopener noreferrer" className="break-all text-cyan-200 underline underline-offset-4 focus-visible:ring-2 focus-visible:ring-cyan-300">Open evidence file {i+1}</a></li>)}</ul>}
    <p className="text-xs text-slate-400">{selected.accepted?"Owner accepted this saved deliverable.":"Saved draft · awaiting owner review. Saving evidence does not complete the task."}</p>
    {!selected.accepted&&task.status==="open"&&<button type="button" disabled={disabled} className="min-h-11 rounded-lg border border-emerald-700 px-3 py-2 text-emerald-200 disabled:opacity-50" onClick={()=>{
     if(!window.confirm("Accept this exact saved deliverable for "+task.title+"? Read its content and linked evidence first. This records completion; it does not authorise deployment, payments or messages."))return;
     void run(async()=>{await send(base+"/accept-deliverable",{taskDigest:task.taskDigest,deliverableId:selected.id,sha256:selected.sha256});notice("Saved deliverable accepted. The task is completed.");});
    }}>Accept saved deliverable</button>}
   </section>}
   {task.status==="open"&&<>
    <form aria-label={"Record deliverable for "+task.title} className="max-w-3xl space-y-3" onSubmit={e=>{e.preventDefault();if(disabled)return;void run(async()=>{
      await send(base+"/deliverable",{taskDigest:task.taskDigest,summary:summary.trim(),content:content.trim(),links:links.split("\n").map(x=>x.trim()).filter(Boolean)});
      notice("Deliverable saved for review. Owner acceptance is still required.");setSummary("");setContent("");setLinks("");
    });}}>
     <fieldset disabled={disabled} className="space-y-3"><legend className="font-medium">Record completed work</legend>
      <p className="text-xs leading-5 text-slate-400">Attach the actual result and evidence. This records a draft; it does not claim a local specialist produced it.</p>
      <label className="block">Deliverable title<input required minLength={8} maxLength={180} value={summary} onChange={e=>setSummary(e.target.value)} className={field}/></label>
      <label className="block">Result and verification<textarea required minLength={80} maxLength={30000} rows={6} value={content} onChange={e=>setContent(e.target.value)} className={field+" resize-y"}/></label>
      <label className="block">Evidence links · one per line<textarea rows={3} value={links} onChange={e=>setLinks(e.target.value)} className={field+" resize-y"} aria-describedby={"link-help-"+task.id}/></label>
      <p id={"link-help-"+task.id} className="text-xs text-slate-400">Up to eight saved ChatGPT Library or Vision79 GitHub evidence links. Never include credentials or private signed download links.</p>
      <button type="submit" className="min-h-11 rounded-lg border border-cyan-700 px-3 py-2 text-cyan-200 disabled:opacity-50">Save deliverable draft</button>
     </fieldset>
    </form>
    <form aria-label={"Reconcile "+task.title} className="max-w-3xl space-y-3 border-t border-slate-800 pt-4" onSubmit={e=>{e.preventDefault();if(disabled)return;
     if(!window.confirm("Record this exact task decision? "+decision.replaceAll("_"," ")+". "+reason))return;
     void run(async()=>{await send(base+"/reconcile",{taskDigest:task.taskDigest,decision,reason:reason.trim(),relatedTaskId:decision==="supersede_duplicate"?related:null});notice("Task decision recorded with its evidence and audit history.");});
    }}>
     <fieldset disabled={disabled} className="space-y-3"><legend className="font-medium">Reconcile an old task</legend>
      <label className="block">Decision<select value={decision} onChange={e=>setDecision(e.target.value)} className={field}>
       {task.reconciliationOptions?.creationTest&&<option value="verify_creation_test">Verify the recorded task-creation test</option>}
       {!!task.reconciliationOptions?.duplicateTaskIds.length&&<option value="supersede_duplicate">Supersede an exact duplicate</option>}
       <option value="cancel">Cancel without claiming completion</option>
      </select></label>
      {decision==="supersede_duplicate"&&<label className="block">Keep this task<select required value={related} onChange={e=>setRelated(e.target.value)} className={field}>{task.reconciliationOptions?.duplicateTaskIds.map(id=>{const t=tasks.find(t=>t.id===id);return <option key={id} value={id}>{t?.title} · {t?.createdAt?.slice(0,10)||id.slice(0,8)}</option>;})}</select></label>}
      <label className="block">Reason and evidence<textarea required minLength={12} maxLength={1000} rows={3} value={reason} onChange={e=>setReason(e.target.value)} className={field+" resize-y"}/></label>
      <p className="text-xs leading-5 text-slate-400">A fresh owner MFA session is required. Test verification checks the original approved job and its recorded task. Duplicate closure keeps the linked task and its history.</p>
      <button type="submit" className="min-h-11 rounded-lg border border-slate-600 px-3 py-2 disabled:opacity-50">Apply recorded decision</button>
     </fieldset>
    </form>
   </>}
  </div>
 </details>;
}
