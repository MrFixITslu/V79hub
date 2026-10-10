// The first migration only describes the existing V79 workspace. It does not
// enroll new customers or change access to product data.
export function migrateLegacyOrganization(store, organizationId, ownerUserId) {
  if (!organizationId || !ownerUserId) throw new Error("Legacy organization identity is required.");
  if (!store.users.some(user => user.id === ownerUserId)) throw new Error("Legacy owner is missing from Hub users.");
  const organizations = store.organizations || [];
  const memberships = store.memberships || [];
  if (organizations.length || memberships.length) {
    if (!organizations.some(org => org.id === organizationId) ||
        !memberships.some(member => member.organizationId === organizationId && member.userId === ownerUserId && member.role === "owner")) {
      throw new Error("Existing organization data needs manual review before migration.");
    }
    return { changed: false, organizations, memberships };
  }

  const now = new Date().toISOString();
  return {
    changed: true,
    organizations: [{
      id: organizationId,
      name: store.workspace.companyName,
      slug: `v79-${organizationId.slice(0, 12)}`,
      status: "active",
      createdAt: now,
    }],
    memberships: store.users.map(user => ({
      organizationId,
      userId: user.id,
      role: user.id === ownerUserId ? "owner" : user.role,
      permissions: Array.isArray(user.permissions) ? [...user.permissions] : [],
      status: "active",
      createdAt: now,
    })),
  };
}