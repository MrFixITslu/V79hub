import test from "node:test";
import assert from "node:assert/strict";
import { prepareOrganizationRename, OrganizationNameError } from "../server/organization-name-sync.mjs";

const base = () => ({
  organizations: [
    { id: "org-one", name: "Old Business", status: "active" },
    { id: "org-two", name: "Other Tenant", status: "active" },
  ],
  memberships: [
    { organizationId: "org-one", userId: "owner-one", role: "owner", status: "active" },
    { organizationId: "org-one", userId: "staff-one", role: "staff", status: "active" },
    { organizationId: "org-two", userId: "owner-two", role: "owner", status: "active" },
  ],
  appEntitlements: [
    { organizationId: "org-one", appId: "app-marketing", enabled: true },
  ],
});
const scoped = (userId, orgId) => `hub:${orgId}:${userId}`;
const proposed = { organizationId:"org-one", scopedUserId:scoped("owner-one","org-one"), name:"New Business", expectedName:"Old Business" };

test("owner of the linked organisation may rename only that organisation", () => {
  const plan = prepareOrganizationRename(base(), proposed, scoped);
  assert.equal(plan.changed, true);
  assert.equal(plan.actorUserId, "owner-one");
  assert.equal(plan.name, "New Business");
});
test("does not silently overwrite concurrently changed names", () => {
  assert.throws(() => prepareOrganizationRename(base(), {...proposed,expectedName:"Already Stale"}, scoped), error =>
    error instanceof OrganizationNameError && error.status === 409);
});
test("staff and cross-tenant owners cannot rename", () => {
  for (const actor of [scoped("staff-one","org-one"), scoped("owner-two","org-two")]) {
    assert.throws(() => prepareOrganizationRename(base(), {...proposed,scopedUserId:actor}, scoped), error => error.status === 403);
  }
});
test("rejects missing Marketing entitlement and invalid business names", () => {
  const missing = base();
  missing.appEntitlements = [];
  assert.throws(() => prepareOrganizationRename(missing,proposed,scoped), error => error.status === 403);
  for (const name of ["", "X", "A".repeat(121), "Name\nInjected"]) {
    assert.throws(() => prepareOrganizationRename(base(), {...proposed,name},scoped));
  }
});
test("idempotent repeated name write does not require old expected name", () => {
  const updated = base();
  updated.organizations[0].name = "New Business";
  assert.equal(prepareOrganizationRename(updated,proposed,scoped).changed, false);
});
