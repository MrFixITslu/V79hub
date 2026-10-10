import test from "node:test";
import assert from "node:assert/strict";
import {
  activateTiquetTenantMapping,
  tiquetProvisioningTarget,
  tiquetTenantLaunchReady,
  tiquetTenantMapping,
} from "../server/tiquet-provisioning.mjs";

function makeStore() {
  return {
    organizations: [
      { id: "legacy", name: "V79", slug: "v79", status: "active" },
      { id: "org-a-1234", name: "Business A", slug: "business-a", status: "active" },
      { id: "org-b-1234", name: "Business B", slug: "business-b", status: "active" },
    ],
    users: [
      { id: "u-a", username: "shared@example.test", email: "shared@example.test" },
      { id: "u-b", username: "shared@example.test", email: "shared@example.test" },
    ],
    memberships: [
      { organizationId: "org-a-1234", userId: "u-a", role: "owner", status: "active" },
      { organizationId: "org-b-1234", userId: "u-b", role: "owner", status: "active" },
    ],
    appEntitlements: [
      { organizationId: "org-a-1234", appId: "app-tiquet", enabled: true },
      { organizationId: "org-b-1234", appId: "app-tiquet", enabled: true },
    ],
    appTenantMappings: [
      { organizationId: "org-a-1234", appId: "app-tiquet", status: "pending", createdAt: "x", updatedAt: "x" },
      { organizationId: "org-b-1234", appId: "app-tiquet", status: "pending", createdAt: "x", updatedAt: "x" },
    ],
    auditEvents: [],
  };
}

test("Tiquet provisioning target resolves only the selected workspace owner", () => {
  const store = makeStore();
  assert.equal(tiquetProvisioningTarget(store, "org-a-1234").owner.id, "u-a");
  assert.equal(tiquetProvisioningTarget(store, "org-b-1234").owner.id, "u-b");
});

test("Tiquet activation stores the returned account and owner without affecting another workspace", () => {
  const current = makeStore();
  const next = activateTiquetTenantMapping(
    current,
    "org-a-1234",
    "org-a-1234",
    "tiquet-account-a",
    "tiquet-user-a",
    "operator",
    "2026-09-30T17:00:00Z",
  );
  const a = tiquetTenantMapping(next, "org-a-1234");
  const b = tiquetTenantMapping(next, "org-b-1234");
  assert.equal(a.status, "active");
  assert.equal(a.externalTenantId, "tiquet-account-a");
  assert.equal(a.externalOwnerId, "tiquet-user-a");
  assert.equal(b.status, "pending");
  assert.equal(tiquetTenantLaunchReady(next, "org-a-1234", "legacy"), true);
  assert.equal(tiquetTenantLaunchReady(next, "org-b-1234", "legacy"), false);
  assert.equal(current.appTenantMappings[0].status, "pending");
});

test("Tiquet activation rejects wrong Hub organization or missing external identities", () => {
  const store = makeStore();
  assert.throws(() => activateTiquetTenantMapping(store, "org-a-1234", "org-b-1234", "a", "u", "operator"), /identity mismatch/);
  assert.throws(() => activateTiquetTenantMapping(store, "org-a-1234", "org-a-1234", "", "u", "operator"), /account identity/);
  assert.throws(() => activateTiquetTenantMapping(store, "org-a-1234", "org-a-1234", "a", "", "operator"), /owner identity/);
  assert.equal(tiquetTenantLaunchReady(store, "legacy", "legacy"), true);
});
