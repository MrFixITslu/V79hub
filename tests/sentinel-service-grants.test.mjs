import test from "node:test";
import assert from "node:assert/strict";
import crypto from "node:crypto";
import {registerSentinelGrant,revokeSentinelGrant,validateSentinelGrantCollection} from "../server/sentinel-service-grants.mjs";
import {validateSentinelServiceEntitlement} from "../server/sentinel-service-entitlement.mjs";

const now=Date.parse("2026-10-10T16:00:00.000Z");
const owner=crypto.randomUUID(), customer=crypto.randomUUID(), account=crypto.randomUUID(), client=crypto.randomUUID();
const review={userId:crypto.randomUUID(),role:"owner",mfaConfirmed:true,mfaVerifiedAt:now-2000};
const proposal={serviceId:"v79-sentinel",sentinelCustomerId:customer,organizationId:owner,
  tiquetAccountId:account,tiquetClientId:client,actions:["ticket.create","ticket.add_recovery_evidence"],
  expiresAt:new Date(now+4*86400_000).toISOString()};
const options=(state={})=>({proposal,ownerOrganizationId:owner,reviewer:review,
  verifyMapping:()=>true,now,...state});
function store(){
  return {organizations:[{id:owner,status:"active"}],
    appEntitlements:[{organizationId:owner,appId:"app-tiquet",enabled:true}],
    organizationPlans:[],sentinelServiceGrants:[]};
}
function allowed(state){
  return validateSentinelServiceEntitlement(state,{
    request:{serviceId:proposal.serviceId,sentinelCustomerId:customer,
      organizationId:owner,accountId:account,clientId:client,action:"ticket.create"},
    ownerOrganizationId:owner,tenantReady:()=>true,now
  }).allowed;
}
test("only verified owner MFA and exact client mapping can create machine grant",()=>{
  const baseline=store();
  assert.throws(()=>registerSentinelGrant(baseline,options({reviewer:{...review,mfaConfirmed:false}})));
  assert.throws(()=>registerSentinelGrant(baseline,options({reviewer:{...review,role:"staff"}})));
  assert.throws(()=>registerSentinelGrant(baseline,options({reviewer:{...review,mfaVerifiedAt:now-360000}})));
  assert.throws(()=>registerSentinelGrant(baseline,options({verifyMapping:()=>false})));
  assert.throws(()=>registerSentinelGrant(baseline,options({proposal:{...proposal,organizationId:crypto.randomUUID()}})));
  assert.throws(()=>registerSentinelGrant(baseline,options({proposal:{...proposal,actions:["ticket.close"]}})));
  assert.throws(()=>registerSentinelGrant(baseline,options({proposal:{...proposal,expiresAt:new Date(now+30*86400_000).toISOString()}})));
  assert.equal(baseline.sentinelServiceGrants.length,0);
  assert.equal(allowed(baseline),false);
});
test("registered explicit grant is machine scoped, validated, persisted and revocable",()=>{
  const baseline=store();
  const issued=registerSentinelGrant(baseline,options());
  assert.equal(baseline.sentinelServiceGrants.length,0);
  assert.equal(issued.store.sentinelServiceGrants.length,1);
  assert.equal(allowed(issued.store),true);
  assert.deepEqual(validateSentinelGrantCollection(issued.store.sentinelServiceGrants),issued.store.sentinelServiceGrants);
  assert.throws(()=>registerSentinelGrant(issued.store,options()));
  const revoked=revokeSentinelGrant(issued.store,{
    grantId:issued.grant.id,reviewer:review,now:now+1000});
  assert.equal(allowed(revoked),false);
  assert.equal(allowed(issued.store),true); // immutable store snapshots
  assert.equal(validateSentinelGrantCollection(revoked.sentinelServiceGrants).length,1);
  assert.throws(()=>revokeSentinelGrant(revoked,{grantId:issued.grant.id,reviewer:review,now:now+1000}));
  const rotated=registerSentinelGrant(revoked,options({now:now+2000}));
  assert.equal(rotated.store.sentinelServiceGrants.length,2);
  assert.equal(allowed(rotated.store),true);
});
test("malformed persisted grant lists fail closed and never synthesize privileges",()=>{
  assert.deepEqual(validateSentinelGrantCollection([]),[]);
  assert.throws(()=>validateSentinelGrantCollection({}));
  const g=registerSentinelGrant(store(),options()).grant;
  assert.throws(()=>validateSentinelGrantCollection([g,g]));
  assert.throws(()=>validateSentinelGrantCollection([{...g,serviceId:"v79-user"}]));
  assert.throws(()=>validateSentinelGrantCollection([{...g,status:"revoked",enabled:true}]));
  assert.throws(()=>validateSentinelGrantCollection([{...g,actions:["ticket.close"]}]));
});
