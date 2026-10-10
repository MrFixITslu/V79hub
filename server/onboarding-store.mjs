export function invitationStatus(invitation, now = Date.now()) {
  if (invitation.status !== "pending") return invitation.status;
  return Date.parse(invitation.expiresAt) <= now ? "expired" : "pending";
}

export function acceptInvitationState(store, invitationId, options) {
  const next = structuredClone(store);
  const invitation = next.ownerInvitations.find(item => item.id === invitationId);
  if (!invitation || invitation.status !== "pending") {
    throw new Error("Invitation is not pending.");
  }
  if (Date.parse(invitation.expiresAt) <= Date.parse(options.now)) {
    throw new Error("Invitation has expired.");
  }
  if (next.organizations.some(org => org.id === invitation.organizationId)) {
    throw new Error("Organization already exists.");
  }

  const now = options.now;
  let user = options.existingUserId
    ? next.users.find(item => item.id === options.existingUserId)
    : null;

  if (!user) {
    user = {
      ...options.newUser,
      createdAt: now,
    };
    next.users.push(user);
  }

  if (next.memberships.some(member =>
    member.organizationId === invitation.organizationId && member.userId === user.id
  )) {
    throw new Error("Membership already exists.");
  }

  next.organizations.push({
    id: invitation.organizationId,
    name: invitation.organizationName,
    slug: invitation.organizationSlug,
    status: "active",
    createdAt: now,
  });

  next.memberships.push({
    organizationId: invitation.organizationId,
    userId: user.id,
    role: "owner",
    permissions: [...options.ownerPermissions],
    status: "active",
    createdAt: now,
  });

  for (const appId of invitation.appIds) {
    next.appEntitlements.push({
      organizationId: invitation.organizationId,
      appId,
      enabled: true,
      createdAt: now,
    });
    if (options.tenantMappedAppIds.includes(appId)) {
      next.appTenantMappings.push({
        organizationId: invitation.organizationId,
        appId,
        status: "pending",
        createdAt: now,
        updatedAt: now,
      });
    }
  }

  invitation.status = "accepted";
  invitation.acceptedAt = now;
  invitation.acceptedUserId = user.id;

  next.auditEvents.push({
    id: options.auditId,
    organizationId: invitation.organizationId,
    actorUserId: user.id,
    type: "owner_invitation_accepted",
    createdAt: now,
    details: {
      invitationId: invitation.id,
      email: invitation.email,
      appIds: [...invitation.appIds],
      existingAccount: Boolean(options.existingUserId),
    },
  });

  if (next.auditEvents.length > 5000) {
    next.auditEvents = next.auditEvents.slice(-5000);
  }

  return {
    nextStore: next,
    userId: user.id,
    organizationId: invitation.organizationId,
    appIds: [...invitation.appIds],
  };
}
