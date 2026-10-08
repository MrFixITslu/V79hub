import test from "node:test";
import assert from "node:assert/strict";
import { planLegacySubscriptions } from "../server/legacy-plan-migration.mjs";
import { organizationCanAccessApp } from "../server/organization-access.mjs";

function legacy() {
  return {
    organizations: [
      { id: "v79-owner", status: "active" },
      { id: "customer-1", status: "active" },
      { id: "customer-2", status: "active" },
    ],
    organizationPlans: [
      { organizationId: "customer-1", planName: "Legacy", status: "active", billingCycle: "custom", appIds: ["app-tiquet"] },
    ],
    appEntitlements: [
      { organizationId: "v79-owner", appId: "app-tiquet", enabled: true },
      { organizationId: "customer-1", appId: "app-tiquet", enabled: true },
      { organizationId: "customer-2", appId: "app-tiquet", enabled: true },
    ],
  };
}
test("migration preview does not touch source and never infers paid or fresh trial", () => {
  const original = legacy();
  const serialized = JSON.stringify(original);
  const { planned, summary, review } = planLegacySubscriptions(original, "v79-owner", "2026-10-08T12:00:00Z");
  assert.equal(JSON.stringify(original), serialized);
  assert.equal(summary.organisations, 3);
  assert.equal(summary.existingPlans, 1);
  assert.equal(summary.proposedPlans, 3);
  assert.equal(summary.customerReviewRequired, 2);
  assert.equal(summary.allowCustomerAccessWithoutVerifiedPolicy, false);
  assert.equal(review.find(x=>x.organizationId==="v79-owner").classification, "internal");
  assert.equal(organizationCanAccessApp(planned,"v79-owner","app-tiquet","v79-owner"), true);
  assert.equal(organizationCanAccessApp(planned,"customer-1","app-tiquet","v79-owner"), false);
  assert.equal(organizationCanAccessApp(planned,"customer-2","app-tiquet","v79-owner"), false);
  assert.equal(planned.organizationPlans.find(x=>x.organizationId==="customer-2").trialEndsAt,undefined);
});
test("migration dry-run is repeatable", () => {
  const first=planLegacySubscriptions(legacy(),"v79-owner","2026-10-08T12:00:00Z");
  const second=planLegacySubscriptions(first.planned,"v79-owner","2026-10-08T12:00:00Z");
  assert.deepEqual(second.planned,first.planned);
});
test("migration fails closed when owner identity is unknown",()=>{
  assert.throws(()=>planLegacySubscriptions(legacy(),""),/owner organisation ID/);
});
