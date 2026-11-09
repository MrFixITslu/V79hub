// Authoritative organisation display-name rules. No product name or slug changes.
export class OrganizationNameError extends Error {
  constructor(message, status = 400) {
    super(message);
    this.name = "OrganizationNameError";
    this.status = status;
  }
}

export function prepareOrganizationRename(store, input, scopedUserId) {
  const organizationId = typeof input?.organizationId === "string" ? input.organizationId.trim() : "";
  const actorId = typeof input?.scopedUserId === "string" ? input.scopedUserId.trim() : "";
  const rawName = typeof input?.name === "string" ? input.name : "";
  const name = rawName.trim().replace(/\s+/g, " ");
  const expectedName = typeof input?.expectedName === "string" ? input.expectedName.trim() : "";
  if (!organizationId || organizationId.length > 180 || !actorId || actorId.length > 180 ||
      !expectedName || expectedName.length > 120 ||
      name.length < 2 || name.length > 120 || /[\u0000-\u001f\u007f]/.test(rawName)) {
    throw new OrganizationNameError("Invalid organisation name request");
  }
  const organization = store.organizations.find(row => row.id === organizationId && row.status === "active");
  if (!organization) throw new OrganizationNameError("Organisation is unavailable", 404);
  const owner = store.memberships.find(row =>
    row.organizationId === organizationId && row.status === "active" &&
    row.role === "owner" && scopedUserId(row.userId, organizationId) === actorId
  );
  if (!owner) throw new OrganizationNameError("Only the organisation owner may change its name", 403);
  const hasMarketing = store.appEntitlements.some(row =>
    row.organizationId === organizationId && row.appId === "app-marketing" && row.enabled === true
  );
  if (!hasMarketing) throw new OrganizationNameError("Marketing is not enabled for this organisation", 403);
  if (organization.name === name) {
    return { changed: false, organizationId, actorUserId: owner.userId, name, previousName: organization.name };
  }
  if (organization.name !== expectedName) {
    throw new OrganizationNameError("The business name has changed in Hub. Refresh Marketing before saving again", 409);
  }
  return { changed: true, organizationId, actorUserId: owner.userId, name, previousName: organization.name };
}
