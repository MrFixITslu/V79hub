import test from "node:test";
import assert from "node:assert/strict";
import express from "express";
import {registerActionBrokerOwnerBridge} from "../server/action-broker-owner-bridge.mjs";

const token = "local_action_test_" + "a".repeat(48);
const id = "B".repeat(43);
const callback = "https://chatgpt.com/connector_platform_oauth_redirect?code=fake&state=state";
const info = {
  requestId: id, resource: "https://actions.v79sl.com/mcp",
  scope: "hub:work_item.propose", clientIdHash: "a".repeat(64), expiresIn:300,
};
async function host(t, opts={}) {
  const calls=[];
  const app=express();
  app.use((req, _res, next)=>{
    req.user={mfaVerifiedAt:opts.stale?Date.now()-400_000:Date.now()};
    next();
  });
  registerActionBrokerOwnerBridge(app, {
    ownerMfaContext:req=>req.get("x-test-owner")==="yes"?{userId:"test-verified-founder"}:null,
    sameOrigin:req=>req.get("origin")==="https://hub.v79sl.com",
    readBridgeToken:()=>opts.badToken?"":token,
    ownerActive:()=>!opts.ownerInactive,
    ownerSubject:()=>"real-hub-owner-locked",
    brokerBaseUrl:"http://v79-action-broker:8766",
    fetchImpl:async(url,init)=>{
      calls.push({url:url.href,method:init.method,body:init.body||null,headers:init.headers});
      let payload=url.pathname==="/internal/request"?(opts.badScope?{...info,scope:"evidence:read"}:info)
        :url.pathname==="/internal/consent"?{redirect:callback}
        :url.pathname==="/internal/revoke"?{revoked:true}:{};
      return {ok:true,text:async()=>JSON.stringify(payload)};
    },
  });
  const server=await new Promise(resolve=>{
    const s=app.listen(0,"127.0.0.1",()=>resolve(s));
  });
  t.after(()=>new Promise(resolve=>server.close(resolve)));
  const base="http://127.0.0.1:"+server.address().port;
  async function request(path, options={}){
    const response=await fetch(base+path,{
      redirect:"manual",
      ...options,
      headers:{"x-test-owner":"yes",...options.headers},
    });
    return {status:response.status,location:response.headers.get("location"),
      body:await response.text()};
  }
  return {request,calls};
}

test("action consent shows exact scope and no execution rights, fresh owner only",async t=>{
  const h=await host(t);
  const r=await h.request("/api/agent/action-broker/authorize?request="+id);
  assert.equal(r.status,200);
  assert.match(r.body,/Allow task proposals/);
  assert.match(r.body,/hub:work_item.propose/);
  assert.match(r.body,/cannot approve or execute/);
  assert.ok(!r.body.includes("evidence:read"));
  assert.equal(h.calls.length,1);
  assert.equal(h.calls[0].url,"http://v79-action-broker:8766/internal/request?request="+id);
});
test("stale owner MFA never displays approval control",async t=>{
  const h=await host(t,{stale:true});
  const r=await h.request("/api/agent/action-broker/authorize?request="+id);
  assert.equal(r.status,200);
  assert.ok(!r.body.includes("Allow task proposals"));
  assert.match(r.body,/fresh owner MFA/i);
});
test("owner-approved connection only redirects to verified ChatGPT callback",async t=>{
  const h=await host(t);
  const r=await h.request("/api/agent/action-broker/authorize",{
    method:"POST",
    headers:{"origin":"https://hub.v79sl.com","content-type":"application/x-www-form-urlencoded"},
    body:"requestId="+id+"&approved=true",
  });
  assert.equal(r.status,303);
  assert.equal(r.location,callback);
  assert.equal(h.calls.length,1);
  assert.deepEqual(JSON.parse(h.calls[0].body),{
    requestId:id,subject:"real-hub-owner-locked",approved:true,
  });
});
test("wrong origin or stale MFA cannot approve action connection",async t=>{
  const h=await host(t);
  const r=await h.request("/api/agent/action-broker/authorize",{
    method:"POST",
    headers:{"origin":"https://evil.test","content-type":"application/x-www-form-urlencoded"},
    body:"requestId="+id+"&approved=true",
  });
  assert.equal(r.status,403);
  assert.equal(h.calls.length,0);
  const stale=await host(t,{stale:true});
  const o=await stale.request("/api/agent/action-broker/authorize",{
    method:"POST",
    headers:{"origin":"https://hub.v79sl.com","content-type":"application/x-www-form-urlencoded"},
    body:"requestId="+id+"&approved=true",
  });
  assert.equal(o.status,403);
  assert.equal(stale.calls.length,0);
});
test("mismatched OAuth scope rejects consent before form is shown",async t=>{
  const h=await host(t,{badScope:true});
  const r=await h.request("/api/agent/action-broker/authorize?request="+id);
  assert.equal(r.status,503);
  assert.ok(!r.body.includes("Allow task proposals"));
});
test("owner-active is private machine-only with no cookies or bearer tokens",async t=>{
  const h=await host(t);
  const fail=await h.request("/internal/action-broker/owner-active");
  assert.equal(fail.status,403);
  const browser=await h.request("/internal/action-broker/owner-active",{
    headers:{"x-v79-action-internal":token,cookie:"h=1"},
  });
  assert.equal(browser.status,403);
  const bearer=await h.request("/internal/action-broker/owner-active",{
    headers:{"x-v79-action-internal":token,authorization:"Bearer fake"},
  });
  assert.equal(bearer.status,403);
  const ok=await h.request("/internal/action-broker/owner-active",{
    headers:{"x-v79-action-internal":token},
  });
  assert.equal(ok.status,200);
  assert.deepEqual(JSON.parse(ok.body),{active:true});
});
test("owner revocation needs fresh MFA, exact confirmation and verified broker receipt",async t=>{
  const h=await host(t);
  const invalid=await h.request("/api/agent/action-broker/revoke",{
    method:"POST",
    headers:{"origin":"https://hub.v79sl.com","content-type":"application/x-www-form-urlencoded"},
    body:"confirmation=NOT_EXACT",
  });
  assert.equal(invalid.status,400);
  const valid=await h.request("/api/agent/action-broker/revoke",{
    method:"POST",
    headers:{"origin":"https://hub.v79sl.com","content-type":"application/x-www-form-urlencoded"},
    body:"confirmation=REVOKE_ACTION_BROKER",
  });
  assert.equal(valid.status,200);
  assert.match(valid.body,/revoked/i);
  assert.equal(h.calls.length,1);
  assert.equal(h.calls[0].url,"http://v79-action-broker:8766/internal/revoke");
});
