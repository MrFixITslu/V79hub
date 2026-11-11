import test from "node:test";
import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { signPlatformRequest } from "../server/platform-contract.mjs";
import {
  mapTiquetAccount, projectTiquetEvent,
  createTiquetEventHandler, createWebsiteEventHandler, projectWebsiteLeadEvent, createEcosystemEventInbox,
} from "../server/ecosystem-v2-event-ingress.mjs";

const org = "org_v79_example_customer";
const account = "a31c38d9-00aa-4d7c-86ef-5b5960ab3919";
const now = Date.parse("2026-11-11T12:00:00.000Z");
const store = () => ({
  organizations:[{ id:org, status:"active" }, { id:"org_other_customer", status:"active" }],
  appTenantMappings:[{ organizationId:org, appId:"app-tiquet", status:"active", externalTenantId:account }],
  appEntitlements:[{ organizationId:org, appId:"app-tiquet", enabled:true }],
});
function event(type="job.created",payload={status:"request",priority:"medium",origin:"website"}) {
  return { id:randomUUID(), type, version:1, occurredAt:new Date(now).toISOString(),
    organizationRef:org, accountRef:account, subjectId:"job_987654", payload };
}
const mapped = {organizationId:org,externalAccountId:account};
test("correct active tenant, mapping and entitlement are required",()=>{
  assert.deepEqual(mapTiquetAccount(store(),org,account),mapped);
  for (const changed of [
    {...store(),organizations:[]},
    {...store(),appTenantMappings:[]},
    {...store(),appEntitlements:[]},
    {...store(),appTenantMappings:[{...store().appTenantMappings[0],externalTenantId:"account_other"}]},
  ]) assert.throws(()=>mapTiquetAccount(changed,org,account));
  assert.throws(()=>mapTiquetAccount(store(),"org_other_customer",account));
});
test("event shape strips no fields silently",()=>{
  const result=projectTiquetEvent(event(),mapped,now);
  assert.equal(result.organizationId,org);
  assert.equal(result.source,"tiquet");
  assert.deepEqual(result.payload,{status:"request",priority:"medium",origin:"website"});
  assert.equal(result.accountRef,account);
});
test("every allowed Tiquet event projects to minimal permitted fields",()=>{
  for(const [type,payload] of [
    ["job.created",{status:"request",origin:"website"}],
    ["job.status_changed",{status:"active",previousStatus:"request"}],
    ["job.paid",{}],
    ["customer.created",{origin:"website"}],
    ["payment.recorded",{currency:"XCD",method:"card_external",provider:"wipay"}],
  ]) assert.equal(projectTiquetEvent(event(type,payload),mapped,now).type,type);
});
test("cross-tenant account and org are rejected",()=>{
  assert.throws(()=>projectTiquetEvent({...event(),organizationRef:"org_other_customer"},mapped,now));
  assert.throws(()=>projectTiquetEvent({...event(),accountRef:"another_account"},mapped,now));
});
test("unapproved personal and financial fields are rejected",()=>{
  for(const payload of [
    {status:"request",email:"person@example.com"},
    {status:"request",title:"Customer medical issue"},
    {status:"request",secret:"abc"},
    {status:"request",origin:"https://example.com"},
    {status:"request",amount:300},
    {status:"request",priority:{nested:"value"}},
  ]) assert.throws(()=>projectTiquetEvent(event("job.created",payload),mapped,now));
});
test("money cannot be smuggled in as Hub settlement",()=>{
  for(const payload of [
    {currency:"XCD",method:"card_external",amountMinor:"25000"},
    {currency:"XCD",method:"card_external",reference:"private_ref"},
    {currency:"US",method:"card_external"},
  ]) assert.throws(()=>projectTiquetEvent(event("payment.recorded",payload),mapped,now));
});
test("invalid type, subject and time reject",()=>{
  assert.throws(()=>projectTiquetEvent(event("invoice.settled",{}),mapped,now));
  assert.throws(()=>projectTiquetEvent({...event(),subjectId:"bad\nid"},mapped,now));
  assert.throws(()=>projectTiquetEvent({...event(),occurredAt:"2025-01-01"},mapped,now));
  assert.throws(()=>projectTiquetEvent({...event(),occurredAt:"2030-01-01"},mapped,now));
  assert.throws(()=>projectTiquetEvent({...event(),id:"not-uuid"},mapped,now));
});
function response(){
  return {code:null,result:null,headers:{},
    setHeader(k,v){this.headers[k]=v;return this},
    status(code){this.code=code;return this},
    json(obj){this.result=obj;return this},
  };
}
function request(raw,secret="s".repeat(40),custom={}){
  const body=Buffer.from(JSON.stringify(raw));
  const timestamp=String(Date.now());
  const signature=signPlatformRequest({method:"POST",pathname:"/api/platform/events",timestamp,body:body.toString(),secret});
  const headers={"x-v79-service-id":"tiquet","x-v79-timestamp":timestamp,"x-v79-signature":signature,...custom};
  return {body:raw,rawBody:body,get:(k)=>headers[k]||""};
}
test("disabled route rejects without writing",async()=>{
  const handler=createTiquetEventHandler({enabled:false});
  const res=response();await handler(request(event()),res);
  assert.equal(res.code,404);
});
test("HMAC required and no fallback to cookie auth",async()=>{
  const writes=[];
  const handler=createTiquetEventHandler({enabled:true,secret:"s".repeat(40),
    now:()=>now,getStore:store,inbox:{write:async(e)=>{writes.push(e);return "accepted"}}});
  for(const req of [
    request(event(),"s".repeat(40),{"x-v79-service-id":"other"}),
    request(event(),"incorrect".repeat(8)),
    {...request(event()),rawBody:Buffer.from("tampered")},
  ]){
    const res=response();await handler(req,res);assert.equal(res.code,401);
  }
  assert.equal(writes.length,0);
});
test("valid signed mapped event returns 202, replay returns 200",async()=>{
  const seen=new Set();
  const inbox={async write(e){if(seen.has(e.id))return "duplicate";seen.add(e.id);return "accepted"}};
  const handler=createTiquetEventHandler({enabled:true,secret:"s".repeat(40),now:()=>now,getStore:store,inbox});
  const one=event(),a=response(),b=response();
  await handler(request(one),a);await handler(request(one),b);
  assert.equal(a.code,202);assert.equal(b.code,200);assert.equal(a.result.eventId,one.id);
});
test("bad tenant mapping refuses event before inbox write",async()=>{
  const inbox={write:async()=>{throw Error("should not write")}};
  const handler=createTiquetEventHandler({enabled:true,secret:"s".repeat(40),now:()=>now,
    getStore:()=>({...store(),appTenantMappings:[]}),inbox});
  const res=response();await handler(request(event()),res);
  assert.equal(res.code,409);
});
test("unavailable inbox fails closed rather than claiming acceptance",async()=>{
  const handler=createTiquetEventHandler({enabled:true,secret:"s".repeat(40),now:()=>now,
    getStore:store,inbox:{write:async()=>{throw Error("postgres down")}}});
  const res=response();await handler(request(event()),res);assert.equal(res.code,503);
});
test("database inbox inserts once and detects conflicting replay",async()=>{
  const rows=new Map();
  const fakePool={async query(sql,values=[]){
    if(sql.includes("CREATE TABLE"))return {rowCount:0,rows:[]};
    if(sql.includes("INSERT INTO")){
      const key=values[0]+":"+values[1];
      if(rows.has(key))return {rowCount:0,rows:[]};
      rows.set(key,{organization_id:values[2],account_ref:values[3],digest:values[9]});
      return {rowCount:1,rows:[{event_id:values[1]}]};
    }
    if(sql.includes("SELECT organization_id")){
      const row=rows.get(values[0]+":"+values[1]);
      return {rowCount:row?1:0,rows:row?[row]:[]};
    }
    return {rowCount:0,rows:[]};
  }};
  const inbox=createEcosystemEventInbox(fakePool);
  const first=projectTiquetEvent(event(),mapped,now);
  assert.equal(await inbox.write(first),"accepted");
  assert.equal(await inbox.write(first),"duplicate");
  await assert.rejects(inbox.write({...first,subjectId:"job_different"}));
});

test("signed website receipts preserve the lead reference, not customer PII",()=>{
  const web={
    id:randomUUID(),type:"lead.created",version:1,occurredAt:new Date(now).toISOString(),
    organizationRef:org,subjectId:"2",correlationId:randomUUID(),
    payload:{leadId:2,interest:"Medical consultation for Jane Smith",leadSource:"Website Contact Form",
      pageOrigin:"/contact?email=jane@example.com",employeesBand:"10-20"},
  };
  const projected=projectWebsiteLeadEvent(web,org,store(),now);
  assert.equal(projected.source,"website");
  assert.equal(projected.subjectId,"lead:2");
  assert.equal(projected.correlationId,web.correlationId);
  assert.deepEqual(projected.payload,{source:"Website Contact Form"});
  assert.equal(JSON.stringify(projected).includes("Jane"),false);
  assert.equal(JSON.stringify(projected).includes("email="),false);
});
test("website event must match the operator organisation and lead ID",()=>{
  const web={id:randomUUID(),type:"lead.created",version:1,
    occurredAt:new Date(now).toISOString(),organizationRef:org,subjectId:"27",
    payload:{leadId:27,leadSource:"Website Contact Form"}};
  assert.throws(()=>projectWebsiteLeadEvent({...web,organizationRef:"org_other_customer"},org,store(),now));
  assert.throws(()=>projectWebsiteLeadEvent({...web,payload:{leadId:26}},org,store(),now));
  assert.throws(()=>projectWebsiteLeadEvent({...web,payload:{leadId:27,email:"someone@example.com"}},org,store(),now));
  assert.throws(()=>projectWebsiteLeadEvent(web,org,{organizations:[]},now));
});
test("website and Tiquet secrets remain independent",async()=>{
  const web={id:randomUUID(),type:"lead.created",version:1,occurredAt:new Date(now).toISOString(),
    organizationRef:org,subjectId:"38",payload:{leadId:38,leadSource:"Website Contact Form"}};
  const tSecret="t".repeat(40),wSecret="w".repeat(40);
  const writes=[];
  const handler=createWebsiteEventHandler({enabled:true,secret:wSecret,
    ownerOrganizationId:org,getStore:store,now:()=>now,
    inbox:{write:async(e)=>{writes.push(e);return "accepted"}}});
  const req=request(web,wSecret,{"x-v79-service-id":"website"});
  const good=response();await handler(req,good);assert.equal(good.code,202);
  const wrong=response();await handler(request(web,tSecret,{"x-v79-service-id":"website"}),wrong);
  assert.equal(wrong.code,401);
  assert.equal(writes.length,1);
});
