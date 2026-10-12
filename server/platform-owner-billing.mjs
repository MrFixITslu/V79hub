/**
 * Minimum-privilege compatibility shim for the V79 platform owner's legacy
 * billing membership. This is a reconstructed contract, NOT a verified copy
 * of the live v79-hub implementation (live git blob af7db645565e...).
 *
 * A caller must independently attest the exact platform-owner user AND the
 * exact platform-owner organization. Membership, email, MFA and owner scope
 * are checked by server.ts before passing verifiedPlatformOwner=true.
 * Never override a general role/tenant permission or authorize a payment.
 */
export function platformOwnerBillingAllowed({
  permission, assigned, verifiedPlatformOwner
} = {}) {
  if (assigned === true) return true;
  return permission === "billing" && verifiedPlatformOwner === true;
}
