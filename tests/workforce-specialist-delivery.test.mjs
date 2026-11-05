import test from "node:test";
import assert from "node:assert/strict";
import {initialWorkState,proposeWork,decideWork,createApprovedWorkItem,claimWork,pauseWork,workDigest} from "../server/workforce-actions.mjs";
import {REVIEW_OPERATION,REVIEW_WORKER,taskDigest,finishSpecialistReview,acceptSpecialistReview,verifiedReviewTask,reconcileSpecialistReview} from "../server/workforce-specialist-delivery.mjs";
import {builtinSkillDetail} from "../server/workforce-builtins.mjs";
const org="synthetic-org",actor="synthetic-founder",now=Date.now();
function created(){
 const state=initialWorkState();
 const j=proposeWork(state,{operation:"create_work_item",system:"hub",summary:"Review customer support workflow",payload:{detail:"Prepare a review of support risks and missing evidence."},idempotencyKey:"synthetic-delivery-task-001"},{organizationId:org,actor,now});
 decideWork(state,j.id,"approve",{organizationId:org,actor,expectedRevision:1,digest:j.digest,now});
 createApprovedWorkItem(state,j.id,{organizationId:org,actor,expectedRevision:2,now});
 const task=state.tasks[0];
 const input={operation:REVIEW_OPERATION,system:task.system,summary:"Specialist review of support workflow",payload:{taskId:task.id,taskDigest:taskDigest(task),specialist:"customer-service",skillSha:builtinSkillDetail("customer-service").skillSha},idempotencyKey:"synthetic-review-key-001"};
 return{state,task,input};
}
function approved(){const x=created();const job=proposeWork(x.state,x.input,{organizationId:org,actor,now});decideWork(x.state,job.id,"approve",{organizationId:org,actor,expectedRevision:1,digest:job.digest,now});return{...x,job};}
function claimed(){const x=approved();claimWork(x.state,{organizationId:org,worker:REVIEW_WORKER,operations:[REVIEW_OPERATION],systems:["hub"],now});return x;}
function receipt(job){return{claimToken:job.claim.token,digest:job.digest,status:"succeeded",output:"DRAFT ADVICE — Review support hand-offs and identify missing response-time evidence. No action has been performed.",model:"synthetic-model",skillSha:job.payload.skillSha};}
function finished(){const x=claimed();finishSpecialistReview(x.state,x.job.id,receipt(x.job),{organizationId:org,now});return x;}
test("task creation is separate from model result and owner accepted completion",()=>{
 const{state,task,job}=finished();assert.equal(task.status,"open");assert.equal(job.result.ownerAccepted,false);
 const args={organizationId:org,actor,expectedRevision:job.revision,digest:job.digest,outputSha256:job.result.outputSha256,now};
 acceptSpecialistReview(state,job.id,args);assert.equal(task.status,"completed");assert.equal(task.completion.kind,"owner-accepted-advisory-review");assert.throws(()=>acceptSpecialistReview(state,job.id,args));
});
test("approval digest includes selected specialist, task content hash and skill pin",()=>{
 const{input}=created();for(const key of ["taskDigest","specialist","skillSha"]){const changed=structuredClone(input);changed.payload[key]=key==="specialist"?"sales":(key==="skillSha"?"b".repeat(40):"b".repeat(64));assert.notEqual(workDigest(input),workDigest(changed));}
});
test("review cannot target another organisation, changed task, or altered protected skill",()=>{
 for(const change of [x=>x.task.organizationId="foreign-org",x=>x.task.detail+=" altered",x=>x.input.payload.skillSha="a".repeat(40)]){
  const x=created();change(x);assert.throws(()=>proposeWork(x.state,x.input,{organizationId:org,actor,now}));}
});
test("idempotent proposals return same job while different duplicate review is rejected",()=>{
 const x=created(),j=proposeWork(x.state,x.input,{organizationId:org,actor,now});assert.equal(proposeWork(x.state,x.input,{organizationId:org,actor,now}).id,j.id);
 assert.throws(()=>proposeWork(x.state,{...x.input,idempotencyKey:"synthetic-different-key-002"},{organizationId:org,actor,now}));
});
test("unapproved, expired, paused and already claimed jobs cannot execute",()=>{
 const x=created();proposeWork(x.state,x.input,{organizationId:org,actor,now});const claim=s=>claimWork(s,{organizationId:org,worker:REVIEW_WORKER,operations:[REVIEW_OPERATION],systems:["hub"],now});assert.equal(claim(x.state),null);
 const y=approved();y.job.approval.expiresAt=new Date(now-1).toISOString();assert.equal(claim(y.state),null);
 const z=approved();pauseWork(z.state,true,{actor,now});assert.equal(claim(z.state),null);
 const a=claimed();assert.equal(claim(a.state),null);
});
test("forged or replayed result cannot complete a job",()=>{
 const x=claimed();for(const change of [r=>r.claimToken="forged",r=>r.digest="a".repeat(64),r=>r.skillSha="a".repeat(40),r=>r.output=""]){const r=receipt(x.job);change(r);assert.throws(()=>finishSpecialistReview(x.state,x.job.id,r,{organizationId:org,now}));}
 const r=receipt(x.job);finishSpecialistReview(x.state,x.job.id,r,{organizationId:org,now});assert.throws(()=>finishSpecialistReview(x.state,x.job.id,r,{organizationId:org,now}));
});
test("failed and uncertain results leave tasks open and cannot be accepted",()=>{
 for(const status of ["failed","uncertain"]){const x=claimed();finishSpecialistReview(x.state,x.job.id,{...receipt(x.job),status},{organizationId:org,now});assert.equal(x.task.status,"open");assert.throws(()=>acceptSpecialistReview(x.state,x.job.id,{organizationId:org,actor,expectedRevision:x.job.revision,digest:x.job.digest,outputSha256:x.job.result.outputSha256,now}));}
});
test("acceptance rejects stale revision, altered output, foreign organisation and paused state",()=>{
 for(const change of [x=>x.args.expectedRevision--,x=>x.job.result.output+=" altered",x=>x.args.organizationId="foreign-org",x=>x.state.paused=true]){
  const x=finished();x.args={organizationId:org,actor,expectedRevision:x.job.revision,digest:x.job.digest,outputSha256:x.job.result.outputSha256,now};change(x);assert.throws(()=>acceptSpecialistReview(x.state,x.job.id,x.args));assert.equal(x.task.status,"open");}
});
test("JSON roundtrip preserves draft and permits only explicit owner acceptance",()=>{
 const x=finished(),state=JSON.parse(JSON.stringify(x.state)),job=state.jobs.find(j=>j.id===x.job.id);assert.equal(state.tasks[0].status,"open");
 acceptSpecialistReview(state,job.id,{organizationId:org,actor,expectedRevision:job.revision,digest:job.digest,outputSha256:job.result.outputSha256,now});assert.equal(state.tasks[0].status,"completed");
});

test("interrupted review needs owner reconciliation, denies late receipts and permits a new approval",()=>{
 const x=claimed(),r=receipt(x.job),args={organizationId:org,actor,expectedRevision:x.job.revision,digest:x.job.digest,now};
 assert.throws(()=>reconcileSpecialistReview(x.state,x.job.id,args));
 reconcileSpecialistReview(x.state,x.job.id,{...args,now:now+120001});assert.equal(x.task.status,"open");assert.equal(x.job.status,"failed");
 assert.throws(()=>finishSpecialistReview(x.state,x.job.id,r,{organizationId:org,now:now+120002}));
 const retry=proposeWork(x.state,{...x.input,idempotencyKey:"synthetic-owner-retry-002"},{organizationId:org,actor,now:now+120003});assert.equal(retry.status,"pending");
});
