import test from "node:test";
import assert from "node:assert/strict";
import crypto from "node:crypto";
import os from "node:os";
import path from "node:path";
import fs from "node:fs";
import express from "express";
import { registerSentinelQaRoutes } from "../server/sentinel-qa-routes.mjs";
import { createHubStorePersistence } from "../server/runtime-store.mjs";
import { createSentinelWriteFence } from "../server/sentinel-write-fence.mjs";

/**
 * Executes the SAME routes wired by server.ts against localhost and a
 * disposable JSON store. No V79 server, accounts, DNS or external endpoints.
 */
function fixture() {
  const operatorId="platform-owner-fixture";
  const customerId="existing-customer-fixture";
  return {
    operatorId,customerId,
    users:[
      {id:operatorId,username:"operator-fixture@example.invalid",password:"pre-existing-owner-hash"},
      {id:customerId,username:"existing-customer@example.invalid",password:"existing-hash"},
    ],
    store:{
      users:[
        {id:operatorId,username:"operator-fixture@example.invalid",password:"pre-existing-owner-hash"},
        {id:customerId,username:"existing-customer@example.invalid",password:"existing-hash"},
      ],
      workspace:{companyName:"Existing V79 Business"},
      ecosystemApps:[],
      organizations:[{id:"platform-owner-org",name:"V79 Owner",slug:"v79-owner"},
        {id:"existing-customer-org",name:"Existing Customer",slug:"existing-customer"}],
      memberships:[{organizationId:"platform-owner-org",userId:operatorId,role:"owner"},
        {organizationId:"existing-customer-org",userId:customerId,role:"owner"}],
      appEntitlements:[],organizationPlans:[],trialReminderEvents:[],
      billingOrders:[],billingPaymentEvents:[],ownerInvitations:[],teamInvitations:[],
      appTenantMappings:[],passwordResetRequests:[],
      auditEvents:[{id:"original-audit",organizationId:"existing-customer-org",
        actorUserId:customerId,type:"existing_activity",details:{}}],
    }
  };
}
function hashPassword(password){
 const salt=crypto.randomBytes(16).toString("hex");
 return "scrypt:"+salt+":"+crypto.scryptSync(password,salt,64).toString("hex");
}
async function harness(){
 const fx=fixture();
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),"v79-sentinel-qa-http-"));
 const storeFile=path.join(dir,"sandbox-store.json");
 const persistence=createHubStorePersistence({backend:"json",storeFile});
 let store=await persistence.load(x=>x,()=>structuredClone(fx.store));
 const initial=structuredClone(store);
 const sessions=new Map([
  ["operator",{userId:fx.operatorId,organizationId:"platform-owner-org",role:"owner"}],
  ["customer",{userId:fx.customerId,organizationId:"existing-customer-org",role:"owner"}],
 ]);
 let persistCount=0;
 let failNextCommit=false;
 let blockCommit=null;
 let resumeOrdinaryWrite=null;
 const app=express();
 const fence=createSentinelWriteFence();
 app.disable("x-powered-by");
 app.use(fence.middleware);
 app.use(express.json({limit:"32kb"}));
 // Isolated equivalent of Hub's earlier requireAuth middleware.
 app.use("/api",(req,res,next)=>{
  const token=(req.get("authorization")||"").replace(/^Bearer /,"");
  const current=sessions.get(token);
  if(!current)return res.status(401).json({error:"Session expired or invalid"});
  if(!store.memberships.some(m=>m.organizationId===current.organizationId &&
        m.userId===current.userId && m.role!=="revoked")) {
    return res.status(401).json({error:"Membership no longer active"});
  }
  req.user=current;
  next();
 });
 const config={
  requirePlatformOperator:(req,res,next)=>{
    if(req.user.userId!==fx.operatorId || req.user.role!=="owner"){
      return res.status(403).json({error:"Platform operator access required"});
    }
    next();
  },
  sameOriginMutation:(req)=>req.get("origin")===`http://127.0.0.1:${server.address().port}`,
  getStore:()=>store,
  hashPassword,
  beginExclusive:fence.beginExclusive,
  commitStore:async nextStore=>{
    const release=fence.beginStoreSave({sentinel:true});
    try {
      if(blockCommit)await blockCommit;
      if(failNextCommit){failNextCommit=false; throw new Error("simulated store commit failure");}
      await persistence.save(nextStore);
      store=nextStore; persistCount++;
    } finally { release(); }
  },
  deleteSessionsWhere:(predicate)=>{
    for(const [token,s] of sessions){if(predicate(s))sessions.delete(token);}
  },
 };
 registerSentinelQaRoutes(app,config);
 app.post("/api/test/ordinary-write",(_req,res)=>res.json({ok:true}));
 app.post("/api/test/slow-write",async(_req,res)=>{
   const end=fence.beginStoreSave();
   try { await new Promise(resolve=>{resumeOrdinaryWrite=resolve;}); res.json({ok:true}); }
   finally {end();resumeOrdinaryWrite=null;}
 });
 // Loopback-only, ephemeral OS-assigned port: not reachable from LAN.
 const server=await new Promise((resolve,reject)=>{
   const s=app.listen(0,"127.0.0.1",()=>resolve(s));
   s.once("error",reject);
 });
 assert.equal(server.address().address,"127.0.0.1");
 const base=`http://127.0.0.1:${server.address().port}`;
 const request=async (route,{method="GET",token="operator",body,origin=true}={})=>{
  const headers={authorization:"Bearer "+token};
  if(origin)headers.origin=base;
  if(body!==undefined)headers["content-type"]="application/json";
  const res=await fetch(base+route,{method,headers,body:body===undefined?undefined:JSON.stringify(body),redirect:"manual"});
  let json;try{json=await res.json();}catch{json=null;}
  return {status:res.status,json,headers:res.headers};
 };
 const close=()=>new Promise(resolve=>server.close(async()=>{await persistence.close();fs.rmSync(dir,{recursive:true,force:true});resolve();}));
 return {request,close,initial,fx,storeFile,dir,sessions,
  getStore:()=>store,getPersistCount:()=>persistCount,
  simulateFailure:()=>{failNextCommit=true;},
  releaseOrdinaryWrite:()=>{if(resumeOrdinaryWrite)resumeOrdinaryWrite();},
  deferNextCommit:()=>{let resume;blockCommit=new Promise(r=>{resume=r;});return ()=>{blockCommit=null;resume();};}
 };
}
const flags=["V79_SENTINEL_QA_CREATE_ENABLED","V79_SENTINEL_QA_CLEANUP_ENABLED"];
const beforeFlags=flags.map(k=>process.env[k]);
function setFlags(create,cleanup) {
 if(create===null)delete process.env[flags[0]];else process.env[flags[0]]=create;
 if(cleanup===null)delete process.env[flags[1]];else process.env[flags[1]]=cleanup;
}
function restored(){for(let i=0;i<flags.length;i++)if(beforeFlags[i]===undefined)delete process.env[flags[i]];else process.env[flags[i]]=beforeFlags[i];}

test("real staging route HTTP lifecycle on isolated 127.0.0.1 only",async(t)=>{
 const h=await harness();
 t.after(async()=>{restored();await h.close();});
 const create="/api/admin/sentinel-qa/organizations";
 const ack={confirm:"CREATE ISOLATED SENTINEL QA"};
 setFlags(null,null);
 await t.test("default flags deny endpoints, even for operator",async()=>{
  assert.equal((await h.request(create,{method:"POST",body:ack})).status,404);
  assert.equal((await h.request(create+"/00000000-0000-4000-8000-000000000001/cleanup-preview")).status,404);
  assert.deepEqual(h.getStore(),h.initial);
 });
 setFlags("1","1");
 await t.test("missing/bad authorization and invalid mutation origin rejected",async()=>{
  assert.equal((await h.request(create,{method:"POST",token:"none",body:ack})).status,401);
  assert.equal((await h.request(create,{method:"POST",token:"customer",body:ack})).status,403);
  assert.equal((await h.request(create,{method:"POST",body:ack,origin:false})).status,403);
  assert.equal((await h.request(create,{method:"POST",body:{confirm:"wrong"}})).status,400);
  assert.equal((await h.request(create,{method:"POST",body:{...ack,email:"someone@example.com"}})).status,400);
  assert.equal((await h.request(create,{method:"POST",body:{...ack,appIds:["app-ffpro"]}})).status,400);
  assert.deepEqual(h.getStore(),h.initial);
 });
 await t.test("ongoing ordinary Hub write prevents Sentinel creation",async()=>{
  const running=h.request("/api/test/slow-write",{method:"POST"});
  await new Promise(r=>setTimeout(r,25));
  const refusal=await h.request(create,{method:"POST",body:ack});
  assert.equal(refusal.status,409);
  h.releaseOrdinaryWrite();
  assert.equal((await running).status,200);
  assert.deepEqual(h.getStore(),h.initial);
 });
 await t.test("failed store commit changes nothing",async()=>{
  h.simulateFailure();
  assert.equal((await h.request(create,{method:"POST",body:ack})).status,503);
  assert.deepEqual(h.getStore(),h.initial);
  assert.equal(h.getPersistCount(),0);
 });
 let created;
 await t.test("create three test identities with no app/email side effects",async()=>{
  const r=await h.request(create,{method:"POST",body:ack});
  assert.equal(r.status,201);
  assert.equal(r.headers.get("cache-control"),"no-store");
  created=r.json;
  assert.match(created.organization.name,/^Sentinel-QA-[0-9a-f-]+$/);
  assert.equal(created.testAccounts.length,3);
  assert.deepEqual(created.testAccounts.map(x=>x.role),["owner","staff","viewer"]);
  for(const acc of created.testAccounts){
    assert.match(acc.username,/@sentinel-qa\.invalid$/);
    assert(acc.oneTimePassword.length>=30);
    const user=h.getStore().users.find(x=>x.id===acc.userId);
    assert(user.password.startsWith("scrypt:"));
    assert(!JSON.stringify(h.getStore().auditEvents).includes(acc.oneTimePassword));
    const parts=user.password.split(":");
    assert.equal(crypto.scryptSync(acc.oneTimePassword,parts[1],64).toString("hex"),parts[2]);
    h.sessions.set("synthetic-"+acc.role,{userId:acc.userId,organizationId:created.organization.id,role:acc.role});
  }
  for(const key of ["appEntitlements","appTenantMappings","billingOrders","teamInvitations","ownerInvitations"]){
    assert.deepEqual(h.getStore()[key],[]);
  }
  assert.equal(h.getStore().organizations.length,h.initial.organizations.length+1);
  assert(fs.existsSync(h.storeFile));
 });
 await t.test("synthetic owner/staff/viewer cannot access platform operator endpoints",async()=>{
  assert.equal((await h.request(create,{method:"POST",token:"synthetic-owner",body:ack})).status,403);
  assert.equal((await h.request(create,{method:"POST",token:"synthetic-staff",body:ack})).status,403);
  assert.equal((await h.request(create+"/"+created.organization.id+"/cleanup-preview",{token:"synthetic-owner"})).status,403);
  assert.equal((await h.request(create+"/"+created.organization.id+"/cleanup",{method:"POST",token:"synthetic-viewer",body:{}})).status,403);
 });
 await t.test("duplicate creation blocked; forged cleanup blocked",async()=>{
  assert.equal((await h.request(create,{method:"POST",body:ack})).status,409);
  assert.equal((await h.request(create+"/existing-customer-org/cleanup-preview")).status,409);
  assert.equal((await h.request(create+"/"+created.organization.id+"/cleanup-preview",{token:"customer"})).status,403);
 });
 const target=create+"/"+created.organization.id;
 let preview;
 await t.test("validated read-only preview and confirmation safeguards",async()=>{
  const p=await h.request(target+"/cleanup-preview");
  assert.equal(p.status,200);
  preview=p.json;
  assert.equal(preview.memberCount,3);
  assert.match(preview.previewHash,/^[a-f0-9]{64}$/);
  assert.equal((await h.request(target+"/cleanup",{method:"POST",body:{confirmName:"bad",previewHash:preview.previewHash}})).status,409);
  assert.equal((await h.request(target+"/cleanup",{method:"POST",body:{confirmName:"DELETE "+created.organization.name,previewHash:"0".repeat(64)}})).status,409);
  assert.equal((await h.request(target+"/cleanup",{method:"POST",body:{confirmName:"DELETE "+created.organization.name,previewHash:preview.previewHash},origin:false})).status,403);
 });
 await t.test("foreign app mapping blocks deletion, preserves test and existing records",async()=>{
  h.getStore().appTenantMappings.push({organizationId:created.organization.id,appId:"app-pos",status:"active"});
  assert.equal((await h.request(target+"/cleanup-preview")).status,409);
  assert.equal((await h.request(target+"/cleanup",{method:"POST",body:{confirmName:"DELETE "+created.organization.name,previewHash:preview.previewHash}})).status,409);
  h.getStore().appTenantMappings.length=0;
  assert.equal(h.getStore().organizations.length,h.initial.organizations.length+1);
 });
 await t.test("concurrent write request refused while mutation commits",async()=>{
  const resume=h.deferNextCommit();
  // Staged cleanup runs only in memory; route-lock must deny another mutation.
  const promise=h.request(target+"/cleanup",{method:"POST",body:{confirmName:"DELETE "+created.organization.name,previewHash:preview.previewHash}});
  await new Promise(r=>setTimeout(r,35));
  const busy=await h.request(create,{method:"POST",body:ack});
  assert.equal(busy.status,409);
  resume();
  const cleanup=await promise;
  assert.equal(cleanup.status,200);
  assert.equal(cleanup.json.syntheticUsersDeleted,3);
 });
 await t.test("deletion keeps customer, revokes synthetic sessions and writes audit",async()=>{
  const s=h.getStore();
  assert.deepEqual(s.organizations,h.initial.organizations);
  assert.deepEqual(s.users,h.initial.users);
  assert.deepEqual(s.memberships,h.initial.memberships);
  assert.deepEqual(s.auditEvents[0],h.initial.auditEvents[0]);
  assert.equal(s.auditEvents.at(-1).type,"sentinel_qa_tenant_deleted");
  assert.equal(h.sessions.has("operator"),true);
  for(const role of ["owner","staff","viewer"]){
    assert.equal(h.sessions.has("synthetic-"+role),false);
    assert.equal((await h.request(create,{method:"POST",token:"synthetic-"+role,body:ack})).status,401);
  }
  const disk=JSON.parse(fs.readFileSync(h.storeFile,"utf8"));
  assert.deepEqual(disk.organizations,h.initial.organizations);
  assert.equal((await h.request(target+"/cleanup-preview")).status,409);
 });
 setFlags(null,null);
 await t.test("flags returned to disabled",async()=>{
  assert.equal((await h.request(create,{method:"POST",body:ack})).status,404);
  assert.equal((await h.request(target+"/cleanup-preview")).status,404);
 });
});
