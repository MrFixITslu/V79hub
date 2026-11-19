import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import express from "express";
import {execFileSync} from "node:child_process";
import {createSkillRegistry} from "../server/workforce-skill-registry.mjs";
import {createPackageStore} from "../server/workforce-skill-packages.mjs";
import {workforceSkillRouter} from "../server/workforce-skill-routes.mjs";
import {scheduledSkillRouter} from "../server/workforce-skill-scheduled.mjs";

const token="worker-test-shared-secret-0123456789abcdefgh";
const archive=()=>execFileSync("python3",["-c",`import io,zipfile,base64
b=io.BytesIO()
with zipfile.ZipFile(b,'w',zipfile.ZIP_DEFLATED) as z:
 z.writestr('SKILL.md','# Review-only scheduled instructions')
 z.writestr('scripts/check.py','print("sandbox-only")')
print(base64.b64encode(b.getvalue()).decode())`]).toString().trim();

test("package owner routes require same origin and fresh MFA; scheduled worker sees only pinned guidance",async()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),"v79-skill-http-"));
 const secret="local-skill-hmac-key-for-isolated-route-tests-001";
 const registry=createSkillRegistry({file:path.join(dir,"skills.json"),secret});
 const packages=createPackageStore({directory:path.join(dir,"packages"),secret});
 const app=express(); app.use(express.json({limit:"2mb"}));
 app.use("/skills",workforceSkillRouter({registry,packages,enabled:()=>true,
  ownerContext:req=>req.get("x-owner")==="yes"?{userId:"owner-user"}:null,
  freshOwnerContext:req=>req.get("x-fresh")==="yes"?{userId:"owner-user"}:null,
  sameOrigin:req=>req.get("origin")==="http://test.local"}));
 app.use("/internal/scheduled",scheduledSkillRouter({packages,enabled:()=>true,workerToken:()=>token}));
 const server=app.listen(0,"127.0.0.1");
 try{
  await new Promise(resolve=>server.once("listening",resolve));
  const url="http://127.0.0.1:"+server.address().port;
  const request=async(route,method="GET",body,headers={})=>{
   const resp=await fetch(url+route,{method,headers:{"x-owner":"yes",origin:"http://test.local",
    ...(body?{"content-type":"application/json"}:{}),...headers},...(body?{body:JSON.stringify(body)}:{})});
   return {status:resp.status,data:await resp.json()};
  };
  const zip=archive();
  assert.equal((await request("/skills/packages/import","POST",{name:"test-package",archive:zip},{"x-owner":"no"})).status,403);
  assert.equal((await request("/skills/packages/import","POST",{name:"test-package",archive:zip},{origin:"https://wrong.local"})).status,403);
  const imported=await request("/skills/packages/import","POST",{name:"test-package",archive:zip});
  assert.equal(imported.status,201);
  const pkg=imported.data.package;
  assert.equal(pkg.status,"quarantined");
  assert.equal((await request("/skills/packages/"+pkg.id+"/approve","POST",{sha256:pkg.sha256,expectedRevision:1})).status,403);
  const approved=await request("/skills/packages/"+pkg.id+"/approve","POST",{sha256:pkg.sha256,expectedRevision:1},{"x-fresh":"yes"});
  assert.equal(approved.status,200);
  assert.equal((await request("/skills/packages/"+pkg.id+"/configure","POST",
   {hooks:["package-integrity"],schedules:["coo-daily"],expectedRevision:2})).status,403);
  const assigned=await request("/skills/packages/"+pkg.id+"/configure","POST",
   {hooks:["package-integrity"],schedules:["coo-daily"],expectedRevision:2},{"x-fresh":"yes"});
  assert.equal(assigned.status,200);
  const anon=await request("/internal/scheduled/coo-daily","GET",undefined,{origin:"", "x-owner":"no"});
  assert.equal(anon.status,403);
  const valid=await request("/internal/scheduled/coo-daily","GET",undefined,
    {origin:"","x-v79-workforce-token":token});
  assert.equal(valid.status,200);
  assert.equal(valid.data.packages.length,1);
  assert.equal(valid.data.packages[0].sha256,pkg.sha256);
  assert.equal(valid.data.packages[0].skill,"# Review-only scheduled instructions");
  assert.doesNotMatch(JSON.stringify(valid.data),/check.py/);
  assert.equal((await request("/internal/scheduled/coo-daily","GET",undefined,
    {origin:"https://wrong.local","x-v79-workforce-token":token})).status,403);
  assert.equal((await request("/internal/scheduled/other","GET",undefined,
    {origin:"","x-v79-workforce-token":token})).status,400);
  assert.equal((await request("/skills/packages/"+pkg.id+"/revoke","POST",{expectedRevision:3})).status,403);
  const revoked=await request("/skills/packages/"+pkg.id+"/revoke","POST",{expectedRevision:3},{"x-fresh":"yes"});
  assert.equal(revoked.status,200);
  assert.equal((await request("/internal/scheduled/coo-daily","GET",undefined,
    {origin:"","x-v79-workforce-token":token})).data.packages.length,0);

 }finally{await new Promise(resolve=>server.close(resolve));fs.rmSync(dir,{recursive:true,force:true});}
});
