import test from "node:test";
import assert from "node:assert/strict";
import { spawn, execFileSync } from "node:child_process";
import { createServer } from "node:http";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import pg from "pg";

// Exact pinned public source checkouts; never contact an existing Hub/Tiquet server.
const TIQUET_COMMIT = "7da53ebb71530366168bd72a7efd52b57d34a23c";
const tiquetDir = resolve(".paired-tiquet");
const pgUrl = "postgresql://tiquet_test:tiquet_test_password@127.0.0.1:5432/tiquet_test";
const platformSecret="paired-ci-platform-secret-12345678901234567890";
const launchSecret="paired-ci-launch-secret-123456789012345678901234";
const jwtSecret="paired-ci-jwt-secret-123456789012345678901234";
const dead="http://127.0.0.1:9";

function checkScope() {
  assert.equal(process.env.V79_PAIRED_TEST_SCOPE, "github-ci-disposable");
  assert.equal(process.env.GITHUB_ACTIONS, "true");
  assert.equal(process.env.DATABASE_URL, pgUrl);
  assert.equal(process.env.NODE_ENV, "test");
  assert.equal(process.env.WIPAY_ENABLED, "0");
  assert.equal(execFileSync("git",["-C",tiquetDir,"rev-parse","HEAD"],{encoding:"utf8"}).trim(),TIQUET_COMMIT);
}
async function unusedPort() {
  const s=createServer();
  await new Promise(r=>s.listen(0,"127.0.0.1",r));
  const p=s.address().port;
  await new Promise(r=>s.close(r));
  return p;
}
function launchProcess(t,label,cwd,argv,env) {
  const child=spawn(process.execPath,argv,{cwd,env,stdio:["ignore","pipe","pipe"]});
  let logs="";
  for(const stream of [child.stdout,child.stderr])stream.on("data",b=>{logs=(logs+String(b)).slice(-2200)});
  t.after(async()=>{
    if(child.exitCode===null && child.signalCode===null){
      child.kill("SIGTERM");
      await Promise.race([
        new Promise(r=>child.once("exit",r)),
        new Promise(r=>setTimeout(r,2000))
      ]);
      if(child.exitCode===null && child.signalCode===null)child.kill("SIGKILL");
    }
  });
  return {child,readLogs:()=>label+" failure: "+logs.replace(/(?:Bearer|token|secret)\s+[-\w.=]+/gi,"[redacted]")};
}
async function ready(origin,route,processInfo,check){
  for(let i=0;i<180;i++){
    try{
      const r=await fetch(origin+route,{signal:AbortSignal.timeout(1200)});
      if(r.ok && await check(r))return;
    }catch{}
    if(processInfo.child.exitCode!==null)break;
    await new Promise(r=>setTimeout(r,100));
  }
  throw Error(processInfo.readLogs());
}
async function req(origin,route,opts={}){
  return fetch(origin+route,{redirect:"manual",signal:AbortSignal.timeout(5000),...opts});
}
async function readOk(r,status){
  assert.equal(r.status,status,await r.clone().text());
  return r.json();
}
function cookieFrom(r){
  const raw=r.headers.get("set-cookie")||"";
  assert.match(raw,/^[A-Za-z_][A-Za-z0-9_]*=/);
  return raw.split(";")[0];
}
function invitedToken(url,fragmentName){
  return new URLSearchParams(new URL(url).hash.slice(1)).get(fragmentName);
}
test("current pinned Hub+Tiquet full stack: replay, cross-tenant read/write and explicit logout", {timeout:115000,skip:!process.env.V79_PAIRED_TEST_SCOPE}, async t=>{
  checkScope();
  const dir=await mkdtemp(join(tmpdir(),"v79-paired-g3-"));
  t.after(async()=>rm(dir,{recursive:true,force:true}));
  const hubPort=await unusedPort();
  const hub="http://127.0.0.1:"+hubPort;
  const tiquet="http://127.0.0.1:3000";
  const hubProcess=launchProcess(t,"Hub",process.cwd(),["--import","tsx","server.ts"],{
    ...process.env,
    NODE_ENV:"production",DATA_DIR:dir,PORT:String(hubPort),APP_URL:hub,
    V79_HUB_STORE_BACKEND:"json",V79_HUB_ADMIN_USERNAME:"admin",
    V79_HUB_ADMIN_EMAIL:"vision79slu@gmail.com",
    V79_HUB_ADMIN_PASSWORD:"paired-ci-admin-password-only-2026",
    V79_PLATFORM_SHARED_SECRET:platformSecret,V79_TIQUET_LAUNCH_SECRET:launchSecret,
    TIQUET_INTERNAL_URL:tiquet,TIQUET_PUBLIC_URL:"https://tiquet.v79sl.com",
    POS_BASE_URL:dead,FFPRO_INTERNAL_URL:dead,MARKETING_INTERNAL_URL:dead,
    ACADEMY_INTERNAL_URL:dead,LASERTAG_INTERNAL_URL:dead,OLLAMA_BASE_URL:"",
    WIPAY_ENABLED:"0",V79_MCP_READONLY_ENABLE:"0",V79_RESEND_API_KEY:"",
  });
  await ready(hub,"/api/health",hubProcess,async()=>true);
  const tiquetProcess=launchProcess(t,"Tiquet",tiquetDir,["server/index.js"],{
    ...process.env,
    NODE_ENV:"test",PORT:"3000",DATABASE_URL:pgUrl,
    JWT_SECRET:jwtSecret,SUPER_ADMIN_JWT_SECRET:"paired-ci-sa-secret-12345678901234567890",
    V79_PLATFORM_SHARED_SECRET:platformSecret,V79_TIQUET_LAUNCH_SECRET:launchSecret,
    V79_HUB_INTERNAL_URL:hub,V79_HUB_PUBLIC_URL:"https://hub.example.test",
    V79_ALLOW_LEGACY_AUTH:"0",V79_ENTITLEMENT_RECHECK_ENABLED:"1",
    V79_HUB_MANAGED_BILLING:"1",SEED_DEMO_DATA:"false",
    SMTP_HOST:"",SMTP_USER:"",SMTP_PASS:"",RESEND_API_KEY:"",
    APP_BASE_URL:tiquet,COMPANY_WEBSITE_URL:"https://example.test"
  });
  await ready(tiquet,"/health/ready",tiquetProcess,async r=>(await r.json()).database==="connected");
  assert.equal((await req(tiquet,"/api/jobs")).status,401);
  assert.equal((await req(tiquet,"/api/auth/login",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({email:"someone@example.test",password:"bad"})})).status,410);
  const login=await req(hub,"/api/auth/login",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({username:"admin",password:"paired-ci-admin-password-only-2026"})});
  await readOk(login,200);
  const adminCookie=cookieFrom(login);
  const operatorHeaders={Cookie:adminCookie,Origin:hub,"content-type":"application/json"};
  async function onboard(suffix){
    const email="owner-"+suffix+"@example.test";
    const response=await req(hub,"/api/admin/onboarding/invitations",{
      method:"POST",headers:operatorHeaders,
      body:JSON.stringify({organizationName:"Paired "+suffix,email,appIds:["app-tiquet"],expiresInHours:24})
    });
    const invite=await readOk(response,201);
    const token=invitedToken(invite.inviteUrl,"invite");
    assert.ok(token);
    const accepted=await req(hub,"/api/onboarding/invitation/accept",{
      method:"POST",
      headers:{Origin:hub,"content-type":"application/json","x-v79-invite-token":token},
      body:JSON.stringify({fullName:"Synthetic "+suffix,password:"synthetic-"+suffix+"-owner-password-123"})
    });
    const body=await readOk(accepted,201);
    const provision=await req(hub,"/api/admin/onboarding/organizations/"+encodeURIComponent(body.organization.id)+"/apps/tiquet/provision",{
      method:"POST",headers:operatorHeaders,body:"{}"
    });
    const p=await readOk(provision,200);
    assert.equal(p.mapping.status,"active");
    return {email,organization:body.organization,hubCookie:cookieFrom(accepted),accountId:p.accountId};
  }
  const a=await onboard("alpha"),b=await onboard("beta");
  assert.notEqual(a.organization.id,b.organization.id);
  assert.notEqual(a.accountId,b.accountId);
  async function enterTiquet(customer){
    const launch=await req(hub,"/api/apps/tiquet/launch",{headers:{Cookie:customer.hubCookie}});
    assert.equal(launch.status,302);
    const target=new URL(launch.headers.get("location"));
    assert.equal(target.origin,"https://tiquet.v79sl.com");
    const ticket=target.searchParams.get("ticket");
    assert.match(ticket,/^[A-Za-z0-9_-]{32,180}$/);
    const redirect=await req(tiquet,"/api/platform/launch?ticket="+encodeURIComponent(ticket));
    assert.equal(redirect.status,302,await redirect.clone().text());
    assert.equal(redirect.headers.get("location"),"/");
    const session=cookieFrom(redirect);
    assert.ok(session.startsWith("tiquet_session="));
    const me=await req(tiquet,"/api/auth/me",{headers:{Cookie:session}});
    const user=await readOk(me,200);
    assert.equal(user.email,customer.email);
    assert.equal(user.account_id,customer.accountId);
    const replay=await req(tiquet,"/api/platform/launch?ticket="+encodeURIComponent(ticket));
    assert.equal(replay.status,302);
    assert.equal(new URL(replay.headers.get("location")).searchParams.get("error"),"launch_denied");
    assert.doesNotMatch(replay.headers.get("set-cookie")||"",/tiquet_session=[A-Za-z0-9._-]{30,}/);
    return session;
  }
  const aCookie=await enterTiquet(a),bCookie=await enterTiquet(b);
  const pool=new pg.Pool({connectionString:pgUrl});
  t.after(async()=>pool.end());
  await pool.query(
    "INSERT INTO clients(id,name,email,createdAt,account_id) VALUES($1,$2,$3,$4,$5),($6,$7,$8,$9,$10)",
    ["ci-client-a","Synthetic Alpha","alpha@example.test",new Date().toISOString(),a.accountId,
     "ci-client-b","Synthetic Beta","beta@example.test",new Date().toISOString(),b.accountId]);
  const clientsA=await readOk(await req(tiquet,"/api/clients",{headers:{Cookie:aCookie}}),200);
  const clientsB=await readOk(await req(tiquet,"/api/clients",{headers:{Cookie:bCookie}}),200);
  assert.deepEqual(clientsA.map(x=>x.name),["Synthetic Alpha"]);
  assert.deepEqual(clientsB.map(x=>x.name),["Synthetic Beta"]);
  assert.equal((await req(tiquet,"/api/clients")).status,401);
  const jwt=(await import("../.paired-tiquet/node_modules/jsonwebtoken/index.js")).default;
  const forged=jwt.sign({
    id:(await readOk(await req(tiquet,"/api/auth/me",{headers:{Cookie:aCookie}}),200)).id,
    account_id:a.accountId,hub_organization_id:b.organization.id,hub_managed:true,
  },jwtSecret,{expiresIn:"1h"});
  assert.equal((await req(tiquet,"/api/clients",{headers:{Authorization:"Bearer "+forged}})).status,403);
  // Synthetic, disposable account suspension must block its own active session
  // immediately, without denying the other organization's account.
  try {
    const changed=await pool.query("UPDATE accounts SET status='suspended' WHERE id=$1",[a.accountId]);
    assert.equal(changed.rowCount,1);
    const blocked=await req(tiquet,"/api/clients",{headers:{Cookie:aCookie}});
    assert.equal(blocked.status,402,"suspended tenant denied");
    assert.equal((await req(tiquet,"/api/clients",{headers:{Cookie:bCookie}})).status,200,
      "unrelated tenant remains available");
  } finally {
    await pool.query("UPDATE accounts SET status='active' WHERE id=$1",[a.accountId]);
  }
  // Genuine disposable full-server WRITE checks, not source-only permission assertions.
  const mutationHeaders=(session)=>({Cookie:session,Origin:tiquet,"content-type":"application/json"});
  const updateClient=async(session,id,name,email)=>req(tiquet,"/api/clients/"+encodeURIComponent(id),{
    method:"PUT",headers:mutationHeaders(session),body:JSON.stringify({name,email})
  });
  const ownUpdate=await updateClient(aCookie,"ci-client-a","Synthetic Alpha updated","alpha@example.test");
  assert.equal(ownUpdate.status,200,"own-tenant client edit permitted");
  const crossA=await updateClient(aCookie,"ci-client-b","Cross-tenant corruption","cross@example.test");
  assert.equal(crossA.status,404,"tenant A cannot edit B client ID");
  const crossB=await updateClient(bCookie,"ci-client-a","Cross-tenant corruption","cross@example.test");
  assert.equal(crossB.status,404,"tenant B cannot edit A client ID");
  const postA=await readOk(await req(tiquet,"/api/clients",{headers:{Cookie:aCookie}}),200);
  const postB=await readOk(await req(tiquet,"/api/clients",{headers:{Cookie:bCookie}}),200);
  assert.deepEqual(postA.map(x=>x.name),["Synthetic Alpha updated"],"B must not edit A");
  assert.deepEqual(postB.map(x=>x.name),["Synthetic Beta"],"A must not edit B");

  // Verify the exact issued JWT before explicit Tiquet logout. Testing a
  // cleared browser cookie alone would be insufficient to prove revocation.
  const copiedJwt=decodeURIComponent(aCookie.slice("tiquet_session=".length));
  assert.match(copiedJwt,/^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/);
  assert.equal((await req(tiquet,"/api/auth/me",{headers:{Authorization:"Bearer "+copiedJwt}})).status,200);

  // Observe but do NOT silently accept cross-app global logout as proven.
  // Hub revokes its own session; current Tiquet tokens carry a separate 30m JWT.
  // Explicitly record the release gate as NO_GO if either Tiquet token survives.
  const hubLogout=await req(hub,"/api/auth/logout",{
    method:"POST",headers:{Cookie:a.hubCookie,Origin:hub}
  });
  assert.equal(hubLogout.status,200,"Hub synthetic owner logged out");
  assert.equal((await req(hub,"/api/auth/me",{headers:{Cookie:a.hubCookie}})).status,401,
    "Hub invalidates reused Hub owner cookie after logout");
  assert.equal((await req(hub,"/api/apps/tiquet/launch",{headers:{Cookie:a.hubCookie}})).status,401,
    "Hub refuses further Tiquet launches after Hub logout");
  assert.equal((await req(hub,"/api/auth/me",{headers:{Cookie:b.hubCookie}})).status,200,
    "Hub logout A does not revoke unrelated B Hub session");
  const tiqCookieAfterHub=await req(tiquet,"/api/auth/me",{headers:{Cookie:aCookie}});
  const tiqBearerAfterHub=await req(tiquet,"/api/auth/me",{
    headers:{Authorization:"Bearer "+copiedJwt}
  });
  for (const status of [tiqCookieAfterHub.status,tiqBearerAfterHub.status]) {
    assert.ok([200,401,403].includes(status),
      "Unexpected Tiquet state after Hub-only logout; release acceptance requires investigation");
  }
  const survivesHubLogout=[tiqCookieAfterHub.status,tiqBearerAfterHub.status].includes(200);
  console.log("HUB_ONLY_GLOBAL_LOGOUT_GATE="+
    (survivesHubLogout?"NO_GO_TIQUET_TOKEN_SURVIVES":"CANDIDATE_PASS_REQUIRES_INDEPENDENT_REVIEW")+
    " HUB_COOKIE_REVOKED=YES"+
    " TIQUET_COOKIE_STATUS="+tiqCookieAfterHub.status+
    " TIQUET_BEARER_STATUS="+tiqBearerAfterHub.status);
  assert.equal((await req(tiquet,"/api/auth/me",{headers:{Cookie:bCookie}})).status,200,
    "Tenant B session unaffected by A Hub-only logout");

  // Tiquet logout must durably revoke copied bearer and cookie variants.
  const logout=await req(tiquet,"/api/auth/logout",{
    method:"POST",headers:{Cookie:aCookie,Origin:tiquet}
  });
  assert.equal(logout.status,200);
  assert.equal((await logout.json()).ok,true);
  const cleared=logout.headers.get("set-cookie")||"";
  assert.match(cleared,/tiquet_session=;/);
  assert.match(cleared,/Max-Age=0/);
  assert.equal((await req(tiquet,"/api/auth/me")).status,401);
  for(const headers of [{Cookie:aCookie},{Authorization:"Bearer "+copiedJwt}]){
    const blocked=await req(tiquet,"/api/auth/me",{headers});
    assert.equal(blocked.status,401,"copied logged-out Tiquet session denied");
    assert.equal((await blocked.json()).code,"SESSION_REVOKED");
  }
  assert.equal((await req(tiquet,"/api/auth/me",{headers:{Cookie:bCookie}})).status,200,"other tenant unaffected by logout");
});
