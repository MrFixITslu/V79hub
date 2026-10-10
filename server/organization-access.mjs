import { accessDecision } from "./subscription-access.mjs";
export function activeMembership(store, userId, organizationId) {
  const organization = store.organizations.find(org => org.id === organizationId && org.status === 'active');
  if (!organization) return null;
  return store.memberships.find(member =>
    member.userId === userId &&
    member.organizationId === organizationId &&
    member.status === 'active'
  ) || null;
}

export function activeMembershipsForUser(store, userId) {
  return (store.memberships || []).filter(member =>
    member.userId === userId &&
    member.status === 'active' &&
    store.organizations.some(org => org.id === member.organizationId && org.status === 'active')
  );
}

export function sessionRole(member) {
  if (!member) return null;
  return member.role === 'owner' ? 'admin' : member.role;
}

export function legacyWorkspaceAccess(store, userId, organizationId, legacyOrganizationId) {
  return organizationId === legacyOrganizationId
    ? activeMembership(store, userId, organizationId)
    : null;
}

export function enabledAppIds(store, organizationId, ownerOrganizationId = "", now = Date.now()) {
  const organization = store.organizations.find(org => org.id === organizationId && org.status === 'active');
  if (!organization) return [];
  const isOwner = Boolean(ownerOrganizationId && organizationId === ownerOrganizationId);
  const plan = (store.organizationPlans || []).find(row => row.organizationId === organizationId);
  if (!accessDecision(plan, now, isOwner).allowed) return [];
  return (store.appEntitlements || [])
    .filter(entry => entry.organizationId === organizationId && entry.enabled === true)
    .map(entry => entry.appId);
}

export function organizationCanAccessApp(store, organizationId, appId, ownerOrganizationId = "", now = Date.now()) {
  return enabledAppIds(store, organizationId, ownerOrganizationId, now).includes(appId);
}

export function visibleEcosystemApps(store, organizationId, ownerOrganizationId = "", now = Date.now()) {
  const allowed = new Set(enabledAppIds(store, organizationId, ownerOrganizationId, now));
  return (store.ecosystemApps || []).filter(app =>
    allowed.has(app.id) &&
    (!app.id.startsWith('app-custom-') || app.ownerOrganizationId === organizationId)
  );
}

export function organizationCanMutateApp(store, organizationId, appId, ownerOrganizationId = "") {
  const app = (store.ecosystemApps || []).find(item => item.id === appId);
  return Boolean(
    app &&
    app.id.startsWith('app-custom-') &&
    app.ownerOrganizationId === organizationId &&
    organizationCanAccessApp(store, organizationId, appId, ownerOrganizationId)
  );
}

export function validLegacyLaunch(store, entry, product, legacyOrganizationId, ownerUserId) {
  const appId = { pos: 'app-v79pos', ffpro: 'app-ffpro', tiquet: 'app-tiquet', marketing: 'app-marketing' }[product];
  return Boolean(
    appId &&
    entry &&
    entry.product === product &&
    entry.expiresAt >= Date.now() &&
    entry.tenantId === legacyOrganizationId &&
    entry.userId === ownerUserId &&
    activeMembership(store, entry.userId, entry.tenantId)?.role === 'owner' &&
    organizationCanAccessApp(store, entry.tenantId, appId, legacyOrganizationId)
  );
}