// Runs *inside* the disposable Hub container on GitHub Actions.
// No external origin or production tenant is contacted.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { signPlatformRequest } from "../server/platform-contract.mjs";

if (process.env.GITHUB_ACTIONS !== "true" || process.env.V79_EPHEMERAL_CI !== "1" ||
    process.env.RESEND_API_KEY || process.env.V79_TRIAL_REMINDERS_ENABLED === "1" ||
    process.env.STAGE_CUSTOMER_PASSWORD?.length < 24) {
  throw Error("Ephemeral stage guard failed; no real mail, trials, or public requests allowed.");
}
const hosts=[
  ["hub","http://v79-hub:3040/api/health"],
  ["pos","http://pos:8080/health"],
  ["ffpro","http://ffpro:3010/api/health"],
  ["tiquet","http://tiquet:3050/health"],
  ["marketing","http://marketing:3070/api/health"],
];
async function waitHealthy(name,url){
  let last="not started";
  for(let i=0;i<80;i++){
    try {
      const result=await fetch(url,{signal:AbortSignal.timeout(2500)});
      if(result.ok) return;
      last="HTTP "+result.status;
    } catch(e){last=e?.name||"unreachable";}
    await new Promise(resolve=>setTimeout(resolve,1000));
  }
  throw Error(name+" did not reach healthy state: "+last);
}
for(const [name,url] of hosts){
  await waitHealthy(name,url);
  console.log("EPHEMERAL_HEALTH_PASS "+name);
}
const endpoint="http://v79-hub:3040/api/platform/entitlement/check";
const pathname="/api/platform/entitlement/check";
const products=[
  ["pos","v79-pos",process.env.V79_POS_PLATFORM_SHARED_SECRET],
  ["ffpro","v79-ffpro",process.env.V79_FFPRO_LAUNCH_SECRET],
  ["tiquet","v79-tiquet",process.env.V79_TIQUET_LAUNCH_SECRET],
  ["marketing","v79-marketing",process.env.V79_MARKETING_LAUNCH_SECRET],
];
function scoped(product,customer){
  const org="synthetic-customer-"+customer;
  const user="synthetic-user-"+customer;
  // Hub's entitlement verifier currently resolves POS-style hashed IDs
  // for all service products, not raw Hub user IDs. Preserve this check.
  if(!["pos","ffpro","tiquet","marketing"].includes(product))
    throw Error("Unsupported staged product");
  const hash=createHash("sha256").update(org+":"+user).digest("hex");
  return hash.slice(0,8)+"-"+hash.slice(8,12)+"-4"+hash.slice(13,16)+"-a"+hash.slice(17,20)+"-"+hash.slice(20,32);
}
async function entitlement(product,serviceId,secret,org,user,{invalidSignature=false}={}){
  const body=JSON.stringify({product,organizationId:org,scopedUserId:user});
  const timestamp=String(Date.now());
  const signature=signPlatformRequest({method:"POST",pathname,timestamp,body,secret});
  const response=await fetch(endpoint,{method:"POST",headers:{
    "content-type":"application/json","x-v79-service-id":serviceId,
    "x-v79-timestamp":timestamp,
    "x-v79-signature":invalidSignature?"0".repeat(64):signature
  },body});
  return {status:response.status,data:await response.json()};
}
for(const [product,serviceId,secret] of products){
  const a=await entitlement(product,serviceId,secret,"synthetic-customer-a",scoped(product,"a"));
  assert.equal(a.status,200,product+" signed active request must complete");
  assert.equal(a.data.allowed,true,product+" active synthetic trial should be accessible");
  assert.ok(a.data.validForSeconds>0 && a.data.validForSeconds<=30);

  const b=await entitlement(product,serviceId,secret,"synthetic-customer-b",scoped(product,"b"));
  assert.equal(b.status,200);
  assert.equal(b.data.allowed,false,product+" cancelled tenant must be denied");

  const cross=await entitlement(product,serviceId,secret,"synthetic-customer-a",scoped(product,"b"));
  assert.equal(cross.status,200);
  assert.equal(cross.data.allowed,false,product+" cross-tenant mismatch must be denied");

  const unsigned=await entitlement(product,serviceId,secret,"synthetic-customer-a",scoped(product,"a"),{invalidSignature:true});
  assert.equal(unsigned.status,401,product+" invalid signature must be rejected");
  console.log("EPHEMERAL_ENTITLEMENT_PASS "+product+" active/cancelled/cross-tenant/HMAC");
}
// Exercise real Hub auth with a synthetic account. Never log the cookie or password.
const login=await fetch("http://v79-hub:3040/api/auth/login",{method:"POST",
  headers:{"content-type":"application/json"},
  body:JSON.stringify({username:"owner-a@example.invalid",password:process.env.STAGE_CUSTOMER_PASSWORD})});
assert.equal(login.status,200,"synthetic customer login should succeed");
const cookie=login.headers.get("set-cookie");
assert.ok(cookie?.startsWith("v79_hub_session="),"HTTP-only session cookie expected");
const dashboard=await fetch("http://v79-hub:3040/api/platform/dashboard",{headers:{Cookie:cookie.split(";")[0]}});
assert.equal(dashboard.status,200,"authenticated dashboard must be accessible");
const summary=await dashboard.json();
assert.equal(summary.organization?.id,"synthetic-customer-a","authenticated session must be tenant-scoped");
console.log("EPHEMERAL_AUTH_PASS isolated_customer_session=true");
console.log("EPHEMERAL_STAGE_PASS all_five_runtime=true real_isolated_databases=true");
