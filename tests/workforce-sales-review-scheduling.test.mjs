import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import express from "express";
import {execFileSync} from "node:child_process";
import {createPackageStore} from "../server/workforce-skill-packages.mjs";
import {workforceSkillRouter} from "../server/workforce-skill-routes.mjs";
import {scheduledSkillRouter} from "../server/workforce-skill-scheduled.mjs";

const secret="isolated-unit-test-independent-hmac-secret-20261107";
const workerToken="local-sales-review-worker-token-32-plus-characters";
const makeZip=(name)=>execFileSync("python3",["-c",[
 "import io,zipfile,base64",
 "b=io.BytesIO()",
 "with zipfile.ZipFile(b,'w',zipfile.ZIP_DEFLATED) as z:",
 " z.writestr('SKILL.md','# Sales guidance for "+name+"\\nOnly draft outreach; no sends, no spending.')",
 "print(base64.b64encode(b.getvalue()).decode())"
].join("\n")]).toString().trim();

test("Sales Review is an isolated, owner-approved, max-two scheduled guidance profile", async()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),"v79-sales-zip-review-"));
 const store=createPackageStore({directory:path.join(dir,"packages"),secret});
 try{
  const records=[];
  for(const label of ["qualified-leads","outreach-copy","third-unapproved"]){
   const imported=await store.import({name:label,archive:makeZip(label)},"owner");
   const approved=await store.approve(imported.id,{sha256:imported.sha256,expectedRevision:imported.revision},"owner");
   records.push(approved);
  }
  const first=await store.configure(records[0].id,{hooks:["package-integrity"],schedules:["sales-review"],expectedRevision:records[0].revision},"owner");
  const second=await store.configure(records[1].id,{hooks:["package-integrity"],schedules:["sales-review"],expectedRevision:records[1].revision},"owner");
  await assert.rejects(store.configure(records[2].id,{hooks:[],schedules:["sales-review"],expectedRevision:records[2].revision},"owner"),{status:409});
  assert.deepEqual(store.scheduledSnapshot("sales-review").packages.map(p=>p.id).sort(),[first.id,second.id].sort());
  for(const job of ["marketing-review","technology-review","coo-daily","ceo-daily"]){
    assert.equal(store.scheduledSnapshot(job).packages.length,0);
  }
  assert.throws(()=>store.scheduledSnapshot("made-up-agent"),{status:400});
  const removed=await store.configure(first.id,{hooks:[],schedules:[],expectedRevision:first.revision},"owner");
  assert.deepEqual(removed.schedules,[]);
  assert.equal(store.scheduledSnapshot("sales-review").packages.length,1);
 } finally {fs.rmSync(dir,{recursive:true,force:true});}
});

test("Sales Review HTTP requires trusted worker token; configuration requires fresh owner MFA", async()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),"v79-sales-review-http-"));
 const store=createPackageStore({directory:path.join(dir,"packages"),secret});
 const registry={}; // Only the package API routes are exercised in this test.
 const app=express();app.use(express.json({limit:"2mb"}));
 app.use("/skills",workforceSkillRouter({registry,packages:store,enabled:()=>true,
  ownerContext:req=>req.get("x-owner")==="yes"?{userId:"founder"}:null,
  freshOwnerContext:req=>req.get("x-fresh")==="yes"?{userId:"founder"}:null,
  sameOrigin:req=>req.get("origin")==="http://testing.local"}));
 app.use("/internal/scheduled",scheduledSkillRouter({packages:store,enabled:()=>true,workerToken:()=>workerToken}));
 const server=app.listen(0,"127.0.0.1");
 try {
  await new Promise(resolve=>server.once("listening",resolve));
  const url="http://127.0.0.1:"+server.address().port;
  const imported=await store.import({name:"sales-outreach",archive:makeZip("sales-outreach")},"founder");
  const pkg=await store.approve(imported.id,{sha256:imported.sha256,expectedRevision:1},"founder");
  const route="/skills/packages/"+pkg.id+"/configure",body={hooks:["package-integrity"],schedules:["sales-review"],expectedRevision:pkg.revision};
  const req=async(headers)=>fetch(url+route,{method:"POST",headers:{"content-type":"application/json",...headers},body:JSON.stringify(body)});
  assert.equal((await req({origin:"http://testing.local","x-owner":"yes"})).status,403);
  assert.equal((await req({origin:"http://evil.local","x-owner":"yes","x-fresh":"yes"})).status,403);
  assert.equal((await req({origin:"http://testing.local","x-owner":"yes","x-fresh":"yes"})).status,200);
  const get=async(headers)=>fetch(url+"/internal/scheduled/sales-review",{headers});
  assert.equal((await get({})).status,403);
  assert.equal((await get({cookie:"session=x","x-v79-workforce-token":workerToken})).status,403);
  assert.equal((await get({origin:"http://evil.local","x-v79-workforce-token":workerToken})).status,403);
  const allowed=await get({"x-v79-workforce-token":workerToken});
  assert.equal(allowed.status,200);
  const payload=await allowed.json();
  assert.equal(payload.job,"sales-review");
  assert.equal(payload.packages.length,1);
  assert.equal(payload.packages[0].sha256,pkg.sha256);
  assert.match(payload.packages[0].skill,/Only draft outreach/);
  assert.equal(JSON.stringify(payload).includes("archive"),false);
 } finally {await new Promise(resolve=>server.close(resolve));fs.rmSync(dir,{recursive:true,force:true});}
});
