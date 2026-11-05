import test from "node:test";
import assert from "node:assert/strict";
import {taskDigest} from "../server/workforce-specialist-delivery.mjs";
import {reconcileTask,reconciliationOptions,saveTaskDeliverable,acceptTaskDeliverable} from "../server/workforce-task-lifecycle.mjs";
import {initialWorkState} from "../server/workforce-actions.mjs";
const ctx={organizationId:"owner-org",actor:"owner",now:1000};
function fixture(title="Marketing plan",detail="Prepare a genuine marketing plan and campaign artwork for review."){
 const state=initialWorkState(),task={id:"task-1",jobId:"origin-1",organizationId:"owner-org",system:"marketing",title,detail,createdAt:"2026-11-05T00:00:00Z",assignedTo:"coo",status:"open"};
 state.tasks.push(task);state.jobs.push({id:task.jobId,organizationId:"owner-org",operation:"create_work_item",status:"succeeded",result:{taskId:task.id},digest:"test-digest",approval:{digest:"test-digest"}});return {state,task};
}
const draft=task=>({taskDigest:taskDigest(task),summary:"Complete documented marketing plan",content:"The actual plan includes a defined audience, verified product claims, a seven-day campaign, approved image assets and a measured enquiry follow-up process.",links:["https://chatgpt.com/library?file_id=libfile_test123&account_id=personal"]});
test("saving a deliverable is not completion and identical retry is idempotent",()=>{
 const {state,task}=fixture(),a=saveTaskDeliverable(state,task.id,draft(task),ctx),b=saveTaskDeliverable(state,task.id,draft(task),ctx);
 assert.equal(task.status,"open");assert.equal(a.id,b.id);assert.equal(task.deliverables.length,1);assert.equal(state.events.length,1);assert.equal(a.accepted,false);
});
test("only exact immutable saved evidence can be accepted",()=>{
 const {state,task}=fixture(),item=saveTaskDeliverable(state,task.id,draft(task),ctx);
 assert.throws(()=>acceptTaskDeliverable(state,task.id,{taskDigest:taskDigest(task),deliverableId:item.id,sha256:"a".repeat(64)},ctx));
 const result=acceptTaskDeliverable(state,task.id,{taskDigest:taskDigest(task),deliverableId:item.id,sha256:item.sha256},ctx);assert.equal(result.status,"completed");assert.equal(result.completion.kind,"owner-accepted-deliverable");
 assert.throws(()=>acceptTaskDeliverable(state,task.id,{taskDigest:taskDigest(task),deliverableId:item.id,sha256:item.sha256},ctx));
});
test("old versions and edited task scopes cannot be accepted",()=>{
 const {state,task}=fixture(),a=saveTaskDeliverable(state,task.id,draft(task),ctx);saveTaskDeliverable(state,task.id,{...draft(task),content:draft(task).content+" A new evidence version."},ctx);
 assert.throws(()=>acceptTaskDeliverable(state,task.id,{taskDigest:taskDigest(task),deliverableId:a.id,sha256:a.sha256},ctx));
 const digest=taskDigest(task);task.detail+=" Scope changed.";
 assert.throws(()=>saveTaskDeliverable(state,task.id,{...draft(task),taskDigest:digest},ctx));
});
test("stored deliverable corruption is rejected",()=>{
 const {state,task}=fixture(),item=saveTaskDeliverable(state,task.id,draft(task),ctx);task.deliverables[0].content+=" tampered";
 assert.throws(()=>acceptTaskDeliverable(state,task.id,{taskDigest:taskDigest(task),deliverableId:item.id,sha256:item.sha256},ctx));
});
test("cross-organisation and paused mutations fail closed",()=>{
 const {state,task}=fixture();assert.throws(()=>saveTaskDeliverable(state,task.id,draft(task),{...ctx,organizationId:"foreign-org"}));state.paused=true;assert.throws(()=>saveTaskDeliverable(state,task.id,draft(task),ctx));
});
test("unsafe links and oversized or missing deliverables are rejected",()=>{
 for(const link of ["javascript:alert(1)","https://evil.example/file","https://chatgpt.com/library?file_id=libfile_test&account_id=personal&token=bad","https://github.com/MrFixITslu/V79hub/blob/main/README.md?secret=bad"]){
  const {state,task}=fixture();assert.throws(()=>saveTaskDeliverable(state,task.id,{...draft(task),links:[link]},ctx));
 }
 const {state,task}=fixture();assert.throws(()=>saveTaskDeliverable(state,task.id,{...draft(task),content:"tiny"},ctx));assert.throws(()=>saveTaskDeliverable(state,task.id,{...draft(task),content:"x".repeat(30001)},ctx));
});
test("approved exact creation test closes only its evidenced recording scope",()=>{
 const {state,task}=fixture("G2 supervised acceptance test","Record this acceptance task only. Do not modify code, deploy services, or change customer data.");
 assert.equal(reconciliationOptions(state,task,ctx.organizationId).creationTest,true);
 const out=reconcileTask(state,task.id,{taskDigest:taskDigest(task),decision:"verify_creation_test",reason:"Approved worker created exactly this recorded COO task.",relatedTaskId:null},ctx);
 assert.equal(out.status,"completed");assert.equal(out.completion.kind,"verified-task-creation-test");assert.equal(out.completion.recordedTaskId,task.id);
});
test("business work and broken original approval cannot be called a verified test",()=>{
 const {state,task}=fixture();assert.throws(()=>reconcileTask(state,task.id,{taskDigest:taskDigest(task),decision:"verify_creation_test",reason:"Only task creation has been observed so far.",relatedTaskId:null},ctx));
 state.jobs[0].approval.digest="bad";assert.throws(()=>saveTaskDeliverable(state,task.id,draft(task),ctx));
});
test("duplicate closure preserves the retained exact task and rejects foreign or self targets",()=>{
 const {state,task}=fixture();const other={...task,id:"task-2",jobId:"origin-2"};state.tasks.push(other);state.jobs.push({...state.jobs[0],id:other.jobId,result:{taskId:other.id}});
 const input={taskDigest:taskDigest(task),decision:"supersede_duplicate",reason:"Keep the exact newer task and its existing evidence.",relatedTaskId:task.id};assert.throws(()=>reconcileTask(state,task.id,input,ctx));
 other.organizationId="foreign-org";assert.throws(()=>reconcileTask(state,task.id,{...input,relatedTaskId:other.id},ctx));other.organizationId=ctx.organizationId;
 const out=reconcileTask(state,task.id,{...input,relatedTaskId:other.id},ctx);assert.equal(out.status,"superseded");assert.equal(other.status,"open");assert.equal(state.tasks.length,2);
});
test("an unresolved running review prevents closure or evidence replacement",()=>{
 const {state,task}=fixture();state.jobs.push({organizationId:ctx.organizationId,operation:"run_specialist_review",status:"running",payload:{taskId:task.id}});
 assert.throws(()=>saveTaskDeliverable(state,task.id,draft(task),ctx));assert.throws(()=>reconcileTask(state,task.id,{taskDigest:taskDigest(task),decision:"cancel",reason:"No further work should run for this entry.",relatedTaskId:null},ctx));
});
test("accepted actual evidence supersedes generic advice without forging model acceptance",()=>{
 const {state,task}=fixture();state.jobs.push({id:"old-review",organizationId:ctx.organizationId,operation:"run_specialist_review",status:"succeeded",revision:4,payload:{taskId:task.id},result:{kind:"specialist-review-draft",ownerAccepted:false,output:"Old advice"}});
 const item=saveTaskDeliverable(state,task.id,draft(task),ctx);acceptTaskDeliverable(state,task.id,{taskDigest:taskDigest(task),deliverableId:item.id,sha256:item.sha256},ctx);
 assert.equal(state.jobs[1].result.ownerAccepted,false);assert.equal(state.jobs[1].result.supersededByDeliverable,item.id);assert.equal(state.jobs[1].result.output,"Old advice");
});
