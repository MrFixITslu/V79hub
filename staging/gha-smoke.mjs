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
// Stage A must travel through the real four-app provisioners before any
// entitlement or launch test. Neither the secrets nor invite/launch tickets
// are logged. MFA is deliberately disabled ONLY in this disposable CI stack.
const base="http://v79-hub:3040";
if (process.env.STAGE_ADMIN_PASSWORD?.length < 24) {
  throw Error("Synthetic administrator secret missing from CI-only staging container");
}
const adminLogin=await fetch(base+"/api/auth/login",{
  method:"POST",redirect:"manual",
  headers:{"content-type":"application/json"},
  body:JSON.stringify({username:"admin",password:process.env.STAGE_ADMIN_PASSWORD}),
});
assert.equal(adminLogin.status,200,"synthetic founder should authenticate only in this disposable CI environment");
const adminCookie=adminLogin.headers.get("set-cookie")?.split(";")[0];
assert.match(adminCookie||"",/^v79_hub_session=/,"founder session cookie required");
const requestApps=["app-v79pos","app-ffpro","app-tiquet","app-marketing"];
const provision=await fetch(base+"/api/admin/customers/synthetic-customer-a/provision",{
  method:"POST",redirect:"manual",
  headers:{cookie:adminCookie,origin:"https://hub.v79sl.com","content-type":"application/json"},
  body:JSON.stringify({appIds:requestApps}),
  signal:AbortSignal.timeout(30000),
});
const provisionResult=await provision.json();
if(provision.status!==200){
  const failures=(provisionResult.results||[]).map(r=>({product:r.product,status:r.status,error:r.error,upstream:r.upstreamStatus}));
  console.error("EPHEMERAL_REAL_PROVISION_FAILURE",JSON.stringify(failures));
}
assert.equal(provision.status,200,"all four real products must provision the synthetic customer");
assert.deepEqual((provisionResult.results||[]).map(r=>r.product).sort(),["ffpro","marketing","pos","tiquet"]);
assert.ok(provisionResult.results.every(r=>r.status==="active"&&r.skipped!==true),
  "the synthetic customer must actually provision, not skip a pre-seeded mapping");
console.log("EPHEMERAL_REAL_PROVISION_PASS all_four_products=true");

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
// Exercise real Hub authentication using actual production login and /me
// routes, while rejecting cross-tenant session reuse and operator access.
async function loginCustomer(letter) {
  const login=await fetch(base+"/api/auth/login",{
    method:"POST",headers:{"content-type":"application/json"},
    body:JSON.stringify({
      username:"owner-"+letter+"@example.invalid",
      password:process.env.STAGE_CUSTOMER_PASSWORD,
      organizationId:"synthetic-customer-"+letter,
    }),
  });
  assert.equal(login.status,200,"synthetic customer "+letter+" login succeeds");
  const cookie=login.headers.get("set-cookie");
  assert.ok(cookie && /session=/i.test(cookie),"HTTP session cookie expected");
  const sessionCookie=cookie.split(";")[0];
  const me=await fetch(base+"/api/auth/me",{headers:{Cookie:sessionCookie}});
  assert.equal(me.status,200,"authenticated /me must succeed");
  const data=await me.json();
  assert.equal(data.organization?.id,"synthetic-customer-"+letter);
  assert.equal(data.user?.platformOperator,false,
    "customer owner may not act as internal Hub platform operator");
  const forbidden=await fetch(base+"/api/admin/customers",{headers:{Cookie:sessionCookie}});
  assert.equal(forbidden.status,403,"customer cannot access platform admin customer records");
  return sessionCookie;
}
const cookieA=await loginCustomer("a");
const cookieB=await loginCustomer("b");
assert.notEqual(cookieA,cookieB,"tenant sessions are distinct");

// Exercise real redirects, HMAC ticket consumption by each independently
// running product, authenticated downstream sessions, and one-time replay
// rejection. Public URLs are parsed but never fetched: CI has no route to
// production and all subsequent requests use Docker-internal origins.
const stageProducts=[
  {name:"pos",host:"pos.v79sl.com",origin:"http://pos:8080",path:"/auth/launch",cookie:"v79_pos_session",me:"/v1/me"},
  {name:"ffpro",host:"ffpro.v79sl.com",origin:"http://ffpro:3010",path:"/api/platform/launch",cookie:"ffpro.sid",me:"/api/auth/session-state"},
  {name:"tiquet",host:"tiquet.v79sl.com",origin:"http://tiquet:3050",path:"/api/platform/launch",cookie:"tiquet_session",me:"/api/auth/me"},
  {name:"marketing",host:"marketing.v79sl.com",origin:"http://marketing:3070",path:"/api/platform/launch",cookie:"v79_marketing_session",me:"/api/auth/me"},
];
for(const product of stageProducts){
  const grant=await fetch(base+"/api/apps/"+product.name+"/launch",{
    redirect:"manual",headers:{cookie:cookieA},signal:AbortSignal.timeout(15000),
  });
  assert.equal(grant.status,302,product.name+" eligible customer A launch should redirect");
  const target=new URL(grant.headers.get("location")||"");
  assert.equal(target.protocol,"https:");
  assert.equal(target.hostname,product.host,"redirect must target designated app only");
  const ticket=product.name==="pos"
    ? new URLSearchParams(target.hash.slice(1)).get("ticket")
    : target.searchParams.get("ticket");
  assert.match(ticket||"",/^[A-Za-z0-9_-]{32,180}$/);
  const internalUrl=new URL(product.path,product.origin);
  const request=product.name==="pos"
    ? {method:"POST",redirect:"manual",headers:{"content-type":"application/json",origin:"https://pos.v79sl.com"},
       body:JSON.stringify({ticket}),signal:AbortSignal.timeout(15000)}
    : {redirect:"manual",signal:AbortSignal.timeout(15000)};
  if(product.name!=="pos") internalUrl.searchParams.set("ticket",ticket);
  const exchanged=await fetch(internalUrl,request);
  assert.equal(exchanged.status,product.name==="pos"?200:302,
    product.name+" real application must consume the Hub ticket");
  const productCookie=(exchanged.headers.get("set-cookie")||"").split(";")[0];
  assert.ok(productCookie.startsWith(product.cookie+"="),
    product.name+" downstream authenticated session cookie missing");
  const identity=await fetch(new URL(product.me,product.origin),{
    headers:{cookie:productCookie,accept:"application/json"},signal:AbortSignal.timeout(10000),
  });
  assert.equal(identity.status,200,product.name+" authenticated downstream profile");
  if(product.name==="ffpro"){
    const details=await identity.json();
    assert.equal(details.authenticated,true,"FFPRO must report authenticated");
  }
  const replay=await fetch(internalUrl,request);
  const replayCookie=replay.headers.get("set-cookie")||"";
  assert.ok(replay.status!==200&&replay.status!==302&&!replayCookie.includes(product.cookie+"="),
    product.name+" must not issue a second authenticated session from a consumed ticket");
  console.log("EPHEMERAL_REAL_LAUNCH_PASS "+product.name+" authenticated=true replay_denied=true");

  const cancelled=await fetch(base+"/api/apps/"+product.name+"/launch",{
    redirect:"manual",headers:{cookie:cookieB},signal:AbortSignal.timeout(15000),
  });
  assert.equal(cancelled.status,403,product.name+" cancelled customer B cannot receive a launch ticket");
  console.log("EPHEMERAL_CANCELLED_LAUNCH_DENIED "+product.name);
}

for(const [cookie,org] of [[cookieA,"synthetic-customer-a"],[cookieB,"synthetic-customer-b"]]){
  const response=await fetch(base+"/api/auth/me",{headers:{Cookie:cookie}});
  assert.equal(response.status,200);
  assert.equal((await response.json()).organization?.id,org);
}
const anonymous=await fetch(base+"/api/auth/me");
assert.equal(anonymous.status,401,"anonymous requests cannot recover tenant sessions");
console.log("EPHEMERAL_AUTH_PASS isolated_customer_sessions=true operator_denied=true");
console.log("EPHEMERAL_STAGE_PASS all_five_runtime=true real_isolated_databases=true");
