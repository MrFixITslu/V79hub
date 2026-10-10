import test from "node:test";
import assert from "node:assert/strict";
import { planLegacySubscriptions, approveReviewedLegacyTrial } from "../server/legacy-plan-migration.mjs";
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

test("one explicitly founder-approved legacy trial preserves owner and app grants", () => {
  const owner = "v79-owner";
  const source=legacy();
  const verified = { organizationId:"customer-1", ownerOrganizationId:owner,
    approvedByUserId:"owner-user", verifiedOwnerUserId:"owner-user",
    decision:"trial", approvedAt:"2026-10-08T16:00:00Z",
    reason:"Founder-approved existing beta customer trial." };
  const original=JSON.stringify(source);
  const { planned, approvedPlan }=approveReviewedLegacyTrial(source,verified);
  assert.equal(JSON.stringify(source),original);
  assert.equal(approvedPlan.accessPolicyType,"trial");
  assert.equal(approvedPlan.status,"trial");
  assert.equal(approvedPlan.trialEndsAt,"2026-10-22T16:00:00.000Z");
  assert.equal(organizationCanAccessApp(planned,"customer-1","app-tiquet",owner,Date.parse("2026-10-08T17:00:00Z")),true);
  assert.equal(organizationCanAccessApp(planned,"customer-1","app-tiquet",owner,Date.parse(approvedPlan.trialEndsAt)),false);
  assert.equal(organizationCanAccessApp(planned,owner,"app-tiquet",owner),true);
  assert.equal(planned.appEntitlements.length,source.appEntitlements.length);
  assert.throws(()=>approveReviewedLegacyTrial(planned,verified),/existing trial or paid/);
});
test("no founder-approved legacy access can become paid by assertion",()=>{
  const original=legacy();
  const base={ organizationId:"customer-1", ownerOrganizationId:"v79-owner",
    approvedByUserId:"owner-user", verifiedOwnerUserId:"owner-user",
    approvedAt:"2026-10-08T16:00:00Z", reason:"Verified founder signoff requested by customer." };
  assert.throws(()=>approveReviewedLegacyTrial(original,{...base,decision:"paid"}),/Verified paid migration requires/);
  assert.throws(()=>approveReviewedLegacyTrial(original,{...base,decision:"trial",approvedByUserId:"not-owner"}),/founder approval/);
  assert.throws(()=>approveReviewedLegacyTrial(original,{...base,decision:"trial",organizationId:"v79-owner"}),/distinct customer/);
  assert.throws(()=>approveReviewedLegacyTrial(original,{...base,decision:"trial",reason:"x"}),/founder approval/);
});
test("founder may explicitly restrict a legacy account without creating a paid claim",()=>{
  const original=legacy();
  const {planned,approvedPlan}=approveReviewedLegacyTrial(original,{
    organizationId:"customer-2", ownerOrganizationId:"v79-owner",
    approvedByUserId:"owner-user",verifiedOwnerUserId:"owner-user",
    approvedAt:"2026-10-08T16:00:00Z",decision:"restrict",
    reason:"Customer legacy organisation awaiting a manual review.",
  });
  assert.equal(approvedPlan.status,"paused");
  assert.equal(approvedPlan.accessPolicyType,"legacy_review");
  assert.equal(organizationCanAccessApp(planned,"customer-2","app-tiquet","v79-owner"),false);
});
