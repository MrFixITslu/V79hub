import test from "node:test";
import assert from "node:assert/strict";
import { spawn, execFileSync } from "node:child_process";
import { createServer } from "node:http";
import { createHash, createHmac } from "node:crypto";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import pg from "pg";
import WebSocket from "ws";

// Exact pinned public source checkouts; never contact an existing Hub/Tiquet server.
const TIQUET_COMMIT = "f1c336bc4406b9c38c23df44a84609bf744512a6";
const HUB_COMMIT = "48c3facacb049610862203535ffee54616573a81";
const tiquetDir = resolve(".paired-tiquet");
const pgUrl = "postgresql://tiquet_test:tiquet_test_password@127.0.0.1:5432/tiquet_test";
const platformSecret="paired-ci-platform-secret-12345678901234567890";
const launchSecret="paired-ci-launch-secret-123456789012345678901234";
const jwtSecret="paired-ci-jwt-secret-123456789012345678901234";
const dead="http://127.0.0.1:9";

function checkScope() {
  assert.equal(execFileSync("git",["-C",".candidate-hub","rev-parse","HEAD"],{encoding:"utf8"}).trim(),HUB_COMMIT);
  for (const [name,sha] of [["v79-ci-patched-hub",HUB_COMMIT],["v79-ci-patched-tiquet",TIQUET_COMMIT]]) {
    assert.equal(execFileSync("docker",["image","inspect",name,"--format",'{{index .Config.Labels "org.opencontainers.image.revision"}}'],{encoding:"utf8"}).trim(),sha);
  }
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
  const isHub=label.includes("Hub");
  const image=isHub ? "v79-ci-patched-hub" : "v79-ci-patched-tiquet";
  const name="v79-ci-patched-"+label.toLowerCase().replace(/[^a-z0-9-]/g,"-")+"-"+process.pid;
  const dockerArgs=["run","--rm","--name",name,"--network","host","--read-only",
    "--cap-drop","ALL","--security-opt","no-new-privileges",
    "--user",String(process.getuid())+":"+String(process.getgid()),
    "--tmpfs","/tmp:rw,nosuid,nodev,size=192m,mode=1777",
    "--tmpfs","/app/data:rw,nosuid,nodev,size=64m,mode=1777",
    "--tmpfs","/app/uploads:rw,nosuid,nodev,size=64m,mode=1777",
    "--tmpfs","/app/logs:rw,nosuid,nodev,size=32m,mode=1777"];
  if(isHub) dockerArgs.push("--mount","type=bind,src="+env.DATA_DIR+",dst="+env.DATA_DIR);
  const keys=["NODE_ENV","DATA_DIR","PORT","APP_URL","DATABASE_URL","JWT_SECRET","SUPER_ADMIN_JWT_SECRET",
    "V79_HUB_STORE_BACKEND","V79_HUB_ADMIN_USERNAME","V79_HUB_ADMIN_EMAIL","V79_HUB_ADMIN_PASSWORD",
    "V79_HUB_TIQUET_SESSION_BINDING","V79_PLATFORM_SHARED_SECRET","V79_TIQUET_LAUNCH_SECRET",
    "TIQUET_INTERNAL_URL","TIQUET_PUBLIC_URL","POS_BASE_URL","FFPRO_INTERNAL_URL","MARKETING_INTERNAL_URL",
    "ACADEMY_INTERNAL_URL","LASERTAG_INTERNAL_URL","OLLAMA_BASE_URL","WIPAY_ENABLED","V79_MCP_READONLY_ENABLE",
    "V79_RESEND_API_KEY","V79_HUB_INTERNAL_URL","V79_HUB_PUBLIC_URL","V79_ALLOW_LEGACY_AUTH",
    "V79_ENTITLEMENT_RECHECK_ENABLED","V79_TIQUET_SESSION_BINDING_ENABLED","V79_HUB_MANAGED_BILLING",
    "SEED_DEMO_DATA","SMTP_HOST","SMTP_USER","SMTP_PASS","RESEND_API_KEY","APP_BASE_URL","COMPANY_WEBSITE_URL"];
  for(const key of keys) if(env[key]!==undefined) dockerArgs.push("--env",key+"="+env[key]);
  dockerArgs.push("--entrypoint","node",image,...argv);
  const child=spawn("docker",dockerArgs,{stdio:["ignore","pipe","pipe"]});
  const stop=async()=>{
    if(child.exitCode!==null || child.signalCode!==null)return;
    const exited=new Promise(resolve=>child.once("exit",resolve));
    try { execFileSync("docker",["stop","--time","2",name],{stdio:"ignore",timeout:8000}); } catch {}
    await Promise.race([exited,new Promise(resolve=>setTimeout(resolve,2000))]);
  };
  t.after(stop);
  let logs="";
  for(const stream of [child.stdout,child.stderr])stream.on("data",b=>{logs=(logs+String(b)).slice(-2200)});
  return {child,stop,readLogs:()=>label+" failure: "+logs.replace(/(?:Bearer|token|secret)\s+[-\w.=]+/gi,"[redacted]")};
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
test("Exact patched OCI pair: SSO, dual-tenant read/write and session revocation", {timeout:115000,skip:!process.env.V79_PAIRED_TEST_SCOPE}, async t=>{
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
    V79_HUB_TIQUET_SESSION_BINDING:"1",
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
    V79_TIQUET_SESSION_BINDING_ENABLED:"1",
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

  // Even a product with the legitimate service HMAC cannot invent an
  // alternate org/user scope for this exact Hub session.
  const hubClaims=jwt.verify(copiedJwt,jwtSecret);
  assert.match(hubClaims.hub_session_id,/^[a-f0-9]{64}$/);
  const linked=await pool.query("SELECT hub_user_id FROM users WHERE account_id=$1 LIMIT 1",[a.accountId]);
  assert.equal(linked.rowCount,1);
  const hubScopedUser=linked.rows[0].hub_user_id;
  const signedStatus=async(organizationId,scopedUserId,authorization=true)=>{
    const pathname="/api/platform/session/status";
    const body=JSON.stringify({product:"tiquet",hubSessionId:hubClaims.hub_session_id,
      organizationId,scopedUserId});
    const timestamp=String(Date.now());
    const h=createHash("sha256").update(body).digest("hex");
    const signature=createHmac("sha256",launchSecret).update(["POST",pathname,timestamp,h].join("\n")).digest("hex");
    return req(hub,pathname,{method:"POST",headers:{
      "content-type":"application/json",
      ...(authorization?{"x-v79-service-id":"v79-tiquet","x-v79-timestamp":timestamp,"x-v79-signature":signature}:{}),
    },body});
  };
  assert.equal((await readOk(await signedStatus(a.organization.id,hubScopedUser),200)).active,true);
  assert.equal((await readOk(await signedStatus(b.organization.id,hubScopedUser),200)).active,false,
    "A session cannot authorize another tenant");
  assert.equal((await readOk(await signedStatus(a.organization.id,"wrong-scoped-user"),200)).active,false);
  assert.equal((await signedStatus(a.organization.id,hubScopedUser,false)).status,401,
    "Unsigned status requests are rejected");

  // Actual staff WebSocket session: one authorized A job and a connected
  // socket must be unsubscribed/closed on the next bounded heartbeat.
  const createdJob=await req(tiquet,"/api/jobs",{
    method:"POST",headers:mutationHeaders(aCookie),
    body:JSON.stringify({title:"Synthetic bound-session socket",client:"Synthetic Alpha updated",
      status:"request",priority:"medium"})
  });
  const wsJob=await readOk(createdJob,201);
  assert.ok(wsJob.id);
  const staffSocket=new WebSocket(
    "ws://127.0.0.1:3000/ws?jobId="+encodeURIComponent(wsJob.id)+"&auth="+encodeURIComponent(copiedJwt)
  );
  t.after(()=>{try{staffSocket.terminate();}catch{}});
  const opened=new Promise((resolve,reject)=>{
    const deadline=setTimeout(()=>reject(Error("staff WebSocket handshake timed out")),6000);
    staffSocket.once("open",()=>{clearTimeout(deadline);resolve();});
    staffSocket.once("error",error=>{clearTimeout(deadline);reject(error);});
  });
  await opened;
  await new Promise(r=>setTimeout(r,350));
  assert.equal(staffSocket.readyState,WebSocket.OPEN,"valid Hub-linked staff socket attached");
  const closedByRevocation=new Promise((resolve,reject)=>{
    const deadline=setTimeout(()=>reject(Error("staff WebSocket did not revoke within 25 seconds")),25000);
    staffSocket.once("close",(code)=>{
      clearTimeout(deadline);resolve(code);
    });
  });

  // With session binding enabled, both Hub and Tiquet tokens must become
  // unusable after the parent Hub session ends.
  // A signed launch ticket minted just before logout must fail consumption
  // once Hub removes the exact session that authorized its creation.
  const pendingLaunch=await req(hub,"/api/apps/tiquet/launch",{headers:{Cookie:a.hubCookie}});
  assert.equal(pendingLaunch.status,302);
  const lateTicket=new URL(pendingLaunch.headers.get("location")).searchParams.get("ticket");
  assert.match(lateTicket,/^[A-Za-z0-9_-]{32,180}$/);
  const hubLogout=await req(hub,"/api/auth/logout",{
    method:"POST",headers:{Cookie:a.hubCookie,Origin:hub}
  });
  assert.equal(hubLogout.status,200,"Hub synthetic owner logged out");
  assert.equal((await req(hub,"/api/auth/me",{headers:{Cookie:a.hubCookie}})).status,401,
    "Hub invalidates reused Hub owner cookie after logout");
  assert.equal((await req(hub,"/api/apps/tiquet/launch",{headers:{Cookie:a.hubCookie}})).status,401,
    "Hub refuses further Tiquet launches after Hub logout");
  const lateAttempt=await req(tiquet,"/api/platform/launch?ticket="+encodeURIComponent(lateTicket));
  assert.equal(lateAttempt.status,302);
  assert.equal(new URL(lateAttempt.headers.get("location")).searchParams.get("error"),"launch_denied",
    "Ticket generated before logout must be rejected after revocation");
  assert.doesNotMatch(lateAttempt.headers.get("set-cookie")||"",/tiquet_session=[A-Za-z0-9._-]{30,}/);
  assert.equal((await req(hub,"/api/auth/me",{headers:{Cookie:b.hubCookie}})).status,200,
    "Hub logout A does not revoke unrelated B Hub session");
  assert.equal((await readOk(await signedStatus(a.organization.id,hubScopedUser),200)).active,false,
    "Authoritative status denies an ended parent Hub session");
  const tiqCookieAfterHub=await req(tiquet,"/api/auth/me",{headers:{Cookie:aCookie}});
  const tiqBearerAfterHub=await req(tiquet,"/api/auth/me",{
    headers:{Authorization:"Bearer "+copiedJwt}
  });
  assert.equal(tiqCookieAfterHub.status,401,
    "Global logout must reject previously issued Tiquet session cookie");
  assert.equal(tiqBearerAfterHub.status,401,
    "Global logout must reject copied Tiquet JWT via Bearer");
  assert.equal((await tiqCookieAfterHub.json()).code,"HUB_SESSION_INACTIVE");
  assert.equal((await tiqBearerAfterHub.json()).code,"HUB_SESSION_INACTIVE");
  console.log("HUB_ONLY_GLOBAL_LOGOUT_GATE=ISOLATED_PASS"+
    " HUB_COOKIE_REVOKED=YES TIQUET_COOKIE_STATUS=401 TIQUET_BEARER_STATUS=401");
  assert.equal(await closedByRevocation,4003,
    "existing authenticated Tiquet staff WebSocket must close on Hub logout");
  console.log("STAFF_WS_HUB_LOGOUT_REVOKED=PASS");
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

  // Simulate a Hub service outage only in the disposable CI stack.
  // The unaffected tenant B must now fail closed rather than use a
  // previously cached successful product-entitlement response.
  await hubProcess.stop();
  const offline=await req(tiquet,"/api/auth/me",{headers:{Cookie:bCookie}});
  assert.equal(offline.status,401,"Hub outage must not silently authorize Tiquet");
  assert.equal((await offline.json()).code,"HUB_SESSION_INACTIVE");
  console.log("HUB_SESSION_STATUS_HMAC_SCOPE=PASS HUB_OUTAGE_FAIL_CLOSED=PASS");

  // Reboot only the disposable Hub process over the same isolated data dir.
  // The persisted session store must keep B alive and A revoked.
  const resumedHub=launchProcess(t,"Restarted synthetic Hub",process.cwd(),["--import","tsx","server.ts"],{
    ...process.env,
    NODE_ENV:"production",DATA_DIR:dir,PORT:String(hubPort),APP_URL:hub,
    V79_HUB_STORE_BACKEND:"json",V79_HUB_ADMIN_USERNAME:"admin",
    V79_HUB_ADMIN_EMAIL:"vision79slu@gmail.com",
    V79_HUB_ADMIN_PASSWORD:"paired-ci-admin-password-only-2026",
    V79_HUB_TIQUET_SESSION_BINDING:"1",
    V79_PLATFORM_SHARED_SECRET:platformSecret,V79_TIQUET_LAUNCH_SECRET:launchSecret,
    TIQUET_INTERNAL_URL:tiquet,TIQUET_PUBLIC_URL:"https://tiquet.v79sl.com",
    POS_BASE_URL:dead,FFPRO_INTERNAL_URL:dead,MARKETING_INTERNAL_URL:dead,
    ACADEMY_INTERNAL_URL:dead,LASERTAG_INTERNAL_URL:dead,OLLAMA_BASE_URL:"",
    WIPAY_ENABLED:"0",V79_MCP_READONLY_ENABLE:"0",V79_RESEND_API_KEY:"",
  });
  await ready(hub,"/api/health",resumedHub,async()=>true);
  assert.equal((await req(hub,"/api/auth/me",{headers:{Cookie:a.hubCookie}})).status,401,
    "revoked Hub session must remain revoked after restart");
  assert.equal((await req(hub,"/api/auth/me",{headers:{Cookie:b.hubCookie}})).status,200,
    "unrelated valid Hub session must survive restart");
  assert.equal((await readOk(await signedStatus(a.organization.id,hubScopedUser),200)).active,false,
    "revoked Hub session may not reappear after restart");
  assert.equal((await req(tiquet,"/api/auth/me",{headers:{Cookie:bCookie}})).status,200,
    "unrelated linked Tiquet access can recover after Hub restarts");
  console.log("HUB_SESSION_RESTART_DURABILITY=PASS");
});
