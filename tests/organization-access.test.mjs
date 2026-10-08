import test from 'node:test';
import assert from 'node:assert/strict';
import {
  activeMembership,
  activeMembershipsForUser,
  enabledAppIds,
  organizationCanAccessApp,
  organizationCanMutateApp,
  sessionRole,
  validLegacyLaunch,
  visibleEcosystemApps,
} from '../server/organization-access.mjs';

function makeStore() {
  return {
    organizations: [
      { id: 'v79', status: 'active' },
      { id: 'business-b', status: 'active' },
      { id: 'suspended', status: 'suspended' },
    ],
    memberships: [
      { organizationId: 'v79', userId: 'owner-a', role: 'owner', status: 'active' },
      { organizationId: 'business-b', userId: 'owner-b', role: 'owner', status: 'active' },
      { organizationId: 'v79', userId: 'shared', role: 'staff', status: 'active' },
      { organizationId: 'business-b', userId: 'shared', role: 'manager', status: 'active' },
      { organizationId: 'v79', userId: 'revoked', role: 'staff', status: 'revoked' },
      { organizationId: 'suspended', userId: 'blocked', role: 'owner', status: 'active' },
    ],
    organizationPlans: [
      { organizationId: 'v79', status: 'active', accessPolicyType: 'internal' },
      { organizationId: 'business-b', status: 'active', accessPolicyType: 'paid', paidThroughAt: '2099-01-01T00:00:00.000Z' },
    ],
    appEntitlements: [
      { organizationId: 'v79', appId: 'app-v79pos', enabled: true },
      { organizationId: 'v79', appId: 'app-custom-a', enabled: true },
      { organizationId: 'business-b', appId: 'app-tiquet', enabled: true },
      { organizationId: 'business-b', appId: 'app-custom-b', enabled: true },
      { organizationId: 'business-b', appId: 'app-custom-unowned', enabled: true },
    ],
    ecosystemApps: [
      { id: 'app-v79pos', name: 'POS' },
      { id: 'app-tiquet', name: 'Tiquet' },
      { id: 'app-custom-a', name: 'A private app', ownerOrganizationId: 'v79' },
      { id: 'app-custom-b', name: 'B private app', ownerOrganizationId: 'business-b' },
      { id: 'app-custom-unowned', name: 'Unowned legacy app' },
    ],
  };
}

test('memberships are resolved only inside the exact active organization', () => {
  const store = makeStore();
  assert.equal(activeMembership(store, 'owner-a', 'v79')?.role, 'owner');
  assert.equal(activeMembership(store, 'owner-a', 'business-b'), null);
  assert.equal(activeMembership(store, 'owner-b', 'v79'), null);
  assert.equal(activeMembership(store, 'revoked', 'v79'), null);
  assert.equal(activeMembership(store, 'blocked', 'suspended'), null);
});

test('a shared account keeps separate roles in separate workspaces', () => {
  const store = makeStore();
  const memberships = activeMembershipsForUser(store, 'shared');
  assert.deepEqual(memberships.map(m => [m.organizationId, sessionRole(m)]), [
    ['v79', 'staff'],
    ['business-b', 'manager'],
  ]);
});

test('app entitlements and private custom apps do not cross organizations', () => {
  const store = makeStore();
  assert.deepEqual(enabledAppIds(store, 'v79', 'v79').sort(), ['app-custom-a', 'app-v79pos']);
  assert.deepEqual(enabledAppIds(store, 'business-b').sort(), ['app-custom-b', 'app-custom-unowned', 'app-tiquet']);

  assert.deepEqual(
    visibleEcosystemApps(store, 'v79', 'v79').map(app => app.id).sort(),
    ['app-custom-a', 'app-v79pos']
  );
  assert.deepEqual(
    visibleEcosystemApps(store, 'business-b').map(app => app.id).sort(),
    ['app-custom-b', 'app-tiquet']
  );

  assert.equal(organizationCanMutateApp(store, 'v79', 'app-custom-a', 'v79'), true);
  assert.equal(organizationCanMutateApp(store, 'business-b', 'app-custom-a'), false);
  assert.equal(organizationCanMutateApp(store, 'v79', 'app-v79pos', 'v79'), false);
  assert.equal(organizationCanAccessApp(store, 'business-b', 'app-v79pos'), false);
});

test('legacy product launch remains fail-closed for non-V79 workspaces', () => {
  const store = makeStore();
  const ticket = (userId, tenantId) => ({
    userId,
    tenantId,
    product: 'pos',
    expiresAt: Date.now() + 60_000,
  });

  assert.equal(validLegacyLaunch(store, ticket('owner-a', 'v79'), 'pos', 'v79', 'owner-a'), true);
  assert.equal(validLegacyLaunch(store, ticket('owner-b', 'business-b'), 'pos', 'v79', 'owner-a'), false);
  assert.equal(validLegacyLaunch(store, ticket('owner-a', 'business-b'), 'pos', 'v79', 'owner-a'), false);
  assert.equal(validLegacyLaunch(store, ticket('shared', 'v79'), 'pos', 'v79', 'owner-a'), false);
});