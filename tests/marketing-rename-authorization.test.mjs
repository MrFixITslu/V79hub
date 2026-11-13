import test from "node:test";
import assert from "node:assert/strict";
import {
  validateMarketingRenameAuthorization,
} from "../server/marketing-rename-authorization.mjs";

function fixture() {
  return {
    state: {
      organizations: [
        { id: "org-a", name: "Original Name", status: "active" },
      ],
      users: [{ id: "owner-a", email: "owner@example.com" }],
      memberships: [
        { organizationId: "org-a", userId: "owner-a", role: "owner", status: "active" },
      ],
      appEntitlements: [
        { organizationId: "org-a", appId: "app-marketing", enabled: true },
      ],
      appTenantMappings: [
        {
          organizationId: "org-a",
          appId: "app-marketing",
          status: "active",
          externalTenantId: "business-a",
          externalOwnerId: "marketing-owner-a",
        },
      ],
    },
    identity: {
      organizationId: "org-a",
      hubOwnerUserId: "owner-a",
      marketingBusinessId: "business-a",
      marketingUserId: "marketing-owner-a",
      expectedName: "Original Name",
    },
  };
}

test("valid Marketing owner and tenant are accepted", () => {
  const { state, identity } = fixture();
  const result = validateMarketingRenameAuthorization(state, identity);
  assert.equal(result.organization.id, "org-a");
  assert.equal(result.owner.id, "owner-a");
});

for (const [description, change] of [
  ["cross-tenant identity", x => { x.identity.marketingBusinessId = "other-business"; }],
  ["wrong Marketing owner", x => { x.identity.marketingUserId = "other-user"; }],
  ["wrong Hub owner", x => { x.identity.hubOwnerUserId = "other-owner"; }],
  ["inactive organisation", x => { x.state.organizations[0].status = "suspended"; }],
  ["disabled entitlement", x => { x.state.appEntitlements[0].enabled = false; }],
  ["inactive mapping", x => { x.state.appTenantMappings[0].status = "pending"; }],
  ["multiple active owners", x => {
    x.state.memberships.push({
      organizationId: "org-a",
      userId: "owner-b",
      role: "owner",
      status: "active",
    });
  }],
  ["stale organisation name", x => { x.identity.expectedName = "Outdated Name"; }],
]) {
  test(`Marketing rename rejects ${description}`, () => {
    const x = fixture();
    change(x);
    assert.throws(
      () => validateMarketingRenameAuthorization(x.state, x.identity),
      { name: "MarketingRenameAccessError" },
    );
  });
}
