import { activeMembership, organizationCanAccessApp } from "./organization-access.mjs";
import { accessDecision } from "./subscription-access.mjs";

export const ENTITLEMENT_RECHECK_SECONDS = 30;
export const PRODUCTS = Object.freeze({
  pos: "app-v79pos",
  ffpro: "app-ffpro",
  tiquet: "app-tiquet",
  marketing: "app-marketing",
});

// Call only behind service HMAC authentication. No user data or reusable tokens returned.
export function validateProductEntitlement(store, {
  product, organizationId, scopedUserId, ownerOrganizationId,
  resolveScopedUserId, memberCanAccessApp, roleEligible, tenantReady,
  now = Date.now(),
}) {
  const denied = { allowed: false, validForSeconds: 0, reason: "revoked" };
  if (!PRODUCTS[product] || !organizationId || !scopedUserId ||
      typeof resolveScopedUserId !== "function" ||
      typeof memberCanAccessApp !== "function" ||
      typeof roleEligible !== "function" ||
      typeof tenantReady !== "function") return denied;
  if (!organizationCanAccessApp(store, organizationId, PRODUCTS[product], ownerOrganizationId, now)) return denied;
  const memberships = Array.isArray(store?.memberships) ? store.memberships : [];
  const matches = memberships.filter(row =>
    row.organizationId === organizationId &&
    row.status === "active" &&
    resolveScopedUserId(row.userId, organizationId) === scopedUserId
  );
  if (matches.length !== 1) return denied;
  const member = activeMembership(store, matches[0].userId, organizationId);
  if (!member || !memberCanAccessApp(member, PRODUCTS[product]) ||
      !roleEligible(product, member.role) ||
      !tenantReady(product, organizationId, ownerOrganizationId)) return denied;
  // Preserve owner-only restriction on the Vision79 internal tenant.
  if (organizationId === ownerOrganizationId && member.role !== "owner") return denied;
  const isInternal = organizationId === ownerOrganizationId;
  const plan = (store.organizationPlans || []).find(row => row.organizationId === organizationId);
  const decision = accessDecision(plan, now, isInternal);
  if (!decision.allowed) return denied;
  const secondsToExpiry = decision.expiresAt
    ? Math.floor((Date.parse(decision.expiresAt) - Number(now)) / 1000)
    : ENTITLEMENT_RECHECK_SECONDS;
  if (secondsToExpiry <= 0) return denied;
  return {
    allowed: true,
    validForSeconds: Math.min(ENTITLEMENT_RECHECK_SECONDS, secondsToExpiry),
    reason: "valid",
  };
}
