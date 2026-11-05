import test from "node:test";
import assert from "node:assert/strict";
import {reviewSpecialistTask} from "../src/specialist-task-review.js";
import {chatRoleRoster} from "../src/chat-roles.js";
const context={userId:"synthetic-founder",email:"vision79slu@gmail.com",organizationId:"synthetic-org",organizationName:"Synthetic",ownerAgent:true,hubAdmin:true,allowedSystems:[]};
const snapshot=()=>({generatedAt:new Date().toISOString(),owner:{email:context.email,organizationId:context.organizationId},hubAdmin:{},business:{},platform:{},connections:{}});
const valid=JSON.stringify({steps:["Review the assigned task and identify gaps in the available evidence.","Prepare a short recommendation for the owner's review before any external changes."],questions:["What evidence would demonstrate the requested outcome?"]});
const fake=(raw:string,spy?:{body:any})=>(async(_url:any,req:any)=>{if(spy)spy.body=JSON.parse(req.body);return new Response(JSON.stringify({message:{content:raw}}));}) as typeof fetch;
const body=(role=chatRoleRoster()[0]!)=>({context,role:role.id,skillSha:role.skillSha,title:"Review the approved task scope",detail:"Prepare a bounded advisory review and identify missing evidence."});
for(const role of chatRoleRoster())test(role.id+" produces a bounded local draft using its protected skill",async()=>{
 const spy={body:null as any};const result=await reviewSpecialistTask(body(role),{readSnapshot:(async()=>snapshot()) as any,fetchImpl:fake(valid,spy)});
 assert.equal(result.roleId,role.id);assert.equal(result.skillSha,role.skillSha);assert.equal(result.ownerAccepted,false);assert.equal(result.mode,"read-only");assert.match(result.output,/DRAFT ADVICE/);
 assert.equal(spy.body.tools,undefined);assert.equal(spy.body.options.num_predict,400);assert.match(spy.body.messages[0].content,/read.only/i);
});
test("untrusted roles, missing owner context, extra fields and modified skill pins fail before model invocation",async()=>{
 for(const change of [(x:any)=>x.role="shell",(x:any)=>x.context={...context,ownerAgent:false},(x:any)=>x.skillSha="a".repeat(40),(x:any)=>x.execute=true]){
  const input:any=body();change(input);let called=false;await assert.rejects(reviewSpecialistTask(input,{readSnapshot:(async()=>{called=true;return snapshot();}) as any,fetchImpl:fake(valid)}));assert.equal(called,false);
 }
});
test("unsafe model claims and model outages produce no deliverable",async()=>{
 for(const raw of ["I deployed the changes.",JSON.stringify({steps:["Consider disabling MFA before continuing."],questions:[]})])await assert.rejects(reviewSpecialistTask(body(),{readSnapshot:(async()=>snapshot()) as any,fetchImpl:fake(raw)}),/MODEL_REVIEW_UNAVAILABLE/);
 await assert.rejects(reviewSpecialistTask(body(),{readSnapshot:(async()=>snapshot()) as any,fetchImpl:(async()=>{throw Error("offline")}) as typeof fetch}),/MODEL_REVIEW_UNAVAILABLE/);
});
