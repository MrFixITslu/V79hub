import test from "node:test";
import assert from "node:assert/strict";
import { spawn, type ChildProcess } from "node:child_process";
import { createServer } from "node:http";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
// @ts-expect-error Existing JavaScript security module has no TypeScript declarations.
import { totpCode } from "../../server/security-contract.mjs";

async function availableUrl() {
  const socket=createServer();
  await new Promise<void>(resolve=>socket.listen(0,"127.0.0.1",()=>resolve()));
  const address=socket.address();
  if (!address || typeof address==="string") throw new Error("No ephemeral TCP port");
  const origin="http://127.0.0.1:"+address.port;
  await new Promise(resolve=>socket.close(resolve));
  return origin;
}

test("actual V79 Hub + actual Business Agent complete MFA-fenced CEO/COO handoff on synthetic localhost only", {timeout:110000}, async t=>{
  const dir=await mkdtemp(join(tmpdir(),"v79-real-agent-internal-only-"));
  const hubOrigin=await availableUrl();
  const agentOrigin=await availableUrl();
  const secret="SYNTHETIC-BUSINESS-AGENT-TOKEN-ONLY-NEVER-DEPLOY";
  const workerToken="SYNTHETIC-WORKFORCE-WORKER-TOKEN-ONLY-NEVER-DEPLOY";
  const workerTokenFile=join(dir,"synthetic-worker.token");
  await writeFile(workerTokenFile,workerToken,{mode:0o600});
  const base=resolve(process.cwd(),"..");
  const children: ChildProcess[]=[];
  t.after(async()=>{
    for(const child of children){
      if(child.exitCode===null){
        child.kill();
        await Promise.race([
          new Promise(resolve=>child.once("exit",resolve)),
          new Promise(resolve=>setTimeout(resolve,1500)),
        ]);
      }
    }
    await rm(dir,{recursive:true,force:true});
  });
  const common={
    NODE_ENV:"production",
    V79_AGENT_API_TOKEN:secret,
    V79_HUB_ADMIN_EMAIL:"vision79slu@gmail.com",
    WIPAY_ENABLED:"0",
    V79_SENTINEL_HUB_SERVICE_ENABLED:"0",
    V79_SENTINEL_GRANT_ADMIN_ENABLED:"0",
    V79_SENTINEL_OWNER_MAPPING_ATTESTED:"0",
    V79_EXECUTIVE_MODEL_CYCLE_ENABLED:"0",
  };
  const forbiddenOrigin="http://127.0.0.1:9";
  // Hub has no live Tiquet, finance, market, POS, real accounts or remote URLs.
  const hub=spawn(process.execPath,["--import","tsx","server.ts"],{
    cwd:base,env:{
      ...process.env,...common,
      DATA_DIR:dir,PORT:new URL(hubOrigin).port,APP_URL:hubOrigin,
      V79_HUB_STORE_BACKEND:"json",
      V79_HUB_ADMIN_PASSWORD:"synthetic-owner-password-123456789",
      V79_REQUIRE_ADMIN_MFA:"1",
      V79_HUB_SECURITY_KEY:"SYNTHETIC-LOCAL-SECURITY-KEY-LONG-ENOUGH",
      V79_WORKFORCE_AUDIT_KEY:"SYNTHETIC-WORKFORCE-AUDIT-KEY-LONG-ENOUGH",
      V79_WORKFORCE_TOKEN_FILE:workerTokenFile,
      V79_WORKFORCE_ACTIONS_ENABLED:"1",
      V79_PLATFORM_SHARED_SECRET:"SYNTHETIC-LOCAL-PLATFORM-KEY-LONG-ENOUGH",
      V79_AGENT_INTERNAL_URL:agentOrigin,
      POS_BASE_URL:forbiddenOrigin,FFPRO_INTERNAL_URL:forbiddenOrigin,
      TIQUET_INTERNAL_URL:forbiddenOrigin,MARKETING_INTERNAL_URL:forbiddenOrigin,
      ACADEMY_INTERNAL_URL:forbiddenOrigin,LASERTAG_INTERNAL_URL:forbiddenOrigin,
      WEBSITE_INTERNAL_URL:forbiddenOrigin,GAMES_INTERNAL_URL:forbiddenOrigin,
    },stdio:["ignore","pipe","pipe"],
  });
  children.push(hub);
  let hubOutput="";
  hub.stdout.on("data",d=>hubOutput=(hubOutput+d).slice(-900));
  hub.stderr.on("data",d=>hubOutput=(hubOutput+d).slice(-900));
  const agent=spawn(process.execPath,["--import","tsx","src/index.ts"],{
    cwd:process.cwd(),env:{
      ...process.env,...common,
      PORT:new URL(agentOrigin).port,
      V79_HUB_AGENT_SNAPSHOT_URL:hubOrigin+"/internal/agent/snapshot",
      V79_AGENT_MODEL_PROVIDER:"ollama",
      OLLAMA_OPENAI_BASE_URL:forbiddenOrigin+"/v1",
      OLLAMA_PREWARM_TIMEOUT_MS:"300",
    },stdio:["ignore","pipe","pipe"],
  });
  children.push(agent);
  let agentOutput="";
  agent.stdout.on("data",d=>agentOutput=(agentOutput+d).slice(-900));
  agent.stderr.on("data",d=>agentOutput=(agentOutput+d).slice(-900));
  const wait=async(origin:string,endpoint:string,child:ChildProcess,log:()=>string)=>{
    for(let i=0;i<250;i++){
      if(child.exitCode!==null)break;
      try {
        const r=await fetch(origin+endpoint,{signal:AbortSignal.timeout(700)});
        if(r.ok)return;
      }catch{}
      await new Promise(r=>setTimeout(r,125));
    }
    assert.fail("local synthetic service startup failed: "+log().slice(-650));
  };
  await Promise.all([
    wait(hubOrigin,"/api/health",hub,()=>hubOutput),
    wait(agentOrigin,"/health",agent,()=>agentOutput),
  ]);
  const call=(path:string,options:RequestInit={})=>fetch(hubOrigin+path,{
    redirect:"manual",signal:AbortSignal.timeout(25000),...options,
  });
  const anon=await call("/api/agent/executive-structure");
  assert.equal(anon.status,401);
  const fake=await call("/api/agent/executive-handoff",{
    method:"POST",headers:{"content-type":"application/json"},body:"{}",
  });
  assert.equal(fake.status,401);
  // The real agent requires an internal token for its independent API.
  assert.equal((await fetch(agentOrigin+"/api/agent/executive-structure")).status,401);

  const login=await call("/api/auth/login",{
    method:"POST",headers:{"content-type":"application/json"},
    body:JSON.stringify({username:"admin",password:"synthetic-owner-password-123456789"}),
  });
  assert.equal(login.status,202);
  const challenge=await login.json();
  assert.equal(challenge.mfaRequired,true);
  const mfa=await call("/api/auth/mfa/complete-login",{
    method:"POST",headers:{"content-type":"application/json"},
    body:JSON.stringify({challengeId:challenge.challengeId,code:totpCode(challenge.secret)}),
  });
  assert.equal(mfa.status,200,await mfa.clone().text());
  const cookie=(mfa.headers.get("set-cookie")||"").split(";")[0];
  assert.match(cookie,/^v79_hub_session=/);
  const headers={cookie,origin:hubOrigin,"content-type":"application/json"};

  const structure=await call("/api/agent/executive-structure",{headers});
  assert.equal(structure.status,200,await structure.clone().text());
  const team=await structure.json();
  assert.deepEqual(team.roles.map((r:{id:string})=>r.id),["ceo","coo"]);
  assert.equal(team.actionsEnabled,false);
  assert.equal(team.applicationWriteAdaptersEnabled,false);

  const handoff=await call("/api/agent/executive-handoff",{
    method:"POST",
    headers:{...headers,"x-v79-agent-token":"forged-client-token"},
    body:JSON.stringify({context:{ownerAgent:false,organizationId:"synthetic-attacker"}}),
  });
  assert.equal(handoff.status,200,await handoff.clone().text());
  const brief=await handoff.json();
  assert.equal(brief.mode,"read-only");
  assert.equal(brief.from,"coo");
  assert.equal(brief.to,"ceo");
  assert.equal(brief.executionEnabled,false);
  assert.equal(brief.appRecordsChanged,false);
  assert.equal(brief.customerCommunicationSent,false);
  assert.equal(brief.ownerApprovalGranted,false);
  assert.ok(Array.isArray(brief.cooReport.findings));
  assert.equal(brief.state,"ceo-review-only");
  // All connected-app data are intentionally unavailable in this no-network
  // test, never incorrectly represented as a verified business all-clear.
  assert.equal(brief.source.status,"incomplete");
  assert.equal((await call("/api/agent/executive-preview",{
    method:"POST",headers,body:"{}",
  })).status,404);

  // Actual Hub owner session must approve the exact G2 action before a
  // separate authenticated worker can create a real disposable work record.
  assert.equal((await call("/api/agent/work-actions")).status,401);
  const taskInput={operation:"create_work_item",system:"hub",summary:"Review synthetic Hub release readiness",
    payload:{detail:"Review the disposable test backlog and prepare a release plan."},idempotencyKey:"synthetic-real-hub-work-item-1234"};
  const jobResponse=await call("/api/agent/work-actions",{method:"POST",headers,body:JSON.stringify(taskInput)});
  assert.equal(jobResponse.status,201,await jobResponse.clone().text());
  const job=(await jobResponse.json()).job;
  const workerHeaders={"content-type":"application/json","x-v79-workforce-token":workerToken};
  const workCall=()=>call("/internal/workforce/execute-work-item",{method:"POST",headers:workerHeaders,body:"{}"});
  assert.equal((await (await workCall()).json()).job,null);
  const approve=await call("/api/agent/work-actions/"+job.id+"/decision",{method:"POST",headers,
    body:JSON.stringify({decision:"approve",expectedRevision:1,digest:job.digest})});
  assert.equal(approve.status,200,await approve.clone().text());
  const execution=await workCall();
  assert.equal(execution.status,200,await execution.clone().text());
  assert.equal((await execution.json()).job.status,"succeeded");
  assert.equal((await (await workCall()).json()).job,null);
  const queue=await call("/api/agent/work-actions",{headers});
  assert.equal((await queue.json()).tasks.length,1);
  assert.equal((await call("/internal/workforce/execute-work-item",{method:"POST",
    headers:{"content-type":"application/json","x-v79-agent-token":secret},body:"{}"})).status,403);

  const logout=await call("/api/auth/logout",{method:"POST",headers,body:"{}"});
  assert.equal(logout.status,200);
  assert.equal((await call("/api/agent/executive-structure",{headers})).status,401);
  assert.equal((await call("/api/agent/work-actions",{headers})).status,401);
});
