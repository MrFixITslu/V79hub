import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import os from "node:os";
import express from "express";
import {createSkillRegistry} from "../server/workforce-skill-registry.mjs";
import {workforceSkillRouter} from "../server/workforce-skill-routes.mjs";

test("owner API refuses foreign callers, cross-origin writes and stale MFA; records server actor",async()=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),"v79-skill-http-"));
 const registry=createSkillRegistry({file:path.join(root,"skills.json"),secret:"local-test-secret-not-used-by-production-00123456789"});
 let enabled=true;
 const app=express();app.use(express.json());
 app.use("/skills",workforceSkillRouter({
  registry, enabled:()=>enabled,
  ownerContext:req=>req.get("x-test-owner")==="yes"?{userId:"authenticated-owner"}:null,
  freshOwnerContext:req=>req.get("x-test-fresh-mfa")==="yes"?{userId:"authenticated-owner"}:null,
  sameOrigin:req=>req.get("origin")==="http://test.local"
 }));
 const server=app.listen(0,"127.0.0.1");
 try{
  await new Promise(resolve=>server.once("listening",resolve));
  const url="http://127.0.0.1:"+server.address().port+"/skills";
  const request=async(relative="",method="GET",body,headers={})=>{
   const response=await fetch(url+relative,{
    method,headers:{"x-test-owner":"yes","origin":"http://test.local",...(body?{"content-type":"application/json"}:{}),...headers},
    ...(body?{body:JSON.stringify(body)}:{})
   });
   return {status:response.status,data:await response.json()};
  };
  assert.equal((await request("","GET",undefined,{"x-test-owner":"no"})).status,403);
  assert.equal((await request("","POST",{name:"A new skill",content:"# draft"},{"origin":"http://wrong.local"})).status,403);
  assert.equal((await request("","POST",{name:"A new skill",content:"# draft",actor:"spoofed"})).status,400);
  const created=await request("","POST",{name:"A new skill",content:"# draft"});
  assert.equal(created.status,201);
  const id=created.data.skill.id;
  assert.equal((await request("/"+id+"/activate","POST",{version:1,workers:["marketing"],expectedRevision:1})).status,403);
  assert.equal((await request("/"+id+"/activate","POST",{version:1,workers:["marketing"],expectedRevision:1},{"x-test-fresh-mfa":"yes"})).status,200);
  assert.equal(registry.list().audit[0].actor,"authenticated-owner");
  assert.equal((await request("/"+id+"/pause","POST",{expectedRevision:2})).status,403);
  assert.equal((await request("/"+id+"/pause","POST",{expectedRevision:2},{"x-test-fresh-mfa":"yes"})).status,200);
  enabled=false;
  assert.equal((await request()).status,503);
 }finally{
  await new Promise(resolve=>server.close(resolve));
  fs.rmSync(root,{recursive:true,force:true});
 }
});
