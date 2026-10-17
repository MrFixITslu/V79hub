import test from "node:test";
import assert from "node:assert/strict";
import crypto from "node:crypto";
import express from "express";
import { createServer } from "node:http";
import { signPlatformRequest } from "../server/platform-contract.mjs";
import { SERVICE_PATH, sentinelServiceRouter, validateSentinelServiceEntitlement } from "../server/sentinel-service-entitlement.mjs";

const now=Date.parse("2026-10-10T15:00:00.000Z");
const customer=crypto.randomUUID();
const request={serviceId:"v79-sentinel",sentinelCustomerId:customer,
  organizationId:"v79-owner",accountId:"tiquet-owner-account",clientId:"internal-pilot",
  action:"ticket.create"};
const secret="synthetic-test-only-owner-to-hub-service-secret-1234567890";
function context(){
  const grant={serviceId:request.serviceId,sentinelCustomerId:customer,
    organizationId:"v79-owner",tiquetAccountId:request.accountId,
    tiquetClientId:request.clientId,status:"active",enabled:true,
    actions:["ticket.create","ticket.add_recovery_evidence"],
    expiresAt:new Date(now+60000).toISOString()};
  const store={organizations:[{id:"v79-owner",status:"active"}],
    appEntitlements:[{organizationId:"v79-owner",appId:"app-tiquet",enabled:true}],
    organizationPlans:[],sentinelServiceGrants:[grant]};
  const args={request,ownerOrganizationId:"v79-owner",
    tenantReady:()=>true,now};
  return {store,args,grant};
}

test("explicit owner-only grant and Tiquet entitlement permit narrow service identity",()=>{
  const {store,args}=context();
  const result=validateSentinelServiceEntitlement(store,args);
  assert.equal(result.allowed,true);
  assert.equal(result.validForSeconds,5);
  assert.equal(validateSentinelServiceEntitlement(store,{...args,
    request:{...request,action:"ticket.add_recovery_evidence"}}).allowed,true);
});

test("missing, revoked, expired, duplicate or changed mapping denies unattended service",()=>{
  const {store,args,grant}=context();
  const failures=[
    {...request,serviceId:"v79-human-owner"},
    {...request,organizationId:"other-org"},
    {...request,accountId:"foreign-account"},
    {...request,clientId:"foreign-client"},
    {...request,sentinelCustomerId:crypto.randomUUID()},
    {...request,action:"ticket.close"},
  ];
  for(const bad of failures)
    assert.equal(validateSentinelServiceEntitlement(store,{...args,request:bad}).allowed,false);
  store.sentinelServiceGrants=[];
  assert.equal(validateSentinelServiceEntitlement(store,args).allowed,false);
  store.sentinelServiceGrants=[grant,{...grant}];
  assert.equal(validateSentinelServiceEntitlement(store,args).allowed,false);
  store.sentinelServiceGrants=[grant];
  grant.revokedAt=new Date(now-1000).toISOString();
  assert.equal(validateSentinelServiceEntitlement(store,args).allowed,false);
  delete grant.revokedAt;
  grant.status="revoked";
  assert.equal(validateSentinelServiceEntitlement(store,args).allowed,false);
  grant.status="active";grant.enabled=false;
  assert.equal(validateSentinelServiceEntitlement(store,args).allowed,false);
  grant.enabled=true;
  assert.equal(validateSentinelServiceEntitlement(store,{...args,now:now+61000}).allowed,false);
});

test("subscription/application access and readiness checked on each request",()=>{
  const {store,args}=context();
  assert.equal(validateSentinelServiceEntitlement(store,{...args,tenantReady:()=>false}).allowed,false);
  store.appEntitlements[0].enabled=false;
  assert.equal(validateSentinelServiceEntitlement(store,args).allowed,false);
  store.appEntitlements[0].enabled=true;
  store.organizations[0].status="suspended";
  assert.equal(validateSentinelServiceEntitlement(store,args).allowed,false);
});

async function harness(t,enabled=true,serviceSecret=secret){
  const {store,args}=context();
  const app=express();
  app.use(express.json({limit:"8kb",verify:(req,_res,raw)=>req.rawBody=Buffer.from(raw)}));
  app.use(SERVICE_PATH,sentinelServiceRouter({enabled,secret:serviceSecret,
    getStore:()=>store,getOwnerOrganizationId:()=>args.ownerOrganizationId,
    tenantReady:()=>true,now:()=>now}));
  const server=createServer(app);
  await new Promise(resolve=>server.listen(0,"127.0.0.1",resolve));
  t.after(()=>new Promise(resolve=>server.close(resolve)));
  const url="http://127.0.0.1:"+server.address().port+SERVICE_PATH;
  async function post(bodyData=request,overrides={}){
    const body=JSON.stringify(bodyData),timestamp=String(Date.now());
    const signature=signPlatformRequest({method:"POST",pathname:SERVICE_PATH,
      timestamp,body,secret:secret});
    const res=await fetch(url,{method:"POST",body,headers:{
      "content-type":"application/json","x-v79-service-id":"v79-tiquet",
      "x-v79-timestamp":timestamp,"x-v79-signature":signature,...overrides},
      signal:AbortSignal.timeout(4000)});
    return {status:res.status,data:await res.json(),cache:res.headers.get("cache-control")};
  }
  return {post,store};
}

test("signed service HTTP request gets short no-store active decision",async t=>{
  const h=await harness(t);
  const response=await h.post();
  assert.equal(response.status,200);
  assert.deepEqual(response.data,{allowed:true,validForSeconds:5});
  assert.equal(response.cache,"no-store");
  h.store.sentinelServiceGrants[0].status="revoked";
  assert.equal((await h.post()).data.allowed,false);
});

test("wrong HMAC, browser credentials, missing mapping and feature-disabled fail closed",async t=>{
  const h=await harness(t);
  assert.equal((await h.post(request,{"x-v79-signature":"0".repeat(64)})).status,401);
  assert.equal((await h.post(request,{origin:"https://evil.example"})).status,403);
  assert.equal((await h.post(request,{"x-v79-service-id":"v79-sentinel"})).status,401);
  assert.equal((await h.post({...request,clientId:"not-owner-client"})).data.allowed,false);
  const off=await harness(t,false);
  assert.equal((await off.post()).status,404);
  const bad=await harness(t,true,"");
  assert.equal((await bad.post()).status,503);
});
