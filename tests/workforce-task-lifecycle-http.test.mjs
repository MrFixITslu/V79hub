import test from "node:test";
import assert from "node:assert/strict";
import express from "express";
import {workforceActionRouters} from "../server/workforce-action-routes.mjs";
import {taskDigest} from "../server/workforce-specialist-delivery.mjs";
test("task evidence HTTP requires owner origin and fresh MFA for acceptance",async()=>{
 const now=1000000,state={version:1,paused:false,jobs:[],tasks:[],events:[]};
 const task={id:"task-1",jobId:"job-1",organizationId:"owner-org",system:"marketing",title:"Marketing plan",detail:"Prepare the actual plan and image assets for owner review.",createdAt:"2026-11-05T00:00:00Z",assignedTo:"coo",status:"open"};
 state.tasks.push(task);state.jobs.push({id:"job-1",organizationId:"owner-org",operation:"create_work_item",status:"succeeded",result:{taskId:task.id},digest:"synthetic",approval:{digest:"synthetic"}});
 const ledger={read:async()=>structuredClone(state),transact:async fn=>fn(state)};
 const app=express();app.use(express.json());app.use((req,_res,next)=>{req.user={mfaVerifiedAt:now-Number(req.get("x-test-age")||0)};next();});
 const routes=workforceActionRouters({ledger,enabled:()=>true,ownerContext:req=>req.get("x-test-owner")==="yes"?{organizationId:"owner-org",userId:"owner"}:null,sameOrigin:req=>req.get("origin")==="https://owner.test",workerToken:()=>"synthetic-worker-boundary-not-production",ownerOrganizationId:()=>"owner-org",ownerReady:()=>true,now:()=>now});
 app.use("/owner",routes.owner);app.use("/worker",routes.worker);
 const server=app.listen(0,"127.0.0.1");await new Promise(r=>server.once("listening",r));const base="http://127.0.0.1:"+server.address().port;
 const body={taskDigest:taskDigest(task),summary:"Complete marketing plan and artwork",content:"Completed plan with a defined audience, verified claims, campaign schedule, lead qualification and approved image assets. Ready for a separate owner acceptance decision.",links:[]};
 const call=(path,data,headers={})=>fetch(base+path,{method:"POST",headers:{"content-type":"application/json","x-test-owner":"yes",origin:"https://owner.test",...headers},body:JSON.stringify(data)});
 try{
  assert.equal((await call("/owner/tasks/task-1/deliverable",body,{"x-test-owner":"no"})).status,403);
  assert.equal((await call("/owner/tasks/task-1/deliverable",body,{origin:"https://foreign.test"})).status,403);
  const saved=await call("/owner/tasks/task-1/deliverable",body);assert.equal(saved.status,201);const item=(await saved.json()).deliverable;
  const acceptance={taskDigest:taskDigest(task),deliverableId:item.id,sha256:item.sha256};
  assert.equal((await call("/owner/tasks/task-1/accept-deliverable",acceptance,{"x-test-age":"300001"})).status,403);assert.equal(task.status,"open");
  assert.equal((await call("/owner/tasks/task-1/reconcile",{taskDigest:taskDigest(task),decision:"cancel",reason:"This would be an owner reconciliation.",relatedTaskId:null},{"x-test-age":"300001"})).status,403);
  assert.equal((await call("/owner/tasks/task-1/accept-deliverable",acceptance)).status,200);assert.equal(task.status,"completed");
  assert.equal((await call("/worker/tasks/task-1/accept-deliverable",acceptance)).status,403);
 }finally{server.closeAllConnections();await new Promise(r=>server.close(r));}
});
