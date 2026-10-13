import test from "node:test";
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createServer } from "node:http";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { totpCode } from "../server/security-contract.mjs";

const syntheticToken="SYNTHETIC_CEO_COO_INTEGRATION_ONLY";
async function listen(server) {
  await new Promise(resolve=>server.listen(0,"127.0.0.1",resolve));
  return `http://127.0.0.1:${server.address().port}`;
}

test("real ephemeral Hub exposes CEO/COO only to founder fresh-MFA session and fixed internal agent API", {timeout:65000}, async t=>{
  const root=await mkdtemp(join(tmpdir(),"v79-g12-ceo-coo-http-"));
  const captured=[];
  const internalAgent=createServer(async(req,res)=>{
    const chunks=[];
    for await (const chunk of req) chunks.push(chunk);
    const body=Buffer.concat(chunks).toString("utf8");
    const path=new URL(req.url,"http://synthetic.invalid").pathname;
    captured.push({method:req.method,path,hasCorrectToken:req.headers["x-v79-agent-token"]===syntheticToken,body});
    if(req.headers["x-v79-agent-token"]!==syntheticToken) {
      res.writeHead(401,{"content-type":"application/json"}).end(JSON.stringify({error:"bad internal token"}));return;
    }
    res.setHeader("content-type","application/json");
    if(req.method==="GET"&&path==="/api/agent/executive-structure") {
      res.end(JSON.stringify({mode:"read-only",actionsEnabled:false,roles:[{id:"ceo"},{id:"coo"}]}));return;
    }
    if(req.method==="POST"&&path==="/api/agent/executive-handoff") {
      res.end(JSON.stringify({mode:"read-only",executionEnabled:false,status:"synthetic-handoff-validated"}));return;
    }
    if(req.method==="POST"&&path==="/api/agent/executive-preview") {
      res.writeHead(404).end(JSON.stringify({error:"Preview disabled"}));return;
    }
    res.writeHead(404).end(JSON.stringify({error:"Unknown fixed route"}));
  });
  const agentUrl=await listen(internalAgent);
  t.after(async()=>{
    internalAgent.closeAllConnections();
    await new Promise(resolve=>internalAgent.close(resolve));
  });
  const portServer=createServer();
  const hubUrl=await listen(portServer);
  await new Promise(resolve=>portServer.close(resolve));

  const child=spawn(process.execPath,["--import","tsx","server.ts"],{
    cwd:process.cwd(),env:{
      ...process.env,
      NODE_ENV:"production",
      V79_HUB_STORE_BACKEND:"json",
      DATA_DIR:root,
      PORT:new URL(hubUrl).port,
      APP_URL:hubUrl,
      V79_HUB_ADMIN_PASSWORD:"synthetic-owner-password-1234567",
      V79_HUB_ADMIN_EMAIL:"vision79slu@gmail.com",
      V79_HUB_SECURITY_KEY:"synthetic-security-key-123456789012345678901",
      V79_PLATFORM_SHARED_SECRET:"synthetic-platform-key-12345678901234567890",
      V79_REQUIRE_ADMIN_MFA:"1",
      V79_AGENT_INTERNAL_URL:agentUrl,
      V79_AGENT_API_TOKEN:syntheticToken,
      WIPAY_ENABLED:"0",
      V79_SENTINEL_HUB_SERVICE_ENABLED:"0",
      V79_SENTINEL_GRANT_ADMIN_ENABLED:"0",
      V79_SENTINEL_OWNER_MAPPING_ATTESTED:"0",
    },stdio:["ignore","pipe","pipe"],
  });
  let logs="";
  child.stdout.on("data",x=>{logs+=x;logs=logs.slice(-8000)});
  child.stderr.on("data",x=>{logs+=x;logs=logs.slice(-8000)});
  t.after(async()=>{
    if(child.exitCode===null) {
      const exited=new Promise(resolve=>child.once("exit",resolve));
      child.kill();
      await Promise.race([exited,new Promise(resolve=>setTimeout(resolve,1500))]);
    }
    await rm(root,{recursive:true,force:true});
  });
  const call=(path,options={})=>fetch(hubUrl+path,{redirect:"manual",signal:AbortSignal.timeout(8000),...options});
  let ready=false;
  for(let i=0;i<250;i++){
    if(child.exitCode!==null)break;
    try{if((await call("/api/health")).ok){ready=true;break}}catch{}
    await new Promise(r=>setTimeout(r,100));
  }
  assert.equal(ready,true,"synthetic Hub startup failed: "+logs.slice(-1000));

  const paths=["/api/agent/executive-structure","/api/agent/executive-handoff","/api/agent/executive-preview"];
  for(const path of paths) {
    const method=path.endsWith("structure")?"GET":"POST";
    const anon=await call(path,{method,headers:{"content-type":"application/json"},...(method==="POST"?{body:"{}"}:{})});
    assert.equal(anon.status,401,"anonymous executive endpoint must fail");
  }
  assert.equal(captured.length,0,"no anonymous request may reach the agent");

  const login=await call("/api/auth/login",{
    method:"POST",headers:{"content-type":"application/json"},
    body:JSON.stringify({username:"admin",password:"synthetic-owner-password-1234567"}),
  });
  assert.equal(login.status,202);
  const challenge=await login.json();
  assert.equal(challenge.mfaRequired,true);
  assert.match(challenge.secret,/^[A-Z2-7]+$/);
  assert.equal(captured.length,0);

  const complete=await call("/api/auth/mfa/complete-login",{
    method:"POST",headers:{"content-type":"application/json"},
    body:JSON.stringify({challengeId:challenge.challengeId,code:totpCode(challenge.secret)}),
  });
  assert.equal(complete.status,200,await complete.clone().text());
  const cookie=(complete.headers.get("set-cookie")||"").split(";")[0];
  assert.match(cookie,/^v79_hub_session=/);
  const headers={cookie,origin:hubUrl,"content-type":"application/json"};

  const structure=await call(paths[0],{headers});
  assert.equal(structure.status,200);
  const roles=await structure.json();
  assert.deepEqual(roles.roles.map(r=>r.id),["ceo","coo"]);
  assert.equal(roles.actionsEnabled,false);
  assert.equal(structure.headers.get("cache-control"),"no-store");
  assert.equal(captured[0].path,paths[0]);
  assert.equal(captured[0].hasCorrectToken,true);

  const handoff=await call(paths[1],{
    method:"POST",headers:{...headers,"x-v79-agent-token":"forged-web-token"},
    body:JSON.stringify({context:{userId:"attacker",ownerAgent:false,organizationId:"cross-tenant"}}),
  });
  assert.equal(handoff.status,200);
  assert.equal((await handoff.json()).executionEnabled,false);
  assert.equal(captured[1].hasCorrectToken,true);
  const forwarded=JSON.parse(captured[1].body);
  assert.equal(forwarded.context.ownerAgent,true);
  assert.notEqual(forwarded.context.userId,"attacker");
  assert.notEqual(forwarded.context.organizationId,"cross-tenant");
  assert.equal(captured[1].path,paths[1]);

  const preview=await call(paths[2],{method:"POST",headers,body:"{}"});
  assert.equal(preview.status,404,"unapproved model preview must remain disabled");
  assert.equal(captured[2].path,paths[2]);
  assert.equal(captured[2].hasCorrectToken,true);

  const logout=await call("/api/auth/logout",{method:"POST",headers,body:"{}"});
  assert.equal(logout.status,200);
  const deniedAfterLogout=await call(paths[0],{headers});
  assert.equal(deniedAfterLogout.status,401,"logout must revoke executive access");
  assert.equal(captured.length,3,"no revoked session request reaches agent");
});
