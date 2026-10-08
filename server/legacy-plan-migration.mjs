import { classifyLegacyPlan, accessDecision, beginTrial } from "./subscription-access.mjs";

// Pure and repeatable: make a REVIEW proposal without touching live data.
export function planLegacySubscriptions(store, ownerOrganizationId, now = new Date()) {
  if (!ownerOrganizationId || typeof ownerOrganizationId !== "string") {
    throw new Error("Verified owner organisation ID is required.");
  }
  const checkedAt = new Date(now).toISOString();
  const organisations = Array.isArray(store?.organizations) ? store.organizations : [];
  const existingPlans = Array.isArray(store?.organizationPlans) ? store.organizationPlans : [];
  const entitlements = Array.isArray(store?.appEntitlements) ? store.appEntitlements : [];
  const review = [];
  const nextPlans = existingPlans.map(plan => structuredClone(plan));
  for (const org of organisations) {
    const isInternalOwner = org.id === ownerOrganizationId;
    const existing = nextPlans.find(plan => plan.organizationId === org.id);
    const appIds = entitlements.filter(row => row.organizationId === org.id && row.enabled).map(row => row.appId);
    if (existing) {
      const proposed = classifyLegacyPlan(existing, isInternalOwner);
      const index = nextPlans.indexOf(existing);
      nextPlans[index] = proposed;
      review.push({
        organizationId: org.id,
        classification: proposed.accessPolicyType,
        wasPresent: true,
        requiresHumanReview: !isInternalOwner && proposed.accessPolicyType === "legacy_review",
        entitledAppCount: appIds.length,
      });
    } else {
      // No inferred trial start or historical payments; the customer remains restricted.
      nextPlans.push({
        organizationId: org.id,
        planName: isInternalOwner ? "V79 Internal" : "Legacy — review required",
        status: isInternalOwner ? "active" : "paused",
        billingCycle: "custom",
        appIds,
        accessPolicyType: isInternalOwner ? "internal" : "legacy_review",
        createdAt: checkedAt,
        updatedAt: checkedAt,
      });
      review.push({
        organizationId: org.id,
        classification: isInternalOwner ? "internal" : "legacy_review",
        wasPresent: false,
        requiresHumanReview: !isInternalOwner,
        entitledAppCount: appIds.length,
      });
    }
  }
  const planned = { ...structuredClone(store), organizationPlans: nextPlans };
  return {
    planned,
    review,
    summary: {
      organisations: organisations.length,
      existingPlans: existingPlans.length,
      proposedPlans: nextPlans.length,
      internal: review.filter(x => x.classification === "internal").length,
      customerReviewRequired: review.filter(x => x.requiresHumanReview).length,
      allowCustomerAccessWithoutVerifiedPolicy: review.some(x =>
        x.classification === "legacy_review" &&
        accessDecision(planned.organizationPlans.find(y => y.organizationId === x.organizationId), now).allowed
      ),
    }
  };
}


// Staging-only pure transformer. This DOES NOT commit any state to PostgreSQL.
// Existing non-owner customers require an explicitly documented founder decision.
// A "paid" decision is deliberately unsupported until independently verified
// billing orders are integrated under V79-02.
export function approveReviewedLegacyTrial(store, {
  organizationId, ownerOrganizationId, approvedByUserId, verifiedOwnerUserId,
  decision, approvedAt, reason,
}) {
  const invalid = message => { throw new Error(message); };
  if (!organizationId || organizationId === ownerOrganizationId ||
      !approvedByUserId || approvedByUserId !== verifiedOwnerUserId ||
      !reason || reason.trim().length < 12) {
    invalid("A distinct customer and verified founder approval with a reason are required.");
  }
  const found = (store.organizations || []).find(x => x.id === organizationId);
  if (!found || found.status !== "active") invalid("An active existing customer organisation is required.");
  const plans = store.organizationPlans || [];
  if (plans.some(x => x.organizationId === organizationId && x.accessPolicyType && x.accessPolicyType !== "legacy_review")) {
    invalid("An existing trial or paid entitlement cannot be replaced.");
  }
  const date = new Date(approvedAt);
  if (!Number.isFinite(date.getTime())) invalid("An exact approved-at timestamp is required.");
  if (decision !== "trial" && decision !== "restrict") {
    invalid("Only approved trial or restricted review states are supported. Verified paid migration requires V79-02.");
  }
  const preview = planLegacySubscriptions(store, ownerOrganizationId, date);
  const index = preview.planned.organizationPlans.findIndex(x => x.organizationId === organizationId);
  const original = preview.planned.organizationPlans[index];
  if (!original || original.accessPolicyType !== "legacy_review") {
    invalid("Customer must be explicitly classified as legacy review before approval.");
  }
  const reviewFields = {
    legacyReviewDecision: decision,
    legacyReviewApprovedBy: approvedByUserId,
    legacyReviewApprovedAt: date.toISOString(),
    legacyReviewReason: reason.trim(),
  };
  const result = decision === "trial"
    ? { ...original, planName: "V79 Beta Trial", ...beginTrial(date), ...reviewFields, updatedAt: date.toISOString() }
    : { ...original, planName: "Legacy — access restricted", status: "paused",
        accessPolicyType: "legacy_review", ...reviewFields, updatedAt: date.toISOString() };
  preview.planned.organizationPlans[index] = result;
  return { planned: preview.planned, approvedPlan: result, requiresDatabaseMigrationApproval: true };
}
