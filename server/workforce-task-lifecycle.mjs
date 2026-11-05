import {createHash,randomUUID} from "node:crypto";
import {taskDigest} from "./workforce-specialist-delivery.mjs";
const exact=(v,keys)=>v&&typeof v==="object"&&!Array.isArray(v)&&Object.keys(v).sort().join(",")===keys.slice().sort().join(",");
const hash=x=>createHash("sha256").update(JSON.stringify(x)).digest("hex");
const clean=(v,max,min=1)=>typeof v==="string"&&v===v.trim()&&v.length>=min&&Buffer.byteLength(v)<=max&&!/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/.test(v);
const CREATION_TESTS=new Set([
 ["G2 supervised acceptance test","Record this acceptance task only. Do not modify code, deploy services, or change customer data."],
 ["Verify G2 approved-task creation","Create one internal test work item to verify founder approval, scheduled COO worker execution, and task recording. Do not deploy code, modify services, access customer data, or perform any other action. The test is successful when the work item is created and assigned to COO."],
 ["G2 acceptance dry-run 2026-10-28","Internal acceptance test only. Verify that the approved G2 worker creates exactly one COO work item. No customer changes, billing, messages, deployments or external actions."]
].map(x=>hash(x)));
function originFor(state,task,org){
 const job=state.jobs.find(j=>j.id===task.jobId&&j.organizationId===org);
 return job?.operation==="create_work_item"&&job.status==="succeeded"&&job.result?.taskId===task.id&&
  job.approval?.digest===job.digest&&task.assignedTo==="coo"?job:null;
}
function current(state,id,digest,{organizationId,actor,now}){
 const task=state.tasks.find(t=>t.id===id&&t.organizationId===organizationId);
 if(state.paused||!actor||!Number.isFinite(now)||!task||task.status!=="open"||taskDigest(task)!==digest||
  !originFor(state,task,organizationId)||state.events.length>=16000)throw Error("Task changed, closed or unavailable");
 if(state.jobs.some(j=>j.organizationId===organizationId&&j.operation==="run_specialist_review"&&j.payload?.taskId===id&&["pending","approved","running","uncertain"].includes(j.status)))throw Error("Reconcile the unresolved specialist review first");
 return task;
}
function audit(state,task,actor,type,now,extra={}){
 state.events.push({id:randomUUID(),jobId:task.jobId,taskId:task.id,actor,type,at:new Date(now).toISOString(),taskDigest:taskDigest(task),...extra});
}
export function reconciliationOptions(state,task,org){
 return {creationTest:!!originFor(state,task,org)&&CREATION_TESTS.has(hash([task.title,task.detail])),
 duplicateTaskIds:state.tasks.filter(t=>t.id!==task.id&&t.organizationId===org&&["open","completed"].includes(t.status)&&t.system===task.system&&t.title===task.title&&t.detail===task.detail&&originFor(state,t,org)).map(t=>t.id)};
}
export function reconcileTask(state,id,input,ctx){
 if(!exact(input,["taskDigest","decision","reason","relatedTaskId"])||!clean(input.reason,1000,12))throw Error("Exact reconciliation and reason required");
 const task=current(state,id,input.taskDigest,ctx),options=reconciliationOptions(state,task,ctx.organizationId),at=new Date(ctx.now).toISOString();
 if(input.decision==="verify_creation_test"){
  if(!options.creationTest||input.relatedTaskId!==null)throw Error("Only the exact recorded task-creation tests qualify");
  const job=originFor(state,task,ctx.organizationId);
  task.status="completed";task.completedAt=at;
  task.completion={kind:"verified-task-creation-test",by:ctx.actor,at,reason:input.reason,evidenceJobId:job.id,recordedTaskId:task.id};
 }else if(input.decision==="supersede_duplicate"){
  if(!options.duplicateTaskIds.includes(input.relatedTaskId))throw Error("Exact same-organisation duplicate required");
  task.status="superseded";task.completion={kind:"superseded-duplicate",by:ctx.actor,at,reason:input.reason,relatedTaskId:input.relatedTaskId};
 }else if(input.decision==="cancel"){
  if(input.relatedTaskId!==null)throw Error("Unexpected related task");
  task.status="cancelled";task.completion={kind:"owner-cancelled",by:ctx.actor,at,reason:input.reason};
 }else throw Error("Unknown reconciliation decision");
 audit(state,task,ctx.actor,"task_"+input.decision,ctx.now);return structuredClone(task);
}
function validateLink(value){
 if(typeof value!=="string"||value.length>700)throw Error("Invalid deliverable link");
 let u;try{u=new URL(value);}catch{throw Error("Invalid deliverable link");}
 if(u.protocol!=="https:"||u.username||u.password||u.hash)throw Error("HTTPS document link required");
 if(u.hostname==="chatgpt.com"&&u.pathname==="/library"){
  if(!/^libfile[-_][A-Za-z0-9_-]+$/.test(u.searchParams.get("file_id")||"")||u.searchParams.get("account_id")!=="personal"||[...u.searchParams.keys()].sort().join(",")!=="account_id,file_id")throw Error("Exact Library document link required");
 }else if(u.hostname==="github.com"){
  if(u.search||!/^\/MrFixITslu\/[A-Za-z0-9_.-]+\/(blob|issues|pull)\//.test(u.pathname))throw Error("V79 source or evidence link required");
 }else throw Error("Use a saved Library file or V79 GitHub evidence link");
 return u.href;
}
function deliverableSha(item){return hash([item.taskDigest,item.summary,item.content,item.links]);}
export function saveTaskDeliverable(state,id,input,ctx){
 if(!exact(input,["taskDigest","summary","content","links"])||!clean(input.summary,180,8)||!clean(input.content,30000,80)||!Array.isArray(input.links)||input.links.length>8)throw Error("Bounded deliverable required");
 const task=current(state,id,input.taskDigest,ctx);const links=[...new Set(input.links.map(validateLink))];
 const item={id:randomUUID(),taskDigest:input.taskDigest,summary:input.summary,content:input.content,links,createdBy:ctx.actor,createdAt:new Date(ctx.now).toISOString(),source:"owner-submitted-deliverable",accepted:false};
 item.sha256=deliverableSha(item);task.deliverables??=[];
 const same=task.deliverables.find(d=>d.sha256===item.sha256);if(same)return structuredClone(same);
 if(task.deliverables.length>=12)throw Error("Deliverable history capacity reached");
 task.deliverables.push(item);task.currentDeliverableId=item.id;audit(state,task,ctx.actor,"task_deliverable_saved",ctx.now,{deliverableSha256:item.sha256});
 return structuredClone(item);
}
export function acceptTaskDeliverable(state,id,input,ctx){
 if(!exact(input,["taskDigest","deliverableId","sha256"]))throw Error("Exact saved deliverable required");
 const task=current(state,id,input.taskDigest,ctx),item=task.deliverables?.find(d=>d.id===input.deliverableId);
 if(!item||task.currentDeliverableId!==item.id||item.accepted||item.taskDigest!==input.taskDigest||item.sha256!==input.sha256||deliverableSha(item)!==input.sha256)throw Error("Saved deliverable changed");
 const at=new Date(ctx.now).toISOString();item.accepted=true;item.acceptedBy=ctx.actor;item.acceptedAt=at;
 task.status="completed";task.completedAt=at;task.completion={kind:"owner-accepted-deliverable",by:ctx.actor,at,deliverableId:item.id,sha256:item.sha256};
 for(const job of state.jobs.filter(j=>j.organizationId===ctx.organizationId&&j.operation==="run_specialist_review"&&j.payload?.taskId===id&&j.result?.kind==="specialist-review-draft"&&!j.result.ownerAccepted)){
  job.result.supersededByDeliverable=item.id;job.revision++;
 }
 audit(state,task,ctx.actor,"task_deliverable_accepted",ctx.now,{deliverableSha256:item.sha256});return structuredClone(task);
}
