export function teamInvitationStatus(invitation, now = Date.now()) {
  if (invitation.status !== "pending") return invitation.status;
  return Date.parse(invitation.expiresAt) <= now ? "expired" : "pending";
}

export function acceptTeamInvitationState(store, invitationId, options) {
  const next = structuredClone(store);
  const invitation = (next.teamInvitations || []).find(item => item.id === invitationId);
  if (!invitation || invitation.status !== "pending") {
    throw new Error("Team invitation is not pending.");
  }
  if (Date.parse(invitation.expiresAt) <= Date.parse(options.now)) {
    throw new Error("Team invitation has expired.");
  }

  const organization = (next.organizations || []).find(org =>
    org.id === invitation.organizationId && org.status === "active"
  );
  if (!organization) throw new Error("Organization is not active.");
  if (!["manager", "staff", "viewer"].includes(invitation.role)) {
    throw new Error("Team invitation role is not allowed.");
  }

  let user = options.existingUserId
    ? next.users.find(item => item.id === options.existingUserId)
    : null;

  if (!user) {
    if (!options.newUser?.id || !options.newUser?.email) {
      throw new Error("New user identity is required.");
    }
    if (String(options.newUser.email).trim().toLowerCase() !== invitation.email) {
      throw new Error("New user email does not match invitation.");
    }
    user = {
      ...options.newUser,
      createdAt: options.now,
    };
    next.users.push(user);
  } else {
    const identityEmail = String(user.email || user.username || "").trim().toLowerCase();
    if (identityEmail !== invitation.email) {
      throw new Error("Existing user email does not match invitation.");
    }
  }

  const existingMembership = (next.memberships || []).find(member =>
    member.organizationId === invitation.organizationId && member.userId === user.id
  );
  if (existingMembership?.status === "active") {
    throw new Error("Membership already exists.");
  }

  if (existingMembership) {
    existingMembership.status = "active";
    existingMembership.role = invitation.role;
    existingMembership.permissions = [...invitation.permissions];
    existingMembership.appIds = [...(invitation.appIds || [])];
    existingMembership.createdAt = options.now;
  } else {
    next.memberships.push({
      organizationId: invitation.organizationId,
      userId: user.id,
      role: invitation.role,
      permissions: [...invitation.permissions],
      appIds: [...(invitation.appIds || [])],
      status: "active",
      createdAt: options.now,
    });
  }

  invitation.status = "accepted";
  invitation.acceptedAt = options.now;
  invitation.acceptedUserId = user.id;

  next.auditEvents.push({
    id: options.auditId,
    organizationId: invitation.organizationId,
    actorUserId: user.id,
    type: "team_invitation_accepted",
    createdAt: options.now,
    details: {
      invitationId: invitation.id,
      email: invitation.email,
      role: invitation.role,
      permissions: [...invitation.permissions],
      appIds: [...(invitation.appIds || [])],
      existingAccount: Boolean(options.existingUserId),
    },
  });

  if (next.auditEvents.length > 5000) next.auditEvents = next.auditEvents.slice(-5000);

  return {
    nextStore: next,
    userId: user.id,
    organizationId: invitation.organizationId,
    role: invitation.role,
    permissions: [...invitation.permissions],
    appIds: [...(invitation.appIds || [])],
  };
}
