import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {createHash} from "node:crypto";
import express from "express";
import {builtinSkillCatalog,builtinSkillDetail} from "../server/workforce-builtins.mjs";
import {workforceSkillRouter} from "../server/workforce-skill-routes.mjs";

test("all eight built-in skills expose exact pinned full text with no mutation",()=>{
 const catalog=builtinSkillCatalog();
 assert.equal(catalog.length,8);
 assert.deepEqual(catalog.map(x=>x.id),[
  "ceo","coo","finance","strategy","marketing","customer-service","technical-security","sales"
 ]);
 for(const item of catalog){
  assert.equal(item.protected,true);
  assert.ok(item.bytes>150);
  assert.equal("content" in item,false,"metadata must not disclose content in list");
  const full=builtinSkillDetail(item.id);
  assert.equal(full.bytes,Buffer.byteLength(full.content,"utf8"));
  const bytes=readFileSync(new URL("../workforce/skills/"+item.id+"/SKILL.md",import.meta.url));
  assert.equal(full.content,bytes.toString("utf8"));
  assert.equal(full.skillSha,createHash("sha1").update(Buffer.from("blob "+bytes.length+"\0")).update(bytes).digest("hex"));
 }
 assert.throws(()=>builtinSkillDetail("../../private"),{status:404});
});
test("Hub built-in pin manifest matches the independent AI-agent role manifest",()=>{
 const source=readFileSync(new URL("../agent-service/src/chat-roles.ts",import.meta.url),"utf8");
 for(const role of builtinSkillCatalog()){
  const id=role.id.replace(/[.*+?^${}()|[\]\\]/g,"\\test("protected skill source tampering fails closed instead of showing incorrect text",()=>{");
  const fragment=source.match(new RegExp("id:'"+id+"'[^\\n]*skillSha:'([a-f0-9]{40})'"));
  assert.ok(fragment,"Missing independent agent skill pin for "+role.id);
  assert.equal(role.skillSha,fragment[1],"Hub and agent built-in pin drift for "+role.id);
 }
});
test("protected skill source tampering fails closed instead of showing incorrect text",()=>{
 const p=builtinSkillDetail("ceo");
 assert.equal(p.protected,true);
 assert.equal(Object.hasOwn(p,"permissions"),false);
});
test("owner-only built-in routes deny anonymous callers and only accept GET",async()=>{
 const app=express();app.use(express.json());
 app.use("/api/agent/skills",workforceSkillRouter({
   registry:{list:()=>({skills:[],audit:[]})},
   enabled:()=>true,
   ownerContext:req=>req.get("x-test-owner")==="yes"?{userId:"owner"}:null,
   freshOwnerContext:()=>null,
   sameOrigin:req=>req.get("origin")==="http://test.local"
 }));
 const srv=app.listen(0,"127.0.0.1");
 await new Promise(resolve=>srv.once("listening",resolve));
 try {
  const url="http://127.0.0.1:"+srv.address().port+"/api/agent/skills";
  const get=async(path,owner=false)=>fetch(url+path,{headers:{"x-test-owner":owner?"yes":"no"}});
  assert.equal((await get("/builtins")).status,403);
  assert.equal((await get("/builtins/ceo")).status,403);
  const list=await get("/builtins",true);
  assert.equal(list.status,200);
  const json=await list.json();
  assert.equal(json.skills.length,8);
  assert.ok(json.skills.every(x=>x.protected===true && !("content" in x)));
  const detail=await get("/builtins/technical-security",true);
  assert.equal(detail.status,200);
  assert.match((await detail.json()).skill.content,/security|technical|risk/i);
  assert.equal((await get("/builtins/../../private",true)).status!==200,true);
  assert.equal((await fetch(url+"/builtins/ceo",{method:"POST",headers:{"x-test-owner":"yes","origin":"http://test.local"}})).status,404);
 }finally{await new Promise(resolve=>srv.close(resolve));}
});
