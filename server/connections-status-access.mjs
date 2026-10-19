/**
 * Permission gate for GET /api/connections/status only.
 * The frontend already exposes My Apps to the verified platform operator.
 * Never apply this exception to general permissions, tenant/app assignments,
 * session/MFA controls, or launch entitlement decisions.
 */
export function canReadConnectionsStatus({ assigned, verifiedPlatformOwner } = {}) {
  return assigned === true || verifiedPlatformOwner === true;
}
