import test from "node:test";
import assert from "node:assert/strict";
import crypto from "node:crypto";
import os from "node:os";
import path from "node:path";
import { mkdtemp, writeFile, readFile, rm, access, readdir } from "node:fs/promises";
import { spawn, execFile } from "node:child_process";
import { promisify } from "node:util";
import { createServer, request as httpRequest } from "node:http";
import { Pool } from "pg";
import { totpCode } from "../server/security-contract.mjs";
import { PostgresStoreRepository } from "../server/postgres-store.mjs";
import { createAgentProposal, appendAgentProposalAudit } from "../server/agent-approval-ledger.mjs";
import { createAgentApprovalAuditChain } from "../server/agent-approval-audit-chain.mjs";

const exec = promisify(execFile);
const cwd = process.cwd();
const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
const random = () => crypto.randomBytes(24).toString("base64url");
function hashPassword(password) {
  const salt = crypto.randomBytes(16).toString("hex");
  return "scrypt:" + salt + ":" + crypto.scryptSync(password, salt, 64).toString("hex");
}
async function freePort() {
  const server = createServer();
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  const port = server.address().port;
  await new Promise(resolve => server.close(resolve));
  return port;
}
async function stop(child) {
  const finished = () => child.exitCode !== null || child.signalCode !== null;
  if (!child || finished()) return;
  const exited = new Promise(resolve => child.once("exit", resolve));
  child.kill("SIGTERM");
  await Promise.race([exited, wait(1500)]);
  if (!finished()) {
    child.kill("SIGKILL");
    await exited;
  }
  assert.ok(finished(), "isolated process must terminate");
}
function fixture(ownerPassword, customerPassword) {
  const owner = crypto.randomUUID(), customer = crypto.randomUUID();
  const ownerOrg = crypto.randomUUID(), customerOrg = crypto.randomUUID();
  const now = "2026-01-01T00:00:00.000Z";
  return {
    owner, customer, ownerOrg, customerOrg,
    state: {
      users: [
        { id: owner, username: "admin", email: "vision79slu@gmail.com", password: hashPassword(ownerPassword),
          fullName: "Synthetic Platform Operator", role: "admin",
          permissions: ["overview","connections","team","security","billing","users"], createdAt: now },
        { id: customer, username: "customer@fixture.invalid", email: "customer@fixture.invalid",
          password: hashPassword(customerPassword), fullName: "Preserved Fixture Customer",
          role: "admin", permissions: ["overview"], createdAt: now },
      ],
      workspace: { companyName: "Disposable Sentinel Integration" },
      ecosystemApps: [],
      organizations: [
        { id: ownerOrg, name: "Synthetic Platform Workspace", slug: "fixture-owner", status: "active", createdAt: now },
        { id: customerOrg, name: "Preserved Customer Workspace", slug: "fixture-customer", status: "active", createdAt: now },
      ],
      memberships: [
        { organizationId: ownerOrg, userId: owner, role: "owner", permissions: ["overview","connections","team","security","billing","users"], status: "active", createdAt: now },
        { organizationId: customerOrg, userId: customer, role: "owner", permissions: ["overview"], status: "active", createdAt: now },
      ],
      appEntitlements: [], organizationPlans: [], trialReminderEvents: [],
      billingOrders: [], billingPaymentEvents: [], ownerInvitations: [], teamInvitations: [],
      appTenantMappings: [], passwordResetRequests: [],
      auditEvents: [{ id: crypto.randomUUID(), type: "fixture_customer_record",
        organizationId: customerOrg, actorUserId: customer, createdAt: now, details: { preserved: true } }],
      fixtureEnvelope: { preserved: "unknown persisted envelope field" },
    },
  };
}
async function postgresBinaryDir() {
  if (process.env.V79_TEST_POSTGRES_BIN) {
    const dir = path.resolve(process.env.V79_TEST_POSTGRES_BIN);
    await access(path.join(dir, "initdb"));
    await access(path.join(dir, "postgres"));
    return dir;
  }
  try {
    const versions = (await readdir("/usr/lib/postgresql")).sort((a,b) => Number(b)-Number(a));
    for (const version of versions) {
      const dir = path.join("/usr/lib/postgresql", version, "bin");
      try { await access(path.join(dir, "initdb")); return dir; } catch {}
    }
  } catch {}
  return null;
}
const pgBin = await postgresBinaryDir();

for (const backend of ["json", "postgres"]) {
  test("full Hub Sentinel auth/MFA/lifecycle with disposable " + backend, {
    timeout: 90000, skip: backend === "postgres" && !pgBin ? "local PostgreSQL binaries unavailable; release gate remains incomplete" : false,
  }, async t => {
    // Deliberately do not inherit DATABASE_URL, DATA_DIR, mail/API keys, product
    // URLs or feature flags. All records are generated here, never copied from V79.
    const root = await mkdtemp(path.join(os.tmpdir(), "v79-full-hub-sentinel-"));
    const dir = path.join(root, "hub");
    const { mkdir } = await import("node:fs/promises");
    await mkdir(dir, { mode: 0o700 });
    let running, pgChild, pool;
    t.after(async () => {
      await stop(running?.child);
      if (pool) await pool.end();
      await stop(pgChild);
      await rm(root, { recursive: true, force: true });
      await assert.rejects(access(root), { code: "ENOENT" });
    });
    const ownerPassword = random(), customerPassword = random();
    const securityKey = random() + random();
    const f = fixture(ownerPassword, customerPassword);
    // Preserve nonempty current agent schema, including a valid keyed chain.
    f.state.agentActionProposals=[];
    f.state.agentProposalAuditTrail=[];
    const preservedProposal=createAgentProposal(f.state.agentActionProposals,{
      operation:"draft_inventory_review",targetSystem:"pos",
      summary:"Synthetic preserved inventory review",
      rationale:"Review the generated inventory fixture without executing any action.",
      evidenceRef:"pos:fixtureInventory",idempotencyKey:"preserved-fixture-proposal",
    },{organizationId:f.ownerOrg,actorUserId:f.owner});
    assert.equal(preservedProposal.kind,"created");
    appendAgentProposalAudit(f.state.auditEvents,preservedProposal.proposal,"agent.proposal.created",f.owner);
    createAgentApprovalAuditChain(securityKey).append(f.state.agentProposalAuditTrail,preservedProposal.proposal,f.owner);
    f.state.appEntitlements.push({ organizationId:f.customerOrg, appId:"app-v79pos", enabled:true });
    f.state.appTenantMappings.push({ organizationId:f.customerOrg, appId:"app-v79pos",
      status:"pending", createdAt:"2026-01-01T00:00:00.000Z" });
    // A disposable upstream exercises the real async provision route. It has
    // no credentials, network target or records belonging to any V79 service.
    let provisionEntered, releaseProvision;
    const provisionStarted=new Promise(resolve=>{provisionEntered=resolve;});
    const provisionGate=new Promise(resolve=>{releaseProvision=resolve;});
    const posStub=createServer(async(req,res)=>{
      let raw="";
      for await(const chunk of req)raw+=chunk;
      const body=JSON.parse(raw);
      assert.equal(req.url,"/api/platform/provision");
      assert.equal(body.organization.id,f.customerOrg);
      provisionEntered();
      await provisionGate;
      res.setHeader("Content-Type","application/json");
      res.end(JSON.stringify({provisioned:true,organizationId:body.organization.id,ownerUserId:body.user.id}));
    });
    await new Promise(resolve=>posStub.listen(0,"127.0.0.1",resolve));
    const posStubUrl="http://127.0.0.1:"+posStub.address().port;
    t.after(async()=>{releaseProvision();posStub.closeAllConnections();await new Promise(resolve=>posStub.close(resolve));});
    const storeFile = path.join(dir, "v79_store.json");
    await writeFile(storeFile, JSON.stringify(f.state), { mode: 0o600 });
    await writeFile(path.join(dir, "pos-identity.json"), JSON.stringify({
      ownerUserId: f.owner, organizationId: f.ownerOrg,
    }), { mode: 0o600 });
    let databaseUrl = "";
    if (backend === "postgres") {
      const pgData = path.join(root, "postgres"), socketDir = path.join(root, "socket");
      await mkdir(socketDir, { mode: 0o700 });
      const user = os.userInfo().username, port = await freePort();
      await exec(path.join(pgBin, "initdb"), ["-D", pgData, "-A", "trust", "--no-locale", "-U", user]);
      pgChild = spawn(path.join(pgBin, "postgres"), [
        "-D", pgData, "-k", socketDir, "-h", "", "-p", String(port),
        "-c", "unix_socket_permissions=0700",
      ], { stdio: ["ignore", "ignore", "pipe"] });
      let pgLogs = "";
      pgChild.stderr.on("data", chunk => { pgLogs += chunk; });
      pool = new Pool({ host: socketDir, port, user, database: "postgres" });
      let ready = false;
      for (let i=0; i<100; i++) {
        if (pgChild.exitCode !== null) break;
        try { await pool.query("SELECT 1"); ready=true; break; } catch { await wait(50); }
      }
      assert.ok(ready, "disposable PostgreSQL failed to start: " + pgLogs.slice(-800));
      assert.equal((await pool.query("SHOW listen_addresses")).rows[0].listen_addresses, "");
      const repo = new PostgresStoreRepository(pool);
      await repo.ensureSchema();
      assert.equal((await repo.initialize(f.state)).initialized, true);
      databaseUrl = "postgresql:///postgres?host=" + encodeURIComponent(socketDir) +
        "&port=" + port + "&user=" + encodeURIComponent(user);
    }
    const readStore = async () => backend === "postgres"
      ? (await new PostgresStoreRepository(pool).load()).state
      : JSON.parse(await readFile(storeFile, "utf8"));
    const port = await freePort(), origin = "http://127.0.0.1:" + port;
    async function start(enabled, { backgroundEnabled=false }={}) {
      const env = {
        PATH: process.env.PATH, LANG: "C.UTF-8", NODE_ENV: "production",
        DATA_DIR: dir, PORT: String(port), APP_URL: origin, V79_HUB_BIND_HOST: "127.0.0.1",
        V79_HUB_STORE_BACKEND: backend, DATABASE_URL: databaseUrl,
        V79_HUB_ADMIN_PASSWORD: ownerPassword, V79_HUB_ADMIN_EMAIL: "vision79slu@gmail.com",
        V79_HUB_SECURITY_KEY: securityKey, V79_REQUIRE_ADMIN_MFA: "1",
        V79_PLATFORM_SHARED_SECRET: securityKey,
        V79_SENTINEL_QA_CREATE_ENABLED: enabled ? "1" : "0",
        V79_SENTINEL_QA_CLEANUP_ENABLED: enabled ? "1" : "0",
        V79_TRIAL_REMINDERS_ENABLED: backgroundEnabled ? "1" : "0",
        V79_TRIAL_REMINDERS_WORKER_LEADER: backgroundEnabled ? "1" : "0",
        RESEND_API_KEY: "", V79_HUB_EMAIL_FROM: "",
        V79_READONLY_PLATFORM_SECRET_FILE: path.join(root, "absent-readonly-secret"),
        V79_AGENT_TOKEN_FILE: path.join(root, "absent-agent-secret"),
      };
      for (const key of ["POS_BASE_URL","ACADEMY_INTERNAL_URL","TIQUET_INTERNAL_URL",
        "FFPRO_INTERNAL_URL","MARKETING_INTERNAL_URL","LASERTAG_INTERNAL_URL",
        "WEBSITE_INTERNAL_URL","GAMES_INTERNAL_URL","V79_AGENT_INTERNAL_URL"]) env[key]="http://127.0.0.1:9";
      env.POS_BASE_URL=posStubUrl;
      env.V79_POS_PLATFORM_SHARED_SECRET=securityKey;
      const child = spawn(process.execPath, ["--import", "tsx", "server.ts"], {
        cwd, env, stdio: ["ignore","pipe","pipe"],
      });
      running = { child, logs: "" };
      const capture = chunk => { running.logs += chunk; };
      child.stdout.on("data", capture); child.stderr.on("data", capture);
      let ready = false;
      for (let i=0; i<250; i++) {
        if (child.exitCode !== null) break;
        try { if ((await fetch(origin+"/api/health")).ok) { ready=true; break; } } catch {}
        await wait(50);
      }
      assert.ok(ready, "isolated full Hub failed readiness: " + running.logs.slice(-1000));
      const listening = await exec("ss", ["-ltn"]);
      const listeners = listening.stdout.split("\n").filter(line => line.split(/\s+/)[3]?.endsWith(":"+port));
      assert.equal(listeners.length, 1);
      assert.ok(listeners[0].includes("127.0.0.1:"+port), "Hub must bind only loopback");
    }
    async function restart(enabled, options={}) { await stop(running.child); await start(enabled, options); }
    async function request(route, { method="GET", cookie, bearer, body, requestOrigin=origin }={}) {
      const headers = { "content-type": "application/json" };
      if (cookie) headers.Cookie=cookie;
      if (bearer) headers.Authorization="Bearer "+bearer;
      if (requestOrigin !== null) headers.Origin=requestOrigin;
      const res = await fetch(origin+route, { method, headers, redirect: "manual",
        ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
      const data = await res.json();
      return { status: res.status, data, cookie: res.headers.get("set-cookie")?.split(";")[0], headers: res.headers };
    }
    const create = "/api/admin/sentinel-qa/organizations", ack = { confirm: "CREATE ISOLATED SENTINEL QA" };
    const login = (username,password,organizationId) => request("/api/auth/login", {
      method:"POST", body:{username,password,...(organizationId ? {organizationId} : {})},
    });
    await start(false);
    assert.equal((await request("/api/admin/sentinel-qa/status")).status,401);
    assert.equal((await request(create,{method:"POST",body:ack})).status,401);
    const challenge = await login("admin", ownerPassword);
    assert.equal(challenge.status,202);
    assert.equal(challenge.cookie,undefined);
    assert.equal(challenge.data.setupRequired,true);
    assert.equal((await request("/api/admin/sentinel-qa/status",{bearer:challenge.data.challengeId})).status,401);
    assert.equal((await request(create,{method:"POST",bearer:challenge.data.challengeId,body:ack})).status,401);
    const wrongMfa = await request("/api/auth/mfa/complete-login",{
      method:"POST",body:{challengeId:challenge.data.challengeId,code:"invalid"},
    });
    assert.equal(wrongMfa.status,401); assert.equal(wrongMfa.cookie,undefined);
    const complete = await request("/api/auth/mfa/complete-login",{
      method:"POST",body:{challengeId:challenge.data.challengeId,code:totpCode(challenge.data.secret)},
    });
    assert.equal(complete.status,200);
    const operatorCookie=complete.cookie;
    assert.match(operatorCookie,/^v79_hub_session=v79_tok_/);
    assert.equal(complete.data.user.platformOperator,true);
    assert.equal(complete.data.user.mfaEnabled,true);
    const supervisor=await request("/api/admin/sentinel-qa/status",{cookie:operatorCookie});
    assert.equal(supervisor.status,200); assert.equal(supervisor.data.createEnabled,false);
    assert.equal(supervisor.data.cleanupEnabled,false); assert.equal(supervisor.data.maintenanceReady,true);
    assert.deepEqual(supervisor.data.organizations,[]); assert.equal(supervisor.data.syntheticUserCount,0);
    const agentInbox=await request("/api/agent/proposals",{cookie:operatorCookie});
    assert.equal(agentInbox.status,200);assert.equal(agentInbox.data.auditIntegrity,"verified");
    assert.equal(agentInbox.data.proposals.length,1);
    assert.equal(agentInbox.data.proposals[0].id,preservedProposal.proposal.id);
    const preservedCheckpoint=await request("/api/agent/approval-audit-checkpoint",{cookie:operatorCookie});
    assert.equal(preservedCheckpoint.status,200);
    assert.equal((await request("/api/auth/mfa/complete-login",{
      method:"POST",body:{challengeId:challenge.data.challengeId,code:totpCode(challenge.data.secret)},
    })).status,401);
    assert.equal((await request("/api/security/mfa/disable",{
      method:"POST",cookie:operatorCookie,body:{password:ownerPassword,code:totpCode(challenge.data.secret)},
    })).status,403);
    assert.equal((await request(create,{method:"POST",cookie:operatorCookie,body:ack})).status,404);
    t.diagnostic("mandatory operator MFA, wrong code/replay denial and default-disabled flags verified");
    const customerLogin=await login("customer@fixture.invalid",customerPassword);
    assert.equal(customerLogin.status,200);
    const customerCookie=customerLogin.cookie;
    assert.equal(customerLogin.data.user.platformOperator,false);
    assert.equal((await request("/api/admin/sentinel-qa/status",{cookie:customerCookie})).status,403);
    const beforeBusy=await readStore();
    await restart(true,{backgroundEnabled:true});
    assert.equal((await request("/api/admin/sentinel-qa/status",{cookie:operatorCookie})).data.maintenanceReady,false);
    assert.equal((await request(create,{method:"POST",cookie:operatorCookie,body:ack})).status,409);
    assert.deepEqual(await readStore(),beforeBusy,"configured reminder worker blocks creation without mutations");
    await restart(true);
    assert.equal((await request("/api/auth/me",{cookie:operatorCookie})).status,200);
    assert.equal((await request(create,{method:"POST",cookie:customerCookie,body:ack})).status,403);
    assert.equal((await request(create,{method:"POST",cookie:operatorCookie,requestOrigin:null,body:ack})).status,403);
    assert.equal((await request(create,{method:"POST",cookie:operatorCookie,requestOrigin:"https://foreign.invalid",body:ack})).status,403);
    // Disconnect the operator while the real route awaits provisioning. QA
    // must stay blocked until its external side effect AND durable mapping end.
    const disconnected=httpRequest(origin+"/api/admin/onboarding/organizations/"+f.customerOrg+"/apps/pos/provision",{
      method:"POST",headers:{Cookie:operatorCookie,Origin:origin,"Content-Type":"application/json"},
    });
    disconnected.on("error",()=>{});disconnected.end("{}");
    await provisionStarted;
    disconnected.destroy();await wait(30);
    const beforeProvision=await readStore();
    try {
      assert.equal((await request(create,{method:"POST",cookie:operatorCookie,body:ack})).status,409);
      assert.deepEqual(await readStore(),beforeProvision,"disconnected upstream work prevents store replacement");
    } finally {releaseProvision();}
    let provisioned=false;
    for(let i=0;i<100;i++){
      const current=await readStore();
      const mapping=current.appTenantMappings.find(m=>m.organizationId===f.customerOrg);
      if(mapping?.status==="active"){assert.equal(mapping.externalTenantId,f.customerOrg);provisioned=true;break;}
      await wait(20);
    }
    assert.ok(provisioned,"disconnected provision must durably activate the correct mapping");
    await wait(30);
    t.diagnostic("disconnected real Hub provisioning blocks QA until upstream and durable mapping settle");
    const baseline=await readStore();
    assert.equal((await request(create,{method:"POST",cookie:operatorCookie,body:{...ack,email:"unsafe@fixture.invalid"}})).status,400);
    // An unfinished ordinary HTTP body is a tracked in-flight mutation.
    const slow=httpRequest(origin+"/api/auth/login",{method:"POST",headers:{"content-type":"application/json"}});
    const slowDone=new Promise((resolve,reject)=>{ slow.on("response",res=>{res.resume();res.on("end",()=>resolve(res.statusCode));});slow.on("error",reject); });
    slow.write('{"username":'); await wait(100);
    try { assert.equal((await request(create,{method:"POST",cookie:operatorCookie,body:ack})).status,409); }
    finally { slow.end('null}'); }
    assert.equal(await slowDone,400);
    assert.deepEqual(await readStore(),baseline);
    const created=await request(create,{method:"POST",cookie:operatorCookie,body:ack});
    assert.equal(created.status,201); assert.equal(created.headers.get("cache-control"),"no-store");
    assert.equal(created.data.testAccounts.length,3);
    const org=created.data.organization, accounts=created.data.testAccounts;
    assert.match(org.name,/^Sentinel-QA-/);
    const target=create+"/"+org.id;
    assert.equal((await request(create,{method:"POST",cookie:operatorCookie,body:ack})).status,409);
    assert.equal((await request(create+"/"+f.customerOrg+"/cleanup-preview",{cookie:operatorCookie})).status,409);
    const cookies=[];
    for (const account of accounts) {
      const signedIn=await login(account.username,account.oneTimePassword);
      assert.equal(signedIn.status,200);
      assert.equal(signedIn.data.organization.id,org.id);
      assert.equal(signedIn.data.user.platformOperator,false);
      assert.deepEqual(signedIn.data.user.permissions,["overview"]);
      cookies.push(signedIn.cookie);
      assert.equal((await request("/api/auth/me",{cookie:signedIn.cookie})).status,200);
      assert.equal((await request("/api/admin/sentinel-qa/status",{cookie:signedIn.cookie})).status,403);
      assert.equal((await request("/api/agent/proposals",{cookie:signedIn.cookie})).status,403);
      assert.equal((await request(target+"/cleanup-preview",{cookie:signedIn.cookie})).status,403);
      assert.equal((await request(create,{method:"POST",cookie:signedIn.cookie,body:ack})).status,403);
      assert.equal((await request(target+"/cleanup",{method:"POST",cookie:signedIn.cookie,body:{}})).status,403);
      assert.equal((await login(account.username,account.oneTimePassword,f.customerOrg)).status,401);
    }
    const afterCreation=await readStore();
    for (const key of ["appEntitlements","appTenantMappings","organizationPlans","billingOrders","billingPaymentEvents",
      "trialReminderEvents","ownerInvitations","teamInvitations","passwordResetRequests","ecosystemApps"]) {
      assert.deepEqual(afterCreation[key],baseline[key],"no side effects in "+key);
    }
    for (const account of accounts) {
      assert.ok(afterCreation.users.find(u=>u.id===account.userId).password.startsWith("scrypt:"));
      assert.ok(!JSON.stringify(afterCreation).includes(account.oneTimePassword),"raw test password must not persist");
    }
    const sessions=JSON.parse(await readFile(path.join(dir,"hub-sessions.json"),"utf8"));
    assert.equal(sessions.sessions.length,5);
    assert.ok(!JSON.stringify(sessions).includes("v79_tok_"));
    await restart(true);
    for (const cookie of cookies) assert.equal((await request("/api/auth/me",{cookie})).status,200);
    const secondMfa=await login("admin",ownerPassword);
    assert.equal(secondMfa.status,202); assert.equal(secondMfa.data.setupRequired,false);
    assert.equal("secret" in secondMfa.data,false);
    assert.equal((await request(create,{method:"POST",bearer:secondMfa.data.challengeId,body:ack})).status,401);
    const verifiedMfa=await request("/api/auth/mfa/complete-login",{
      method:"POST",body:{challengeId:secondMfa.data.challengeId,code:totpCode(challenge.data.secret)},
    });
    assert.equal(verifiedMfa.status,200);
    assert.equal(verifiedMfa.data.user.mfaEnabled,true);
    assert.equal((await request("/api/auth/me",{cookie:verifiedMfa.cookie})).status,200);
    assert.equal((await request("/api/auth/mfa/complete-login",{
      method:"POST",body:{challengeId:secondMfa.data.challengeId,code:totpCode(challenge.data.secret)},
    })).status,401);
    assert.equal((await request("/api/auth/logout",{method:"POST",cookie:verifiedMfa.cookie})).status,200);
    assert.equal((await request("/api/auth/me",{cookie:verifiedMfa.cookie})).status,401);
    t.diagnostic("three real synthetic logins, workspace/operator isolation, persisted sessions and enrolled-MFA verification after restart verified");
    const preview=await request(target+"/cleanup-preview",{cookie:operatorCookie});
    assert.equal(preview.status,200); assert.equal(preview.data.memberCount,3);
    const deletion={confirmName:"DELETE "+org.name,previewHash:preview.data.previewHash};
    const beforeBlockedCleanup=await readStore();
    await restart(true,{backgroundEnabled:true});
    assert.equal((await request(target+"/cleanup",{method:"POST",cookie:operatorCookie,body:deletion})).status,409);
    assert.deepEqual(await readStore(),beforeBlockedCleanup,"configured reminder worker blocks deletion without mutations");
    await restart(true);
    // Simulate future persisted schema and external-tenant references only in
    // this disposable fixture, with the Hub stopped for every direct edit.
    async function writeIsolatedState(state) {
      assert.ok(running.child.exitCode !== null || running.child.signalCode !== null);
      if (backend === "postgres") {
        const repo=new PostgresStoreRepository(pool), current=await repo.load();
        await repo.replace(current.revision,state);
      } else {
        await writeFile(storeFile,JSON.stringify(state),{mode:0o600});
      }
    }
    for (const contaminant of ["schema-extension","external-tenant","duplicate-user","agent-proposal","agent-audit"]) {
      await stop(running.child);
      const contaminated=structuredClone(afterCreation);
      if (contaminant === "schema-extension") contaminated.fixtureEnvelope.futureLink={organizationId:org.id};
      else if (contaminant === "external-tenant") contaminated.appTenantMappings.push({organizationId:org.id,appId:"app-pos",status:"active"});
      else if (contaminant === "agent-proposal") contaminated.agentActionProposals[0].organizationId=org.id;
      else if (contaminant === "agent-audit") contaminated.agentProposalAuditTrail[0].actorUserId=accounts[2].userId;
      else {
        contaminated.users=contaminated.users.filter(u=>u.id!==accounts[2].userId);
        contaminated.users.push(structuredClone(contaminated.users.find(u=>u.id===accounts[0].userId)));
      }
      await writeIsolatedState(contaminated);
      await start(true);
      assert.equal((await request(target+"/cleanup-preview",{cookie:operatorCookie})).status,409,contaminant+" blocks preview");
      assert.equal((await request(target+"/cleanup",{method:"POST",cookie:operatorCookie,body:deletion})).status,409,contaminant+" blocks deletion");
      assert.deepEqual(await readStore(),contaminated,"rejected cleanup preserves all state");
      await stop(running.child);
      await writeIsolatedState(afterCreation);
      await start(true);
    }
    t.diagnostic("unknown persisted schema references and external tenant mappings fail closed without data changes");
    assert.equal((await request(target+"/cleanup",{method:"POST",cookie:operatorCookie,body:{...deletion,confirmName:"wrong"}})).status,409);
    assert.equal((await request(target+"/cleanup",{method:"POST",cookie:operatorCookie,body:{...deletion,previewHash:"0".repeat(64)}})).status,409);
    assert.equal((await request(target+"/cleanup",{method:"POST",cookie:operatorCookie,requestOrigin:null,body:deletion})).status,403);
    assert.deepEqual(await readStore(),afterCreation);
    if (backend === "postgres") {
      // Hold the actual PostgreSQL row lock, so cleanup remains in its exclusive
      // commit window. Ordinary writes must fail before reaching login/logout.
      const lock=await pool.connect();
      try {
        await lock.query("BEGIN");
        await lock.query("SELECT store_key FROM v79_hub_state WHERE store_key='main' FOR UPDATE");
        const cleaning=request(target+"/cleanup",{method:"POST",cookie:operatorCookie,body:deletion});
        let blocked=false;
        for (let i=0;i<100;i++) {
          const r=await pool.query("SELECT 1 FROM pg_stat_activity WHERE datname=current_database() AND wait_event_type='Lock'");
          if(r.rowCount){blocked=true;break;} await wait(20);
        }
        try {
          assert.ok(blocked,"cleanup must reach durable PostgreSQL write lock");
          assert.equal((await request("/api/auth/logout",{method:"POST",cookie:customerCookie})).status,423);
          assert.equal((await login("customer@fixture.invalid",customerPassword)).status,423);
          for (const route of ["/api/apps/pos/launch","/api/apps/tiquet/launch",
            "/api/apps/marketing/launch","/api/apps/ffpro/launch",
            "/api/billing/wipay/return","/api/ecosystem/apps",
            "/API/APPS/pos/launch","/Api/Billing/WiPay/Return","/Api/Ecosystem/Apps"]) {
            assert.equal((await request(route,{cookie:operatorCookie})).status,423,route+" blocked before side effects");
            assert.equal((await fetch(origin+route,{method:"HEAD",headers:{Cookie:operatorCookie}})).status,423);
          }
          for (const route of ["/api/agent/proposals",
            "/api/agent/proposals/"+preservedProposal.proposal.id+"/decision",
            "/api/agent/proposals/"+preservedProposal.proposal.id+"/marketing-draft"]) {
            assert.equal((await request(route,{method:"POST",cookie:operatorCookie,body:{}})).status,423);
          }
          assert.equal((await request("/api/agent/approval-audit-checkpoint",{cookie:operatorCookie})).status,200);
          assert.equal((await request("/api/health")).status,200);
          assert.equal((await request("/api/auth/me",{cookie:customerCookie})).status,200);
          assert.equal((await request(create,{method:"POST",cookie:operatorCookie,body:ack})).status,409);
        } finally { await lock.query("COMMIT"); }
        const removed=await cleaning;
        assert.equal(removed.status,200); assert.equal(removed.data.syntheticUsersDeleted,3);
      } finally { await lock.query("ROLLBACK").catch(()=>{}); lock.release(); }
      t.diagnostic("real PostgreSQL commit contention blocks ordinary writes and overlapping Sentinel mutation");
    } else {
      const removed=await request(target+"/cleanup",{method:"POST",cookie:operatorCookie,body:deletion});
      assert.equal(removed.status,200); assert.equal(removed.data.syntheticUsersDeleted,3);
    }
    const after=await readStore();
    for (const key of Object.keys(baseline).filter(key=>key!=="auditEvents")) {
      assert.deepEqual(after[key],baseline[key],"preserve unrelated "+key);
    }
    assert.deepEqual(after.auditEvents.slice(0,-1),baseline.auditEvents);
    assert.equal(after.auditEvents.at(-1).type,"sentinel_qa_tenant_deleted");
    assert.equal(after.auditEvents.at(-1).details.syntheticUsersDeleted,3);
    assert.equal(after.organizations.some(o=>o.id===org.id),false);
    assert.equal(after.memberships.some(m=>m.organizationId===org.id),false);
    for(const account of accounts){
      assert.equal(after.users.some(u=>u.id===account.userId),false);
      assert.equal((await login(account.username,account.oneTimePassword)).status,401);
    }
    for(const cookie of cookies) assert.equal((await request("/api/auth/me",{cookie})).status,401);
    const remaining=JSON.parse(await readFile(path.join(dir,"hub-sessions.json"),"utf8")).sessions;
    assert.equal(remaining.length,2);
    assert.deepEqual(new Set(remaining.map(s=>s.userId)),new Set([f.owner,f.customer]));
    assert.equal((await request("/api/auth/me",{cookie:customerCookie})).status,200);
    assert.equal((await request("/api/auth/me",{cookie:operatorCookie})).status,200);
    await restart(false);
    for(const cookie of cookies) assert.equal((await request("/api/auth/me",{cookie})).status,401);
    assert.equal((await request("/api/auth/me",{cookie:customerCookie})).status,200);
    assert.equal((await request("/api/auth/me",{cookie:operatorCookie})).status,200);
    assert.equal((await request(create,{method:"POST",cookie:operatorCookie,body:ack})).status,404);
    assert.equal((await request(target+"/cleanup-preview",{cookie:operatorCookie})).status,404);
    assert.deepEqual(await readStore(),after);
    assert.deepEqual((await request("/api/agent/approval-audit-checkpoint",{cookie:operatorCookie})).data,preservedCheckpoint.data);
    assert.equal((await request("/api/agent/proposals",{cookie:operatorCookie})).data.auditIntegrity,"verified");
    assert.deepEqual(after.agentActionProposals,f.state.agentActionProposals);
    assert.deepEqual(after.agentProposalAuditTrail,f.state.agentProposalAuditTrail);
    t.diagnostic("nonempty agent proposal ledger and HMAC audit chain preserved exactly; cross-references blocked");
    t.diagnostic("exact organization/users/memberships removed; sessions revoked across restart; unrelated data preserved; flags disabled");
  });
}
