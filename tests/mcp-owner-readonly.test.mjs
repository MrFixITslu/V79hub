import test from "node:test";
import assert from "node:assert/strict";
import crypto from "node:crypto";
import fs from "node:fs";
import { mcpReadAccessDecision, verifyMcpDownstreamAssertion, ownerMcpAppProjection } from "../server/mcp-owner-readonly.mjs";

const NOW = 1_792_000_000_000;
const issuer = "https://issuer.v79-mcp.invalid";
const org = "org-v79-owner-001";
const userId = "owner-v79-001";
const { publicKey, privateKey } = crypto.generateKeyPairSync("rsa", { modulusLength: 2048 });
const pem = publicKey.export({ type: "spki", format: "pem" });
const options = { publicKeyPem: pem, kid: "key-2026-01", issuer };
const headers = { alg: "RS256", typ: "at+jwt", kid: "key-2026-01" };
const claim = {
  iss: issuer, aud: "v79-hub-mcp-readonly", sub: userId, tenant: org,
  client_id: "v79-mcp-internal", agent_id: "v79-coo", scope: "hub.apps.read",
  iat: NOW / 1000 - 20, nbf: NOW / 1000 - 20, exp: NOW / 1000 + 60,
  jti: "synthetic-read-nonce-01",
};
const encode = value => Buffer.from(JSON.stringify(value)).toString("base64url");
function sign(payload=claim, header=headers, signer=privateKey) {
  const input = encode(header) + "." + encode(payload);
  return input + "." + crypto.sign("RSA-SHA256", Buffer.from(input, "ascii"), signer).toString("base64url");
}
function makeStore() {
  return {
    users: [{ id: userId, email: "vision79slu@gmail.com", role: "admin" }],
    organizations: [{ id: org, status: "active" }],
    memberships: [{ organizationId: org, userId, status: "active", role: "owner" }],
    organizationPlans: [{ organizationId: org, status: "active", accessPolicyType: "internal" }],
    ecosystemApps: [
      { id: "app-tiquet", name: "V79Tiquet" },
      { id: "app-pos", name: "V79 POS" },
      { id: "app-custom-outside", name: "Outside", ownerOrganizationId: "someone-else" },
    ],
    appEntitlements: [
      { organizationId: org, appId: "app-tiquet", enabled: true },
      { organizationId: org, appId: "app-pos", enabled: false },
      { organizationId: org, appId: "app-custom-outside", enabled: true },
    ],
  };
}
function decide({ token=sign(), store=makeStore(), enabled=true, method="GET", cookie="", authorization,
                 tokenOptions=options }={}) {
  return mcpReadAccessDecision({
    enabled, method, authorization: authorization ?? "Bearer " + token, cookie,
    tokenOptions, store, ownerOrganizationId: org, ownerUserId: userId,
    ownerEmail: "vision79slu@gmail.com", now: NOW,
  });
}

test("disabled route is inert and does not validate credentials", () => {
  assert.deepEqual(decide({enabled:false}), {status:404,error:"MCP_DISABLED"});
});
test("only GET is allowed", () => {
  for (const method of ["POST", "PUT", "DELETE", "PATCH"]) {
    assert.equal(decide({method}).status,405);
  }
});
test("browser cookies never authenticate delegated API", () => {
  assert.equal(decide({cookie:"v79_session=abc"}).status,401);
});
test("missing bearer is denied", () => {
  assert.equal(decide({authorization:""}).status,401);
});
test("untrusted bearer syntax is denied", () => {
  assert.equal(decide({authorization:"Basic foo"}).status,401);
});
test("RSA signed downstream assertion validates in isolation", () => {
  let p=verifyMcpDownstreamAssertion({token:sign(),...options,now:NOW});
  assert.deepEqual(Object.keys(p).sort(),["userId","organizationId","agentId","clientId","jti"].sort());
});
test("owner-only entitled minimal app list", () => {
  const r=decide();
  assert.equal(r.status,200);
  assert.deepEqual(r.body,{
    apps:[{id:"app-tiquet",name:"V79Tiquet"}],
    readOnly:true,tenantScoped:true
  });
});
test("owner MFA/session cookies cannot serve as credentials", () => {
  assert.equal(decide({authorization:"Bearer session-token-value"}).status,403);
});
test("forged signature denied", () => {
  const token=sign(), parts=token.split(".");
  parts[1]=encode({...claim,tenant:"someone-else"});
  assert.equal(decide({token:parts.join(".")}).status,403);
});
test("wrong audience and issuer denied", () => {
  assert.equal(decide({token:sign({...claim,aud:"v79-mcp"})}).status,403);
  assert.equal(decide({token:sign({...claim,iss:"https://evil.invalid"})}).status,403);
});
test("wrong OAuth client and fake agent denied", () => {
  assert.equal(decide({token:sign({...claim,client_id:"browser"})}).status,403);
  assert.equal(decide({token:sign({...claim,agent_id:"wildcard-agent"})}).status,403);
});
test("write/wildcard scope denied", () => {
  for (const scope of ["hub.apps.write","*","hub.apps.read hub.apps.write"]) {
    assert.equal(decide({token:sign({...claim,scope})}).status,403);
  }
});
test("expiration, future time and long lifetime denied", () => {
  assert.equal(decide({token:sign({...claim,exp:NOW/1000-1})}).status,403);
  assert.equal(decide({token:sign({...claim,iat:NOW/1000+30})}).status,403);
  assert.equal(decide({token:sign({...claim,exp:NOW/1000+500})}).status,403);
});
test("missing tenant or subject denied", () => {
  assert.equal(decide({token:sign({...claim,tenant:""})}).status,403);
  assert.equal(decide({token:sign({...claim,sub:""})}).status,403);
});
test("token identity outside owner org denied", () => {
  assert.equal(decide({token:sign({...claim,tenant:"other-company"})}).status,403);
  assert.equal(decide({token:sign({...claim,sub:"other-user"})}).status,403);
});
test("revoked owner membership denied immediately", () => {
  const store=makeStore();
  store.memberships[0].status="revoked";
  assert.equal(decide({store}).status,403);
});
test("suspended organization denied", () => {
  const store=makeStore();store.organizations[0].status="suspended";
  assert.equal(decide({store}).status,403);
});
test("owner identity and role must match exact expected account", () => {
  const store=makeStore();store.users[0].email="wrong@example.invalid";
  assert.equal(decide({store}).status,403);
  const store2=makeStore();store2.memberships[0].role="staff";
  assert.equal(decide({store:store2}).status,403);
});
test("app entitlement removal immediately affects projection", () => {
  const store=makeStore();store.appEntitlements=[];
  assert.deepEqual(decide({store}).body.apps,[]);
});
test("noncanonical JWT JSON claims denied before cryptographic validation", () => {
  const body=Buffer.from(JSON.stringify(claim)+" ").toString("base64url");
  const h=encode(headers), input=h+"."+body;
  const sig=crypto.sign("RSA-SHA256",Buffer.from(input,"ascii"),privateKey).toString("base64url");
  assert.equal(decide({token:input+"."+sig}).status,403);
});
test("duplicate JSON member denied even with valid signature", () => {
  const payload=JSON.stringify(claim).replace('"iss":', '"iss":"https://evil.invalid","iss":');
  const input=encode(headers)+"."+Buffer.from(payload).toString("base64url");
  const sig=crypto.sign("RSA-SHA256",Buffer.from(input,"ascii"),privateKey).toString("base64url");
  assert.equal(decide({token:input+"."+sig}).status,403);
});
test("signer key mismatch and unsupported algorithms denied", () => {
  const evil=crypto.generateKeyPairSync("rsa",{modulusLength:2048});
  assert.equal(decide({token:sign(claim,headers,evil.privateKey)}).status,403);
  assert.equal(decide({token:sign(claim,{...headers,alg:"none"})}).status,403);
});
test("fixed trust parameters must be configured", () => {
  assert.equal(decide({tokenOptions:{...options,publicKeyPem:""}}).status,403);
  assert.equal(decide({tokenOptions:{...options,kid:""}}).status,403);
});
test("no secrets, customer fields or user identifiers in output", () => {
  const x=JSON.stringify(decide().body).toLowerCase();
  for(const forbidden of ["vision79slu@gmail.com",userId,org,"password","access_token","api_key","member"])
    assert.equal(x.includes(forbidden.toLowerCase()),false);
});
test("Hub route is registered before normal browser authorization and disabled by default", () => {
  const c=fs.readFileSync(new URL("../server.ts",import.meta.url),"utf8");
  assert.ok(c.includes('app.all("/api/integrations/mcp/v1/apps"'));
  assert.ok(c.indexOf('app.all("/api/integrations/mcp/v1/apps"') < c.indexOf('app.use("/api", requireAuth)'));
  assert.ok(c.includes('process.env.V79_MCP_READONLY_ENABLE === "1"'));
  assert.ok(c.includes('res.setHeader("Cache-Control", "no-store")'));
});
test("contract intentionally contains no write primitives", () => {
  const c=fs.readFileSync(new URL("../server/mcp-owner-readonly.mjs",import.meta.url),"utf8");
  for(const forbidden of ["fetch(", "exec(", "spawn(", "saveStore(","fs.writeFile","process.env.V79_POS_PLATFORM_SHARED_SECRET"])
    assert.equal(c.includes(forbidden),false);
});
