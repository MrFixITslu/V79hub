import test from "node:test";
import assert from "node:assert/strict";
import crypto from "node:crypto";
import {readFileSync} from "node:fs";
import {createSentinelWriteFence} from "../server/sentinel-write-fence.mjs";
import {validateSentinelOwnerGrantRequest,validateSentinelOwnerRevocation}
  from "../server/sentinel-grant-operator.mjs";
import {registerSentinelGrant,revokeSentinelGrant}
  from "../server/sentinel-service-grants.mjs";
import {validateSentinelServiceEntitlement}
  from "../server/sentinel-service-entitlement.mjs";

const now=Date.parse("2026-10-10T21:00:00.000Z");
const owner=crypto.randomUUID();
const userId=crypto.randomUUID();
const expected={sentinelCustomerId:crypto.randomUUID(),
  tiquetAccountId:crypto.randomUUID(),tiquetClientId:crypto.randomUUID()};
const session={userId,organizationId:owner,role:"owner",mfaVerified:true,mfaVerifiedAt:now-1000};
const user={id:userId,mfaEnabled:true};
const body={confirmation:"AUTHORIZE_ONE_V79_SENTINEL_PILOT",actions:["ticket.create"],
  expiresAt:new Date(now+3600_000).toISOString()};
const opts=(changes={})=>({
  body,session,user,ownerOrganizationId:owner,expected,now,...changes
});
const state=()=>({organizations:[{id:owner,status:"active"}],
  appEntitlements:[{organizationId:owner,appId:"app-tiquet",enabled:true}],
  sentinelServiceGrants:[]});
const auth=(store,action="ticket.create")=>validateSentinelServiceEntitlement(store,{
  request:{serviceId:"v79-sentinel",sentinelCustomerId:expected.sentinelCustomerId,
    organizationId:owner,accountId:expected.tiquetAccountId,
    clientId:expected.tiquetClientId,action},
  ownerOrganizationId:owner,tenantReady:()=>true,now});

test("strict owner-only fresh MFA and exact single-action request",()=>{
  const good=validateSentinelOwnerGrantRequest(opts());
  assert.deepEqual(good.proposal.actions,["ticket.create"]);
  assert.equal(good.proposal.tiquetClientId,expected.tiquetClientId);
  assert.throws(()=>validateSentinelOwnerGrantRequest(opts({
    session:{...session,mfaVerifiedAt:now-301000}
  })));
  assert.throws(()=>validateSentinelOwnerGrantRequest(opts({
    session:{...session,mfaVerified:false}
  })));
  assert.throws(()=>validateSentinelOwnerGrantRequest(opts({
    session:{...session,organizationId:crypto.randomUUID()}
  })));
  assert.throws(()=>validateSentinelOwnerGrantRequest(opts({
    user:{...user,mfaEnabled:false}
  })));
  assert.throws(()=>validateSentinelOwnerGrantRequest(opts({
    expected:{...expected,tiquetClientId:"invalid"}
  })));
  assert.throws(()=>validateSentinelOwnerGrantRequest(opts({
    body:{...body,clientId:crypto.randomUUID()}
  })));
  assert.throws(()=>validateSentinelOwnerGrantRequest(opts({
    body:{...body,actions:["ticket.close"]}
  })));
  assert.throws(()=>validateSentinelOwnerGrantRequest(opts({
    body:{...body,expiresAt:new Date(now+2*86400_000).toISOString()}
  })));
  assert.throws(()=>validateSentinelOwnerGrantRequest(opts({
    body:{...body,confirmation:"approve"}
  })));
});

test("scoped grant persists, is revocable and never grants ticket recovery/close",()=>{
  const intent=validateSentinelOwnerGrantRequest(opts());
  const created=registerSentinelGrant(state(),{
    ...intent,ownerOrganizationId:owner,verifyMapping:()=>true,now
  });
  assert.equal(auth(created.store).allowed,true);
  assert.equal(auth(created.store,"ticket.add_recovery_evidence").allowed,false);
  assert.throws(()=>registerSentinelGrant(created.store,{
    ...intent,ownerOrganizationId:owner,verifyMapping:()=>true,now
  }));
  const revocation=validateSentinelOwnerRevocation({
    grantId:created.grant.id,confirmation:"REVOKE_V79_SENTINEL_PILOT",
    session,user,ownerOrganizationId:owner,now
  });
  const revoked=revokeSentinelGrant(created.store,revocation);
  assert.equal(auth(revoked).allowed,false);
  assert.equal(revoked.sentinelServiceGrants[0].revokedBy,userId);
  assert.throws(()=>validateSentinelOwnerRevocation({
    grantId:created.grant.id,confirmation:"REVOKE_V79_SENTINEL_PILOT",
    session:{...session,mfaVerifiedAt:now-400000},user,ownerOrganizationId:owner,now
  }));
});


test("grant issuance and revocation use ordinary fenced writes, not QA-only exclusive persistence",()=>{
  const server=readFileSync(new URL("../server.ts",import.meta.url),"utf8");
  const start=server.indexOf('const SENTINEL_GRANT_ADMIN=');
  const end=server.indexOf('function billingServiceFromRequest(',start);
  assert(start>0 && end>start,"Grant HTTP routes must be registered before billing service endpoints");
  const routes=server.slice(start,end);
  assert.equal((routes.match(/await commitStore\(/g)||[]).length,2,"Both issue and revoke must persist through ordinary Hub writes");
  assert.doesNotMatch(routes,/commitSentinelStore\(/,"QA-exclusive persistence would reject normal admin grants");
  const fence=createSentinelWriteFence();
  const finish=fence.beginStoreSave();
  finish();
  assert.throws(()=>fence.beginStoreSave({sentinel:true}),/outside exclusive maintenance window/);
});
