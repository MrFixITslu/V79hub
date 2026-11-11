/**
 * Live HTTP contract checks against three isolated candidate containers.
 * Explicitly prohibited from calling an external service or real mail.
 * Modes: provision, submit, convert.
 */
import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";

if (process.env.GITHUB_ACTIONS !== "true" || process.env.V79_EPHEMERAL_CI !== "1" ||
    process.env.RESEND_API_KEY || process.env.V79_TRIAL_REMINDERS_ENABLED === "1")
  throw new Error("Disposable CI guard failed");
const HUB="http://v79-hub:3040",WEB="http://website:3000";
const STATE="/app/data/v79-v2-ephemeral-state.json";
const mode=process.argv[2];

function cookie(response,name){
  const value=response.headers.get("set-cookie") || "";
  const item=value.split(";")[0];
  assert.ok(item.startsWith(name+"="), "Expected synthetic "+name+" cookie");
  return item;
}
async function request(url, options={}){
  const u=new URL(url);
  if (!["v79-hub","website","tiquet"].includes(u.hostname) ||
      !["http:"].includes(u.protocol))
    throw Error("Synthetic stage may contact internal Docker services only");
  return fetch(url,{redirect:"manual",signal:AbortSignal.timeout(18000),...options});
}
async function json(response,label,expected){
  const value=await response.json().catch(()=>({}));
  assert.equal(response.status,expected,label+": HTTP "+response.status+
    " "+JSON.stringify(value).slice(0,500));
  return value;
}
function posted(data,cookieHeader){
  return {method:"POST",
    headers:{"content-type":"application/json",...(cookieHeader?{cookie:cookieHeader}:{}),
      origin:"http://website:3000"},
    body:JSON.stringify(data)};
}
async function ownerLogin(username,password,organizationId){
  const result=await request(HUB+"/api/auth/login",{
    method:"POST",headers:{"content-type":"application/json"},
    body:JSON.stringify({username,password,...(organizationId?{organizationId}:{})}),
  });
  await json(result,"Hub login",200);
  return cookie(result,"v79_hub_session");
}
async function receipts(cookieHeader){
  const r=await request(HUB+"/api/ecosystem/v2/events",{headers:{cookie:cookieHeader}});
  const v=await json(r,"Hub event receipts",200);
  assert.equal(v.status,"event_receipts_only");
  assert.ok(Array.isArray(v.events));
  return v.events;
}
async function poll(fn,label,tries=18){
  for(let i=0;i<tries;i++){
    const found=await fn();
    if(found)return found;
    await new Promise(resolve=>setTimeout(resolve,1300));
  }
  throw Error("Stage did not observe "+label);
}

if(mode==="provision"){
  const cookieHeader=await ownerLogin("admin",process.env.STAGE_ADMIN_PASSWORD);
  const provision=await request(HUB+
    "/api/admin/customers/synthetic-customer-a/provision",{
      method:"POST",headers:{cookie:cookieHeader,origin:"https://hub.v79sl.com",
        "content-type":"application/json"},
      body:JSON.stringify({appIds:["app-tiquet"]}),
  });
  const payload=await json(provision,"Real Tiquet provisioning",200);
  assert.ok(Array.isArray(payload.results));
  assert.ok(payload.results.some(x=>x.product==="tiquet"&&x.status==="active"));
  console.log("V2_EPHEMERAL_PROVISION_PASS one_real_tiquet_tenant=true");
}else if(mode==="submit"){
  for(const [name,url] of [["hub",HUB+"/api/health"],["website",WEB+"/api/ready"],["tiquet","http://tiquet:3050/health"]]){
    await json(await request(url),name+" readiness",200);
  }
  const key=randomUUID(),input={
    name:"Stage Example",company:"Stage Example Enterprise",
    email:"stage-customer@example.invalid",phone:"17585550199",
    serviceRequested:"Managed IT",biggestChallenge:"New server setup",
    message:"Synthetic-only integration acceptance",
    leadSource:"Website Contact Form",pageOrigin:"/contact",
  };
  const first=await request(WEB+"/api/leads",{
    ...posted(input),headers:{...posted(input).headers,"idempotency-key":key},
  });
  const lead=await json(first,"Website lead capture",201);
  assert.ok(Number.isSafeInteger(lead.id)&&lead.id>0);
  assert.ok(Number.isSafeInteger(lead.crmLeadId)&&lead.crmLeadId>0);
  assert.equal(lead.isDuplicate,false);
  const duplicate=await request(WEB+"/api/leads",{
    ...posted(input),headers:{...posted(input).headers,"idempotency-key":key},
  });
  const repeated=await json(duplicate,"Same-key website replay",200);
  assert.equal(repeated.id,lead.id);
  // A second enquiry with an independent key must not create another
  // authoritative CRM→Website mapping to the same prospect.
  const second=await request(WEB+"/api/leads",{
    ...posted(input),headers:{...posted(input).headers,
      "idempotency-key":randomUUID()},
  });
  const different=await json(second,"Second website enquiry",201);
  assert.notEqual(different.id,lead.id);
  assert.equal(different.crmLeadId,lead.crmLeadId,
    "A repeated contact must be detected as the same CRM prospect");
  assert.equal(different.isDuplicate,true);
  const operator=await ownerLogin("admin",process.env.STAGE_ADMIN_PASSWORD);
  const receipt=await poll(async()=>{
    const items=await receipts(operator);
    return items.find(x=>x.source==="website"&&x.subject_id==="lead:"+lead.id);
  },"website lead event");
  assert.ok(receipt.correlation_id);
  assert.ok(!JSON.stringify(receipt).includes("stage-customer@example.invalid"));
  writeFileSync(STATE,JSON.stringify({
    leadId:lead.id,crmLeadId:lead.crmLeadId,correlationId:receipt.correlation_id,
  }),{flag:"wx",mode:0o600});
  console.log("V2_EPHEMERAL_PRE_APPROVAL_PASS website_crm=true duplicate_safe=true hub_event=true");
}else if(mode==="convert"){
  const {leadId,crmLeadId,correlationId}=JSON.parse(readFileSync(STATE,"utf8"));
  // Only disposable CI uses a password admin. Production requires Hub MFA;
  // the actual Hub→Website SSO browser journey remains a separate release gate.
  const firstLogin=await request(WEB+"/api/admin/login",posted({
    password:process.env.STAGE_WEB_ADMIN_PASSWORD,
  }));
  await json(firstLogin,"Synthetic Website initial login",200);
  const firstCookie=cookie(firstLogin,"v79_admin");
  const password=process.env.STAGE_WEB_ADMIN_PASSWORD+"-rotated";
  const changed=await request(WEB+"/api/admin/change-password",posted({
    currentPassword:process.env.STAGE_WEB_ADMIN_PASSWORD,newPassword:password,
  },firstCookie));
  await json(changed,"Synthetic first-login password rotation",200);
  const login=await request(WEB+"/api/admin/login",posted({password}));
  await json(login,"Synthetic Website admin sign-in",200);
  const webCookie=cookie(login,"v79_admin");
  const convertPath=WEB+"/api/admin/crm/leads/"+crmLeadId+"/convert";
  const approved=await request(convertPath,posted({
    notes:"Customer scope confirmed during synthetic stage.",contractValue:350,
  },webCookie));
  const record=await json(approved,"Website CRM approved conversion",200);
  assert.equal(record.isConverted,true);
  const firstClient=record.convertedClientDetails?.clientId;
  assert.ok(typeof firstClient==="string"&&firstClient.length>=4);
  const retry=await request(convertPath,posted({notes:"Retry only"},webCookie));
  const retried=await json(retry,"Idempotent staff conversion",200);
  assert.equal(retried.convertedClientDetails?.clientId,firstClient);
  const customer=await ownerLogin("owner-a@example.invalid",
    process.env.STAGE_CUSTOMER_PASSWORD,"synthetic-customer-a");
  const event=await poll(async()=>{
    const events=await receipts(customer);
    return events.find(x=>x.source==="tiquet"&&x.type==="job.created"&&
      x.correlation_id===correlationId);
  },"signed Tiquet job event");
  assert.ok(event.subject_id);
  assert.ok(!JSON.stringify(event).includes("stage-customer@example.invalid"));
  const other=await ownerLogin("owner-b@example.invalid",
    process.env.STAGE_CUSTOMER_PASSWORD,"synthetic-customer-b");
  const forbidden=await receipts(other);
  assert.ok(!forbidden.some(x=>x.subject_id===event.subject_id));
  console.log("V2_EPHEMERAL_E2E_PASS approved_link=true customer_id="+
    "verified_and_redacted event_correlated=true cross_tenant_isolated=true");
}else{
  throw Error("Expected provision|submit|convert");
}
