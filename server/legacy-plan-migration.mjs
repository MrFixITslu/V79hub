import { classifyLegacyPlan, accessDecision } from "./subscription-access.mjs";

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
