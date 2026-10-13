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

  // Internal-only, synthetic bank transfer journey in the same isolated
  // full Hub process, with a REAL fresh-MFA owner session. The CI test is not
  // checking a bank account and does not confer entitlement in live V79.
  async function syntheticCustomer(name,email,price) {
    const invited=await call("/api/admin/onboarding/invitations",{
      method:"POST",headers,
      body:JSON.stringify({organizationName:name,email,appIds:["app-tiquet"],expiresInHours:24}),
    });
    assert.equal(invited.status,201,await invited.clone().text());
    const invite=await invited.json();
    const token=new URLSearchParams(new URL(invite.inviteUrl).hash.slice(1)).get("invite");
    assert.ok(token);
    const joined=await call("/api/onboarding/invitation/accept",{
      method:"POST",headers:{"origin":hubUrl,"content-type":"application/json","x-v79-invite-token":token},
      body:JSON.stringify({fullName:"Synthetic Test Customer",password:"synthetic-test-customer-password-123"}),
    });
    assert.equal(joined.status,201,await joined.clone().text());
    const details=await joined.json();
    const session=(joined.headers.get("set-cookie")||"").split(";")[0];
    assert.match(session,/^v79_hub_session=/);
    const change=await call(`/api/admin/customers/${details.organization.id}/plan`,{
      method:"PUT",headers,body:JSON.stringify({
        planName:"Internal Test Plan",status:"trial",billingCycle:"monthly",
        priceXcd:price,renewalDate:"2027-01-15",appIds:["app-tiquet"],
        reason:"Disposable CI-only internal Hub manual billing acceptance",
      }),
    });
    assert.equal(change.status,200,await change.clone().text());
    return {id:details.organization.id,session,requestHeaders:{origin:hubUrl,cookie:session,"content-type":"application/json"}};
  }
  const customerA=await syntheticCustomer("Ephemeral Billing A","ci-a@example.invalid",199);
  const customerB=await syntheticCustomer("Ephemeral Billing B","ci-b@example.invalid",149);

  async function invoice(customer,expected) {
    const requested=await call("/api/billing/manual/request",{
      method:"POST",headers:customer.requestHeaders,body:"{}",
    });
    assert.equal(requested.status,201,await requested.clone().text());
    const data=await requested.json();
    assert.equal(data.order.status,"pending");
    assert.equal(data.order.currency,"XCD");
    assert.equal(data.order.amount,expected);
    assert.equal(data.pendingVerification,true);
    return data.order.id;
  }
  const orderA=await invoice(customerA,199);
  const orderB=await invoice(customerB,149);
  const ownerOrders=await call("/api/admin/billing/manual/orders",{headers});
  assert.equal(ownerOrders.status,200);
  assert.equal((await ownerOrders.json()).orders.length,2);
  assert.equal((await call("/api/admin/billing/manual/orders",{
    headers:{cookie:customerA.session},
  })).status,403);

  const confirmation=(id,amount,ref,verified)=>JSON.stringify({
    bankReference:ref,receivedAmount:amount,
    evidenceNote:"CI-ONLY fictional test ledger, not actual bank funds",
    bankStatementVerified:verified,confirmation:"CONFIRM "+id,
  });
  const ownerConfirmA=`/api/admin/billing/manual/orders/${orderA}/confirm`;
  const deniedClaim=await call(ownerConfirmA,{
    method:"POST",headers,body:confirmation(orderA,199,"SYNTHETIC-ONLY-REF-001",false),
  });
  assert.equal(deniedClaim.status,409,"bank statement proof cannot be omitted");
  assert.equal((await (await call("/api/billing/summary",{headers:{cookie:customerA.session}})).json()).status,"trial");
  assert.equal((await call(ownerConfirmA,{
    method:"POST",headers:customerA.requestHeaders,
    body:confirmation(orderA,199,"SYNTHETIC-ONLY-REF-001",true),
  })).status,403,"customer cannot mark an invoice paid");

  // The affirmative assertion exists ONLY in this disposable test environment.
  const approved=await call(ownerConfirmA,{
    method:"POST",headers,body:confirmation(orderA,199,"SYNTHETIC-ONLY-REF-001",true),
  });
  assert.equal(approved.status,200,await approved.clone().text());
  assert.equal((await approved.json()).verified,true);
  const paidSummary=await (await call("/api/billing/summary",{headers:{cookie:customerA.session}})).json();
  assert.equal(paidSummary.status,"active");
  const customerBPlan=await (await call("/api/billing/summary",{headers:{cookie:customerB.session}})).json();
  assert.equal(customerBPlan.status,"trial","unrelated tenant retains unpaid trial");
  const replay=await call(ownerConfirmA,{
    method:"POST",headers,body:confirmation(orderA,199,"SYNTHETIC-ONLY-REF-001",true),
  });
  assert.equal(replay.status,409,"identical approval must not be replayed");
  const reused=await call(`/api/admin/billing/manual/orders/${orderB}/confirm`,{
    method:"POST",headers,body:confirmation(orderB,149,"SYNTHETIC-ONLY-REF-001",true),
  });
  assert.equal(reused.status,409,"same pseudo bank reference cannot settle another tenant");
  const ordersB=await (await call("/api/billing/orders",{headers:{cookie:customerB.session}})).json();
  assert.equal(ordersB.orders[0].status,"pending");
  assert.equal(captured.length,3,"billing must not contact CEO/COO agent or execute financial agent actions");

  const logout=await call("/api/auth/logout",{method:"POST",headers,body:"{}"});
  assert.equal(logout.status,200);
  const deniedAfterLogout=await call(paths[0],{headers});
  assert.equal(deniedAfterLogout.status,401,"logout must revoke executive access");
  assert.equal(captured.length,3,"no revoked session request reaches agent");
});
