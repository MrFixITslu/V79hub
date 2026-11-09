/**
 * Canonical V79 Hub organisation-name guard.
 * Pure function: no I/O, no trust in Marketing's browser-supplied identity.
 * The HTTP route must independently verify the platform HMAC before this check.
 */
export function authorizeOrganizationRename({body,organizations,memberships,mapping,scopedHubUserId}) {
  const organizationId = typeof body?.organizationId === "string" ? body.organizationId.trim() : "";
  const businessId = typeof body?.businessId === "string" ? body.businessId.trim() : "";
  const hubUserId = typeof body?.hubUserId === "string" ? body.hubUserId.trim() : "";
  const name = typeof body?.name === "string" ? body.name.trim().normalize("NFC") : "";

  if (!name || name.length > 180 ||
      /[\u0000-\u001f\u007f\u202a-\u202e\u2066-\u2069]/u.test(name) ||
      organizationId.length < 8 || organizationId.length > 180 ||
      businessId.length < 8 || businessId.length > 180 ||
      hubUserId.length < 8 || hubUserId.length > 180) {
    return {ok:false,status:400,error:"Invalid organization name or tenant identity"};
  }
  const organization = organizations.find(org => org.id === organizationId && org.status === "active");
  const owner = memberships.find(m => m.organizationId === organizationId &&
      m.role === "owner" && m.status === "active" &&
      scopedHubUserId(m.userId,organizationId) === hubUserId);
  if (!organization || !owner || mapping?.status !== "active" ||
      mapping.externalTenantId !== businessId) {
    return {ok:false,status:403,error:"Active owner and tenant mapping required"};
  }
  return {ok:true,organizationId,businessId,hubUserId,name,organization,owner};
}
