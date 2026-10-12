/**
 * Minimum-privilege compatibility shim for the V79 platform owner's legacy
 * billing membership. This is a reconstructed contract, NOT a verified copy
 * of the live v79-hub implementation (live git blob af7db645565e...).
 *
 * The server.ts caller derives assigned from Array.includes() and
 * verifiedPlatformOwner from a strict Boolean identity/membership check
 * against the V79 platform user, email and organization. This helper grants
 * an owner-scoped BILLING ROUTE permission; it does not independently check
 * MFA or confirm a payment, settlement, subscription or provider callback.
 * Those actions require their own route-level financial safeguards.
 *
 * Strict boolean comparisons deliberately reject truthy malformed inputs
 * (for example "true" strings). This is a safety improvement even if the
 * live helper accepts or returns non-boolean values for synthetic inputs.
 */
export function platformOwnerBillingAllowed({
  permission, assigned, verifiedPlatformOwner
} = {}) {
  if (assigned === true) return true;
  return permission === "billing" && verifiedPlatformOwner === true;
}
