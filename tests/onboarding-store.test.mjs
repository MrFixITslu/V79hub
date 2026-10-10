import test from "node:test";
import assert from "node:assert/strict";
import { invitationStatus } from "../server/onboarding-store.mjs";

test("owner invitation status fails closed on expiry and preserves terminal states", () => {
  const now = Date.parse("2026-09-30T12:00:00Z");
  assert.equal(invitationStatus({ status: "pending", expiresAt: "2026-09-30T12:01:00Z" }, now), "pending");
  assert.equal(invitationStatus({ status: "pending", expiresAt: "2026-09-30T11:59:59Z" }, now), "expired");
  assert.equal(invitationStatus({ status: "accepted", expiresAt: "2026-09-30T11:00:00Z" }, now), "accepted");
  assert.equal(invitationStatus({ status: "revoked", expiresAt: "2026-09-30T13:00:00Z" }, now), "revoked");
});

import { acceptInvitationState } from "../server/onboarding-store.mjs";

test("atomic invitation acceptance rejects an expired pending invite", () => {
  const store = {
    ownerInvitations: [{
      id: "invite-expired",
      organizationId: "org-expired",
      organizationName: "Expired Co",
      organizationSlug: "expired-co",
      email: "owner@example.test",
      appIds: [],
      status: "pending",
      createdAt: "2026-09-30T10:00:00Z",
      expiresAt: "2026-09-30T11:00:00Z",
    }],
    organizations: [],
    users: [],
    memberships: [],
    appEntitlements: [],
    appTenantMappings: [],
    auditEvents: [],
  };

  assert.throws(() => acceptInvitationState(store, "invite-expired", {
    newUser: { id: "u1", username: "owner@example.test", email: "owner@example.test", password: "hash", fullName: "Owner", role: "admin", permissions: [] },
    ownerPermissions: [],
    tenantMappedAppIds: [],
    auditId: "audit-1",
    now: "2026-09-30T12:00:00Z",
  }), /expired/);

  assert.equal(store.organizations.length, 0);
  assert.equal(store.memberships.length, 0);
});
