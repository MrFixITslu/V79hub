import test from "node:test";
import assert from "node:assert/strict";
import { validateProductEntitlement, ENTITLEMENT_RECHECK_SECONDS } from "../server/entitlement-validation.mjs";
import { beginTrial } from "../server/subscription-access.mjs";
const time=Date.parse("2026-10-08T12:00:00Z");
function createCtx(plan=beginTrial(time)) {
  const org="customer-one";
  const store={
    organizations:[{id:org,status:"active"}],
    memberships:[{organizationId:org,userId:"hub-u1",role:"owner",status:"active"}],
    organizationPlans:[{organizationId:org,...plan}],
    appEntitlements:[{organizationId:org,appId:"app-tiquet",enabled:true}],
  };
  return {
    store,
    args: {
      product:"tiquet",organizationId:org,scopedUserId:"scoped-hub-u1",
      ownerOrganizationId:"v79-owner",now:time,
      resolveScopedUserId: id=>"scoped-"+id,
      memberCanAccessApp: ()=>true,
      roleEligible:()=>true,
      tenantReady:()=>true,
    }
  };
}
test("product revalidation is scoped and time bounded",()=>{
  const {store,args}=createCtx();
  const valid=validateProductEntitlement(store,args);
  assert.equal(valid.allowed,true);
  assert.equal(valid.validForSeconds,ENTITLEMENT_RECHECK_SECONDS);
  assert.equal(validateProductEntitlement(store,{...args,now:Date.parse(store.organizationPlans[0].trialEndsAt)}).allowed,false);
  assert.equal(validateProductEntitlement(store,{...args,scopedUserId:"scoped-hub-u2"}).allowed,false);
  assert.equal(validateProductEntitlement(store,{...args,product:"pos"}).allowed,false);
});
test("app revalidation is fail-closed on cancellations, missing mapping, role or membership",()=>{
  const {store,args}=createCtx();
  assert.equal(validateProductEntitlement(store,{...args,tenantReady:()=>false}).allowed,false);
  assert.equal(validateProductEntitlement(store,{...args,roleEligible:()=>false}).allowed,false);
  assert.equal(validateProductEntitlement(store,{...args,memberCanAccessApp:()=>false}).allowed,false);
  store.organizationPlans[0].status="cancelled";
  assert.equal(validateProductEntitlement(store,args).allowed,false);
  store.organizationPlans[0].status="trial";
  store.memberships[0].status="revoked";
  assert.equal(validateProductEntitlement(store,args).allowed,false);
});
test("near trial boundary response TTL cannot exceed remaining entitlement lifetime",()=>{
  const {store,args}=createCtx();
  const end=Date.parse(store.organizationPlans[0].trialEndsAt);
  const result=validateProductEntitlement(store,{...args,now:end-10_000});
  assert.equal(result.allowed,true);
  assert.equal(result.validForSeconds,10);
  assert.equal(validateProductEntitlement(store,{...args,now:end-500}).allowed,false);
});
