import test from "node:test";
import assert from "node:assert/strict";
import {
  activatePosTenantMapping,
  posProvisioningTarget,
  posTenantLaunchReady,
  posTenantMapping,
} from "../server/pos-provisioning.mjs";

function store() {
  return {
    organizations: [
      { id: "legacy", name: "V79", slug: "v79", status: "active" },
      { id: "org-a-1234", name: "Business A", slug: "business-a", status: "active" },
      { id: "org-b-1234", name: "Business B", slug: "business-b", status: "active" },
    ],
    users: [
      { id: "u-a", username: "a@example.test" },
      { id: "u-b", username: "b@example.test" },
    ],
    memberships: [
      { organizationId: "org-a-1234", userId: "u-a", role: "owner", status: "active" },
      { organizationId: "org-b-1234", userId: "u-b", role: "owner", status: "active" },
    ],
    appEntitlements: [
      { organizationId: "org-a-1234", appId: "app-v79pos", enabled: true },
      { organizationId: "org-b-1234", appId: "app-v79pos", enabled: true },
    ],
    appTenantMappings: [
      { organizationId: "org-a-1234", appId: "app-v79pos", status: "pending", createdAt: "x", updatedAt: "x" },
      { organizationId: "org-b-1234", appId: "app-v79pos", status: "pending", createdAt: "x", updatedAt: "x" },
    ],
    auditEvents: [],
  };
}

test("POS provisioning target resolves only the selected organization owner", () => {
  const current = store();
  const a = posProvisioningTarget(current, "org-a-1234");
  const b = posProvisioningTarget(current, "org-b-1234");

  assert.equal(a.organization.name, "Business A");
  assert.equal(a.owner.id, "u-a");
  assert.equal(b.organization.name, "Business B");
  assert.equal(b.owner.id, "u-b");
  assert.notEqual(a.owner.id, b.owner.id);
});

test("activating POS mapping is tenant-exact and does not change another workspace", () => {
  const current = store();
  const next = activatePosTenantMapping(current, "org-a-1234", "org-a-1234", "platform-owner", "2026-09-30T15:00:00Z");

  assert.equal(posTenantMapping(next, "org-a-1234").status, "active");
  assert.equal(posTenantMapping(next, "org-a-1234").externalTenantId, "org-a-1234");
  assert.equal(posTenantMapping(next, "org-b-1234").status, "pending");
  assert.equal(posTenantLaunchReady(next, "org-a-1234", "legacy"), true);
  assert.equal(posTenantLaunchReady(next, "org-b-1234", "legacy"), false);
  assert.equal(current.appTenantMappings[0].status, "pending");
  assert.equal(next.auditEvents.at(-1).organizationId, "org-a-1234");
});

test("POS mapping rejects a product tenant ID from another workspace", () => {
  const current = store();
  assert.throws(
    () => activatePosTenantMapping(current, "org-a-1234", "org-b-1234", "platform-owner"),
    /identity mismatch/
  );
  assert.equal(posTenantLaunchReady(current, "legacy", "legacy"), true);
});
