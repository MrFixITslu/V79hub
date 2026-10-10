import test from "node:test";
import assert from "node:assert/strict";
import { acceptTeamInvitationState, teamInvitationStatus } from "../server/team-invitation-store.mjs";

function baseStore(role = "staff") {
  return {
    organizations: [{ id: "org-a", name: "Business A", slug: "business-a", status: "active" }],
    users: [],
    memberships: [],
    teamInvitations: [{
      id: "invite-1",
      organizationId: "org-a",
      email: "member@example.test",
      role,
      permissions: role === "manager" ? ["overview", "connections", "team"] : ["overview", "connections"],
      appIds: ["app-v79pos"],
      tokenHash: "hash",
      status: "pending",
      createdAt: "2026-09-30T10:00:00Z",
      expiresAt: "2026-10-01T10:00:00Z",
      createdByUserId: "owner-a",
    }],
    auditEvents: [],
  };
}

test("team invitation status fails closed on expiry", () => {
  const invitation = baseStore().teamInvitations[0];
  assert.equal(teamInvitationStatus(invitation, Date.parse("2026-09-30T12:00:00Z")), "pending");
  assert.equal(teamInvitationStatus(invitation, Date.parse("2026-10-01T10:00:00Z")), "expired");
  invitation.status = "revoked";
  assert.equal(teamInvitationStatus(invitation, Date.parse("2026-09-30T12:00:00Z")), "revoked");
});

test("team invitation acceptance atomically creates only the selected workspace membership", () => {
  const current = baseStore("staff");
  const result = acceptTeamInvitationState(current, "invite-1", {
    newUser: {
      id: "user-1",
      username: "member@example.test",
      email: "member@example.test",
      password: "hash",
      fullName: "Team Member",
      role: "staff",
      permissions: ["overview", "connections"],
    },
    auditId: "audit-1",
    now: "2026-09-30T12:00:00Z",
  });

  assert.equal(current.users.length, 0, "source store must not be mutated");
  assert.equal(current.memberships.length, 0, "source memberships must not be mutated");
  assert.equal(current.teamInvitations[0].status, "pending");

  assert.equal(result.nextStore.users.length, 1);
  assert.deepEqual(result.nextStore.memberships[0], {
    organizationId: "org-a",
    userId: "user-1",
    role: "staff",
    permissions: ["overview", "connections"],
    appIds: ["app-v79pos"],
    status: "active",
    createdAt: "2026-09-30T12:00:00Z",
  });
  assert.equal(result.nextStore.teamInvitations[0].status, "accepted");
  assert.equal(result.nextStore.auditEvents[0].type, "team_invitation_accepted");
});

test("existing Hub identity can join another workspace without duplicating the account", () => {
  const current = baseStore("manager");
  current.users.push({
    id: "shared-user",
    username: "member@example.test",
    email: "member@example.test",
    password: "hash",
    fullName: "Shared Member",
    role: "staff",
    permissions: ["overview"],
  });
  current.memberships.push({
    organizationId: "org-other",
    userId: "shared-user",
    role: "staff",
    permissions: ["overview"],
    status: "active",
    createdAt: "2026-09-29T12:00:00Z",
  });

  const result = acceptTeamInvitationState(current, "invite-1", {
    existingUserId: "shared-user",
    auditId: "audit-2",
    now: "2026-09-30T12:00:00Z",
  });

  assert.equal(result.nextStore.users.length, 1);
  assert.equal(result.nextStore.memberships.length, 2);
  const joined = result.nextStore.memberships.find(member => member.organizationId === "org-a");
  assert.equal(joined.role, "manager");
  assert.deepEqual(joined.permissions, ["overview", "connections", "team"]);
  assert.deepEqual(joined.appIds, ["app-v79pos"]);
});

test("team invitation acceptance rejects expiry, privileged roles and identity mismatch", () => {
  const expired = baseStore();
  assert.throws(() => acceptTeamInvitationState(expired, "invite-1", {
    newUser: { id: "u1", email: "member@example.test" },
    auditId: "a1",
    now: "2026-10-02T00:00:00Z",
  }), /expired/);

  const privileged = baseStore("staff");
  privileged.teamInvitations[0].role = "admin";
  assert.throws(() => acceptTeamInvitationState(privileged, "invite-1", {
    newUser: { id: "u1", email: "member@example.test" },
    auditId: "a2",
    now: "2026-09-30T12:00:00Z",
  }), /role is not allowed/);

  const mismatch = baseStore();
  assert.throws(() => acceptTeamInvitationState(mismatch, "invite-1", {
    newUser: { id: "u1", email: "someone-else@example.test" },
    auditId: "a3",
    now: "2026-09-30T12:00:00Z",
  }), /does not match invitation/);
});
