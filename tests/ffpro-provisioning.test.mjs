import test from "node:test";
import assert from "node:assert/strict";
import {
  activateFfproTenantMapping,
  ffproProvisioningTarget,
  ffproTenantLaunchReady,
  ffproTenantMapping,
} from "../server/ffpro-provisioning.mjs";

function store() {
  return {
    organizations: [
      { id: "legacy", name: "V79", slug: "v79", status: "active" },
      { id: "org-a-1234", name: "Business A", slug: "business-a", status: "active" },
      { id: "org-b-1234", name: "Business B", slug: "business-b", status: "active" },
    ],
    users: [
      { id: "u-a", username: "a@example.test", email: "a@example.test" },
      { id: "u-b", username: "b@example.test", email: "b@example.test" },
    ],
    memberships: [
      { organizationId: "org-a-1234", userId: "u-a", role: "owner", status: "active" },
      { organizationId: "org-b-1234", userId: "u-b", role: "owner", status: "active" },
    ],
    appEntitlements: [
      { organizationId: "org-a-1234", appId: "app-ffpro", enabled: true },
      { organizationId: "org-b-1234", appId: "app-ffpro", enabled: true },
    ],
    appTenantMappings: [
      { organizationId: "org-a-1234", appId: "app-ffpro", status: "pending", createdAt: "x", updatedAt: "x" },
      { organizationId: "org-b-1234", appId: "app-ffpro", status: "pending", createdAt: "x", updatedAt: "x" },
    ],
    auditEvents: [],
  };
}

test("FFPRO provisioning target resolves only the selected workspace owner", () => {
  const current = store();
  const a = ffproProvisioningTarget(current, "org-a-1234");
  const b = ffproProvisioningTarget(current, "org-b-1234");
  assert.equal(a.owner.id, "u-a");
  assert.equal(a.ownerEmail, "a@example.test");
  assert.equal(b.owner.id, "u-b");
  assert.equal(b.ownerEmail, "b@example.test");
});

test("activating FFPRO mapping is tenant-exact and preserves other workspaces", () => {
  const current = store();
  const next = activateFfproTenantMapping(
    current,
    "org-a-1234",
    "org-a-1234",
    "finance-a",
    "platform-owner",
    "2026-09-30T16:00:00Z"
  );
  assert.equal(ffproTenantMapping(next, "org-a-1234").status, "active");
  assert.equal(ffproTenantMapping(next, "org-a-1234").externalTenantId, "org-a-1234");
  assert.equal(ffproTenantMapping(next, "org-a-1234").externalOwnerId, "finance-a");
  assert.equal(ffproTenantMapping(next, "org-b-1234").status, "pending");
  assert.equal(ffproTenantLaunchReady(next, "org-a-1234", "legacy"), true);
  assert.equal(ffproTenantLaunchReady(next, "org-b-1234", "legacy"), false);
  assert.equal(current.appTenantMappings[0].status, "pending");
});

test("FFPRO mapping rejects another workspace tenant or missing finance owner", () => {
  const current = store();
  assert.throws(
    () => activateFfproTenantMapping(current, "org-a-1234", "org-b-1234", "finance-a", "operator"),
    /identity mismatch/
  );
  assert.throws(
    () => activateFfproTenantMapping(current, "org-a-1234", "org-a-1234", "", "operator"),
    /finance owner identity/
  );
  assert.equal(ffproTenantLaunchReady(current, "legacy", "legacy"), true);
});
