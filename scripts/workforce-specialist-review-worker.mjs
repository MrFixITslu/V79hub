#!/usr/bin/env node
// Run only inside the Hub container via the host oneshot unit. Credentials stay
// inside this process. One approved advisory review per invocation; no tools.
import fs from "node:fs";
const pressure=fs.readFileSync("/proc/pressure/io","utf8");
const avg=kind=>Number(new RegExp(kind+" avg10=([0-9.]+)").exec(pressure)?.[1]||0);
if(avg("some")>15||avg("full")>10){console.log("SPECIALIST_REVIEW=DEFERRED_HOST_IO_PRESSURE");process.exit(0);}
const workToken=fs.readFileSync(process.env.V79_WORKFORCE_TOKEN_FILE||"/run/secrets/v79-workforce-token","utf8").trim();
const agentToken=String(process.env.V79_AGENT_API_TOKEN||"").trim()||fs.readFileSync("/run/secrets/v79-agent-token","utf8").trim();
if(workToken.length<32||agentToken.length<32)throw Error("Worker credentials unavailable");
const headers={"content-type":"application/json","x-v79-workforce-token":workToken};
async function post(path,body){
 const r=await fetch("http://127.0.0.1:3040/internal/workforce/"+path,{
  method:"POST",headers,body:JSON.stringify(body),redirect:"error",signal:AbortSignal.timeout(10000)});
 if(!r.ok)throw Error("WORKFORCE_REQUEST_REJECTED");
 const text=await r.text();if(Buffer.byteLength(text)>50000)throw Error("OVERSIZED_WORKFORCE_RESPONSE");
 return JSON.parse(text);
}
let job;
try{
 const claim=await post("claim-specialist-review",{});job=claim.job;
 if(!job){console.log("SPECIALIST_REVIEW=NO_APPROVED_JOB");process.exit(0);}
 const identity=JSON.parse(fs.readFileSync("/app/data/pos-identity.json","utf8"));
 if(identity.organizationId!==job.organizationId||process.env.V79_REQUIRE_ADMIN_MFA!=="1")throw Error("OWNER_SCOPE_UNAVAILABLE");
 const context={userId:identity.ownerUserId,email:process.env.V79_HUB_ADMIN_EMAIL,
  organizationId:identity.organizationId,organizationName:"V79 Digital",ownerAgent:true,hubAdmin:true,
  allowedSystems:["hub","website","lasertag","marketing","pos","tiquet","ffpro","academy","games"]};
 const r=await fetch("http://v79-business-agent:3055/api/agent/task-review",{
  method:"POST",redirect:"error",headers:{"content-type":"application/json","x-v79-agent-token":agentToken},
  body:JSON.stringify({context,role:job.payload.specialist,skillSha:job.payload.skillSha,
   system:claim.task.system,title:claim.task.title,detail:claim.task.detail}),signal:AbortSignal.timeout(110000)});
 const raw=await r.text();if(Buffer.byteLength(raw)>16000)throw Error("OVERSIZED_REVIEW");
 const review=JSON.parse(raw);
 if(!r.ok||review.mode!=="read-only"||review.kind!=="specialist-review-draft"||review.modelProvider!=="ollama"||
  review.roleId!==job.payload.specialist||review.skillSha!==job.payload.skillSha||review.ownerAccepted!==false||
  typeof review.output!=="string"||typeof review.model!=="string")throw Error("INVALID_REVIEW_RESULT");
 await post(job.id+"/specialist-receipt",{claimToken:job.claim.token,digest:job.digest,status:"succeeded",
  output:review.output,model:review.model,skillSha:review.skillSha});
 console.log("SPECIALIST_REVIEW=DRAFT_SAVED_OWNER_ACCEPTANCE_REQUIRED");
}catch{
 if(job){
  try{await post(job.id+"/specialist-receipt",{claimToken:job.claim.token,digest:job.digest,status:"failed",
   output:"Specialist review unavailable. No task deliverable was accepted and no external action was performed.",
   model:"unavailable",skillSha:job.payload.skillSha});console.log("SPECIALIST_REVIEW=FAILED_RECORDED");}
  catch{console.log("SPECIALIST_REVIEW=RECONCILIATION_REQUIRED_DO_NOT_RETRY");}
 }else console.log("SPECIALIST_REVIEW=UNAVAILABLE");
 process.exitCode=1;
}
