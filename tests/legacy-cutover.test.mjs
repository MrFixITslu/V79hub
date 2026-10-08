import test from "node:test";
import assert from "node:assert/strict";
import { prepareApprovedLegacyCutover, APPROVED_CUSTOMER_POLICY } from "../server/legacy-cutover.mjs";
import { organizationCanAccessApp } from "../server/organization-access.mjs";
const owner = "vision79-owner", founder = "founder-user", customer = "existing-customer";
const now = "2026-10-16T09:30:00.000Z";
function sample() {
  return {
    organizations: [{id:owner,status:"active"},{id:customer,status:"active"}],
    memberships:[
      {organizationId:owner,userId:founder,role:"owner",status:"active"},
      {organizationId:customer,userId:"customer-owner",role:"owner",status:"active"},
    ],
    appEntitlements:[
      {organizationId:owner,appId:"app-tiquet",enabled:true},
      ...["app-tiquet","app-ffpro","app-v79pos","app-marketing","app-academy"]
        .map(appId=>({organizationId:customer,appId,enabled:true})),
    ],
    organizationPlans: [],
    billingOrders: [], users: [],
  };
}
const args={ownerOrganizationId:owner,verifiedOwnerUserId:founder,customerOrganizationId:customer,activationAt:now};
test("founder decision remains pending until cutover timestamp, then grants 14 exact days",()=>{
  const original=sample(), prior=JSON.stringify(original);
  const result=prepareApprovedLegacyCutover(original,args);
  assert.equal(JSON.stringify(original),prior);
  assert.equal(result.alreadyApplied,false);
  assert.equal(result.summary.approvedOn,"2026-10-08");
  assert.equal(result.summary.trialStart,now);
  assert.equal(result.summary.trialEnd,"2026-10-30T09:30:00.000Z");
  assert.equal(result.summary.retainedEntitlements,5);
  assert.equal(result.planned.organizationPlans.filter(x=>x.organizationId===customer).length,1);
  assert.equal(organizationCanAccessApp(result.planned,customer,"app-tiquet",owner,Date.parse(now)),true);
  assert.equal(organizationCanAccessApp(result.planned,customer,"app-tiquet",owner,Date.parse(result.summary.trialEnd)),false);
  assert.equal(organizationCanAccessApp(result.planned,owner,"app-tiquet",owner),true);
});
test("restart or duplicate activation cannot restart or extend trial",()=>{
  const first=prepareApprovedLegacyCutover(sample(),args);
  const second=prepareApprovedLegacyCutover(first.planned,{...args,activationAt:"2026-10-18T09:30:00.000Z"});
  assert.equal(second.alreadyApplied,true);
  assert.deepEqual(second.planned,first.planned);
  assert.equal(second.summary.trialStart,first.summary.trialStart);
  assert.equal(second.summary.trialEnd,first.summary.trialEnd);
});
test("changed customer or owner inventory, missing memberships and extra entitlements stop activation",()=>{
  const checks=[
    s=>s.organizations.push({id:"unexpected",status:"active"}),
    s=>s.memberships[0].status="revoked",
    s=>s.memberships[1].role="staff",
    s=>s.appEntitlements.push({organizationId:customer,appId:"app-extra",enabled:true}),
    s=>s.appEntitlements[2].appId="app-tiquet",
    s=>s.organizations[1].status="suspended",
  ];
  for (const modify of checks) {
    const state=sample();modify(state);
    assert.throws(()=>prepareApprovedLegacyCutover(state,args));
  }
});
test("cutover will not silently convert a verified paid customer or an unknown owner",()=>{
  const paid=sample();
  paid.organizationPlans=[{organizationId:customer,accessPolicyType:"paid",status:"active",paidThroughAt:"2099-01-01"}];
  assert.throws(()=>prepareApprovedLegacyCutover(paid,args),/classified differently/);
  assert.throws(()=>prepareApprovedLegacyCutover(sample(),{...args,verifiedOwnerUserId:"intruder"}),/Verified platform owner/);
  assert.throws(()=>prepareApprovedLegacyCutover(sample(),{...args,customerOrganizationId:owner}),/distinct|identities/);
});
test("approval date is separate from cutover time and is never automatically backdated",()=>{
  assert.equal(APPROVED_CUSTOMER_POLICY.approvedOn,"2026-10-08");
  assert.throws(()=>prepareApprovedLegacyCutover(sample(),{...args,activationAt:"2026-10-07T09:00:00Z"}),/post-approval/);
});

test("trial cutover requires exact UTC ISO timestamp without loose parsing",()=>{
  for (const activationAt of ["2026-10-16","2026-10-16T09:30:00+00:00",
    "October 16, 2026","2026-10-16T09:30Z","2026-02-30T09:30:00.000Z",
    null,undefined,123456]) {
    assert.throws(()=>prepareApprovedLegacyCutover(sample(),{...args,activationAt}),/UTC ISO|valid post-approval/);
  }
});
test("untyped older subscription cannot silently be converted into a trial",()=>{
  const old=sample();
  old.organizationPlans=[{
    organizationId:customer,status:"active",planName:"Legacy unspecified",billingCycle:"monthly",
  }];
  assert.throws(()=>prepareApprovedLegacyCutover(old,args),/classified differently/);
});
