import test from "node:test";
import assert from "node:assert/strict";
import { beginTrial, accessDecision, classifyLegacyPlan } from "../server/subscription-access.mjs";
import { organizationCanAccessApp, enabledAppIds } from "../server/organization-access.mjs";

const now = Date.parse("2026-10-08T12:00:00.000Z");
function storeFor(plan, status = "active") {
  return {
    organizations: [{ id: "customer", status }],
    organizationPlans: plan ? [{ organizationId: "customer", ...plan }] : [],
    appEntitlements: [{ organizationId: "customer", appId: "app-tiquet", enabled: true }],
  };
}
test("14 days exact and time-bound on every access decision", () => {
  const trial = beginTrial(now);
  assert.equal(Date.parse(trial.trialEndsAt) - Date.parse(trial.trialStartedAt), 14 * 86400000);
  assert.equal(organizationCanAccessApp(storeFor(trial), "customer", "app-tiquet", "", now), true);
  assert.equal(organizationCanAccessApp(storeFor(trial), "customer", "app-tiquet", "", Date.parse(trial.trialEndsAt) - 1), true);
  assert.equal(organizationCanAccessApp(storeFor(trial), "customer", "app-tiquet", "", Date.parse(trial.trialEndsAt)), false);
  assert.equal(enabledAppIds(storeFor(trial), "customer", "", Date.parse(trial.trialEndsAt)).length, 0);
  assert.equal(accessDecision(trial, Date.parse(trial.trialEndsAt)).reason, "trial_expired");
});
test("cancelled and paused plans never authorize an enabled app", () => {
  const plan = beginTrial(now);
  for (const status of ["paused","cancelled"]) {
    assert.equal(organizationCanAccessApp(storeFor({ ...plan, status }), "customer", "app-tiquet", "", now), false);
  }
});
test("missing, invalid or tampered trial dates fail closed", () => {
  const plan = beginTrial(now);
  for (const invalid of [
    { ...plan, trialEndsAt: "" },
    { ...plan, trialEndsAt: "2099-01-01T00:00:00.000Z" },
    { ...plan, trialStartedAt: "" },
    { ...plan, status: "active" },
  ]) assert.equal(organizationCanAccessApp(storeFor(invalid), "customer", "app-tiquet", "", now), false);
  assert.equal(organizationCanAccessApp(storeFor(null), "customer", "app-tiquet", "", now), false);
});
test("paid plan requires verified access period and status", () => {
  const paid={status:"active",accessPolicyType:"paid",paidThroughAt:"2026-11-08T12:00:00.000Z"};
  assert.equal(organizationCanAccessApp(storeFor(paid), "customer", "app-tiquet", "", now),true);
  assert.equal(organizationCanAccessApp(storeFor(paid), "customer", "app-tiquet", "", Date.parse(paid.paidThroughAt)),false);
  assert.equal(organizationCanAccessApp(storeFor({...paid,paidThroughAt:""}), "customer", "app-tiquet", "", now),false);
});
test("owner exception is explicit and cannot be requested by customer id", () => {
  assert.equal(organizationCanAccessApp(storeFor(null), "customer", "app-tiquet", "customer", now), true);
  assert.equal(organizationCanAccessApp(storeFor(null), "customer", "app-tiquet", "v79-owner", now), false);
  assert.equal(organizationCanAccessApp(storeFor(beginTrial(now),"suspended"),"customer","app-tiquet","customer",now),false);
});
test("legacy active plans are not silently treated as verified payments",()=>{
  const original={organizationId:"customer",status:"active"};
  assert.equal(classifyLegacyPlan(original).accessPolicyType,"legacy_review");
  assert.equal(accessDecision(classifyLegacyPlan(original), now).allowed, false);
  assert.equal(classifyLegacyPlan(original,true).accessPolicyType,"internal");
});
