import {createHash, randomUUID} from "node:crypto";
import {builtinSkillDetail} from "./workforce-builtins.mjs";

export const REVIEW_OPERATION = "run_specialist_review";
export const REVIEW_WORKER = "v79-specialist-review";
export const REVIEW_ROLES = Object.freeze(["ceo","coo","finance","strategy","marketing","customer-service","technical-security","sales"]);
const SHA = /^[a-f0-9]{64}$/;
const exact=(v,keys)=>v&&typeof v==="object"&&!Array.isArray(v)&&Object.keys(v).sort().join(",")===keys.slice().sort().join(",");
export const sha256=value=>createHash("sha256").update(value).digest("hex");
export function taskDigest(task) {
 return sha256(JSON.stringify([task.id,task.jobId,task.organizationId,task.system,task.title,task.detail,task.createdAt]));
}
export function validateReviewPayload(payload) {
 if(!exact(payload,["taskId","taskDigest","specialist","skillSha"])||typeof payload.taskId!=="string"||
   !/^[a-zA-Z0-9-]{1,128}$/.test(payload.taskId)||!SHA.test(payload.taskDigest)||
   !REVIEW_ROLES.includes(payload.specialist)||! /^[a-f0-9]{40}$/.test(payload.skillSha))throw Error("Invalid specialist review");
}
export function verifiedReviewTask(state,payload,org) {
 validateReviewPayload(payload);
 const task=state.tasks.find(t=>t.id===payload.taskId&&t.organizationId===org);
 const origin=task&&state.jobs.find(j=>j.id===task.jobId&&j.organizationId===org);
 if(!task||task.status!=="open"||origin?.operation!=="create_work_item"||origin.status!=="succeeded"||
   origin.result?.taskId!==task.id||!origin.approval||origin.approval.digest!==origin.digest||
   taskDigest(task)!==payload.taskDigest||builtinSkillDetail(payload.specialist).skillSha!==payload.skillSha)
   throw Error("Task or protected skill changed; queue a new review");
 return task;
}
export function assertReviewCanBeProposed(state,payload,org) {
 const task=verifiedReviewTask(state,payload,org);
 if(state.jobs.some(j=>j.organizationId===org&&j.operation===REVIEW_OPERATION&&j.payload.taskId===task.id&&
   ["pending","approved","running","uncertain"].includes(j.status)))throw Error("Task already has an unresolved review");
 return task;
}
export function finishSpecialistReview(state,id,receipt,{organizationId,now=Date.now()}) {
 const job=state.jobs.find(j=>j.id===id&&j.organizationId===organizationId);
 if(!exact(receipt,["claimToken","digest","status","output","model","skillSha"])||
   !job||job.operation!==REVIEW_OPERATION||job.status!=="running"||job.claim?.worker!==REVIEW_WORKER||
   job.claim.token!==receipt.claimToken||job.digest!==receipt.digest||
   !["succeeded","failed","uncertain"].includes(receipt.status)||receipt.skillSha!==job.payload.skillSha||
   typeof receipt.output!=="string"||Buffer.byteLength(receipt.output)>12000||
   /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/.test(receipt.output)||
   typeof receipt.model!=="string"||!/^[a-zA-Z0-9_.:/-]{1,100}$/.test(receipt.model))throw Error("Invalid specialist receipt");
 const task=verifiedReviewTask(state,job.payload,organizationId);
 if(receipt.status==="succeeded"&&receipt.output.trim().length<20)throw Error("Empty result is not delivery");
 if(state.events.length>=16000)throw Error("Audit capacity reached");
 const at=new Date(now).toISOString();
 job.status=receipt.status;job.revision++;
 job.result={at,kind:"specialist-review-draft",output:receipt.output,model:receipt.model,
  specialist:job.payload.specialist,skillSha:receipt.skillSha,outputSha256:sha256(receipt.output),
  taskDigest:job.payload.taskDigest,ownerAccepted:false};
 task.lastReviewJobId=job.id;
 state.events.push({id:randomUUID(),jobId:job.id,actor:REVIEW_WORKER,type:"specialist_"+job.status,
  at,revision:job.revision,digest:job.digest});
 return job;
}
export function acceptSpecialistReview(state,id,{organizationId,actor,expectedRevision,digest,outputSha256,now=Date.now()}) {
 const job=state.jobs.find(j=>j.id===id&&j.organizationId===organizationId);
 if(state.paused||!actor||!job||job.operation!==REVIEW_OPERATION||job.status!=="succeeded"||
   job.revision!==expectedRevision||job.digest!==digest||job.result?.ownerAccepted||
   job.result?.kind!=="specialist-review-draft"||job.result.outputSha256!==outputSha256||
   sha256(job.result.output)!==outputSha256)throw Error("Review result changed or unavailable");
 const task=verifiedReviewTask(state,job.payload,organizationId);
 if(state.events.length>=16000)throw Error("Audit capacity reached");
 const at=new Date(now).toISOString();
 job.result.ownerAccepted=true;job.result.acceptedBy=actor;job.result.acceptedAt=at;job.revision++;
 task.status="completed";task.completedAt=at;
 task.completion={kind:"owner-accepted-advisory-review",reviewJobId:job.id,by:actor,outputSha256};
 state.events.push({id:randomUUID(),jobId:job.id,actor,type:"specialist_review_accepted",at,revision:job.revision,digest:job.digest});
 return job;
}
export function publicReviewTask(task) {return {...task,taskDigest:taskDigest(task)};}

export function reconcileSpecialistReview(state,id,{organizationId,actor,expectedRevision,digest,now=Date.now()}) {
 const job=state.jobs.find(j=>j.id===id&&j.organizationId===organizationId);
 if(!actor||!job||job.operation!==REVIEW_OPERATION||!["running","uncertain"].includes(job.status)||
   job.revision!==expectedRevision||job.digest!==digest||!Number.isFinite(Date.parse(job.claim?.at))||
   now-Date.parse(job.claim.at)<180000)throw Error("Review is not eligible for interrupted-run reconciliation");
 if(state.events.length>=16000)throw Error("Audit capacity reached");
 const at=new Date(now).toISOString();job.status="failed";job.revision++;
 job.result={kind:"specialist-review-interrupted",at,ownerAccepted:false,
  output:"Owner closed an interrupted advisory review. No deliverable was accepted. A new review requires a new approval."};
 state.events.push({id:randomUUID(),jobId:job.id,actor,type:"specialist_review_reconciled",at,revision:job.revision,digest:job.digest});
 return job;
}
