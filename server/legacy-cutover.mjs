import { approveReviewedLegacyTrial } from "./legacy-plan-migration.mjs";
import { accessDecision } from "./subscription-access.mjs";

const APPROVED_ON = "2026-10-08";
export const APPROVED_CUSTOMER_POLICY = Object.freeze({
  decision: "trial",
  approvedOn: APPROVED_ON,
  trialDays: 14,
  entitlementCount: 5,
  maximumCustomerOrganisations: 1,
});

// A side-effect-free cutover planner. A release operator will need a separately
// approved, revision-checked database writer to apply it.
export function prepareApprovedLegacyCutover(store, {
  ownerOrganizationId,
  verifiedOwnerUserId,
  customerOrganizationId,
  activationAt,
}) {
  if (!ownerOrganizationId || !verifiedOwnerUserId || !customerOrganizationId ||
      customerOrganizationId === ownerOrganizationId) {
    throw new Error("Owner and explicitly approved customer identities are required.");
  }
  // Require an unambiguous UTC instant; loose date strings must never
  // silently start, backdate, or extend a customer's sole approved trial.
  if (typeof activationAt !== "string" ||
      !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3})?Z$/.test(activationAt)) {
    throw new Error("An exact UTC ISO activation timestamp is required.");
  }
  const timestamp = new Date(activationAt);
  if (!Number.isFinite(timestamp.getTime()) ||
      timestamp.toISOString() !== (activationAt.includes(".") ? activationAt :
        activationAt.replace("Z",".000Z")) ||
      timestamp < new Date("2026-10-08T00:00:00Z")) {
    throw new Error("A valid post-approval activation timestamp is required.");
  }
  const orgs = Array.isArray(store?.organizations) ? store.organizations : [];
  const owner = orgs.find(org => org.id === ownerOrganizationId && org.status === "active");
  const others = orgs.filter(org => org.id !== ownerOrganizationId);
  if (!owner || others.length !== APPROVED_CUSTOMER_POLICY.maximumCustomerOrganisations ||
      others[0].id !== customerOrganizationId || others[0].status !== "active") {
    throw new Error("Organisation inventory differs from approved one-customer baseline.");
  }
  const memberships = Array.isArray(store?.memberships) ? store.memberships : [];
  if (!memberships.some(row =>
        row.organizationId === ownerOrganizationId && row.userId === verifiedOwnerUserId &&
        row.role === "owner" && row.status === "active")) {
    throw new Error("Verified platform owner is not an active owner member.");
  }
  const customerOwners = memberships.filter(row => row.organizationId === customerOrganizationId &&
    row.status === "active" && row.role === "owner");
  if (customerOwners.length !== 1) {
    throw new Error("Customer does not have exactly one active owner member.");
  }
  const entitlements = Array.isArray(store?.appEntitlements) ? store.appEntitlements : [];
  const customerEntitlements = entitlements.filter(x => x.organizationId === customerOrganizationId && x.enabled);
  if (customerEntitlements.length !== APPROVED_CUSTOMER_POLICY.entitlementCount ||
      new Set(customerEntitlements.map(x => x.appId)).size !== customerEntitlements.length) {
    throw new Error("Customer entitlement inventory differs from approved baseline.");
  }
  const plans = Array.isArray(store?.organizationPlans) ? store.organizationPlans : [];
  const matches = plans.filter(row => row.organizationId === customerOrganizationId);
  if (matches.length > 1) throw new Error("Duplicate customer plan records.");
  const existing = matches[0];
  if (existing?.accessPolicyType === "trial" &&
      existing?.legacyReviewDecision === "trial" &&
      existing?.legacyReviewApprovedOn === APPROVED_ON) {
    const originalStart = Date.parse(existing.trialStartedAt || "");
    const originalEnd = Date.parse(existing.trialEndsAt || "");
    if (!Number.isFinite(originalStart) || !Number.isFinite(originalEnd) ||
        originalEnd - originalStart !== 14 * 86400000) {
      throw new Error("Previously activated trial dates are invalid.");
    }
    return {
      planned: structuredClone(store),
      alreadyApplied: true,
      summary: { approvedOn: APPROVED_ON, trialStart: existing.trialStartedAt,
        trialEnd: existing.trialEndsAt, retainedEntitlements: customerEntitlements.length,
        productionDataTouched: false },
    };
  }
  if (existing && existing.accessPolicyType !== "legacy_review") {
    throw new Error("Customer plan already classified differently; manual reconciliation required.");
  }
  const { planned, approvedPlan } = approveReviewedLegacyTrial(store, {
    organizationId: customerOrganizationId,
    ownerOrganizationId,
    approvedByUserId: verifiedOwnerUserId,
    verifiedOwnerUserId,
    decision: "trial",
    // Timestamp of verified activation; prior policy approval is recorded
    // separately as an explicit date, not backdated as the trial start.
    approvedAt: timestamp.toISOString(),
    reason: "Founder approved one fresh beta trial for the existing customer on 2026-10-08.",
  });
  const updated = planned.organizationPlans.find(row => row.organizationId === customerOrganizationId);
  updated.legacyReviewApprovedOn = APPROVED_ON;
  if (!accessDecision(approvedPlan, timestamp).allowed) {
    throw new Error("Approved trial is not active at the activation boundary.");
  }
  if (planned.appEntitlements.length !== entitlements.length ||
      planned.memberships.length !== memberships.length ||
      planned.organizations.length !== orgs.length) {
    throw new Error("Migration would change existing identity or entitlement inventories.");
  }
  return {
    planned,
    alreadyApplied: false,
    summary: { approvedOn: APPROVED_ON,
      trialStart: updated.trialStartedAt, trialEnd: updated.trialEndsAt,
      retainedEntitlements: customerEntitlements.length, productionDataTouched: false },
  };
}
