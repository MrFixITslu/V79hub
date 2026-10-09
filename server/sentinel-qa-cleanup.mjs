import { retainSentinelAuditMarkers } from "./sentinel-audit-retention.mjs";
import crypto from "node:crypto";

/**
 * Hub-local Sentinel QA cleanup, deliberately fail-closed.
 * The marker MUST be created by a reviewed, dedicated Sentinel-tenant creation flow.
 * Merely naming an existing workspace "Sentinel-QA-..." never grants deletion authority.
 *
 * Pure functions only: no databases, filesystem, network, sessions or side effects.
 */
export class SentinelCleanupError extends Error {
  constructor(code, message) {
    super(message);
    this.name = "SentinelCleanupError";
    this.code = code;
  }
}
const deny = (reason) => { throw new SentinelCleanupError("CLEANUP_BLOCKED", reason); };
const isArray = Array.isArray;
const allowedMarkerType = "sentinel_qa_tenant_created";
const memberTag = "sentinel_qa_member_added";
const uuid = /^[a-f0-9]{8}-[a-f0-9]{4}-[1-8][a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/i;
const userKeys = ["users", "memberships", "organizations", "appEntitlements",
  "organizationPlans", "trialReminderEvents", "billingOrders", "billingPaymentEvents",
  "ownerInvitations", "teamInvitations", "appTenantMappings",
  "passwordResetRequests", "auditEvents", "ecosystemApps"];
function ensureArrays(store) {
  if (!store || typeof store !== "object" || userKeys.some(k => !isArray(store[k]))) {
    deny("Cannot prove cleanup safety: required Hub collections are missing");
  }
}
function matchOrgName(id) { return `Sentinel-QA-${id}`; }
function associated(record, id) {
  return record.organizationId === id ||
    record.ownerOrganizationId === id ||
    record.subjectReference === id;
}
function sorted(ids) { return [...ids].sort(); }
function sha256(value) { return crypto.createHash("sha256").update(value).digest("hex"); }

/**
 * Verifies an exact Sentinel organization AND exact source marker AND every
 * dependency in the known Hub datastore. Does not mutate input.
 */
export function previewSentinelCleanup(store, { organizationId, operatorUserId } = {}) {
  ensureArrays(store);
  if (typeof organizationId !== "string" || !uuid.test(organizationId) ||
      typeof operatorUserId !== "string" || !operatorUserId) deny("Invalid target or operator");
  const organizations = store.organizations.filter(o => o.id === organizationId);
  if (organizations.length !== 1 || organizations[0].name !== matchOrgName(organizationId) ||
      organizations[0].slug !== matchOrgName(organizationId).toLowerCase()) {
    deny("Target is not an exactly named Sentinel-QA organization");
  }
  const markers = store.auditEvents.filter(e => e.type === allowedMarkerType && e.organizationId === organizationId);
  if (markers.length !== 1 || markers[0].actorUserId !== operatorUserId ||
      markers[0].details?.purpose !== "synthetic_qa_only" ||
      markers[0].details?.organizationId !== organizationId) {
    deny("No unique trusted creation marker from this platform operator");
  }
  const marker = markers[0];
  const registered = marker.details.syntheticUserIds;
  if (!isArray(registered) || registered.length < 2 || registered.length > 6 ||
      registered.some(v => typeof v !== "string") ||
      new Set(registered).size !== registered.length ||
      registered.includes(operatorUserId)) deny("Invalid synthetic user manifest");
  const userSet = new Set(registered);
  const orgMemberships = store.memberships.filter(m => m.organizationId === organizationId);
  if (orgMemberships.length !== registered.length ||
      new Set(orgMemberships.map(m => m.userId)).size !== registered.length ||
      orgMemberships.some(m => !userSet.has(m.userId)) ||
      orgMemberships.filter(m => m.role === "owner").length !== 1) {
    deny("Organization membership does not match the exact synthetic manifest");
  }
  if (store.memberships.some(m => userSet.has(m.userId) && m.organizationId !== organizationId)) {
    deny("Shared user identity detected");
  }
  if (store.users.filter(u => userSet.has(u.id)).length !== registered.length) {
    deny("One or more synthetic users cannot be uniquely identified");
  }
  // Creation evidence includes the exact, initially generated identities; owner/staff
  // cannot add an unrecorded user and later have the cleanup silently remove it.
  if (store.users.some(u => userSet.has(u.id) &&
        !String(u.username || "").toLowerCase().endsWith("@sentinel-qa.invalid"))) {
    deny("Synthetic user identity suffix mismatch");
  }
  if (store.appTenantMappings.some(m => associated(m, organizationId)) ||
      store.appEntitlements.some(v => associated(v, organizationId)) ||
      store.organizationPlans.some(v => associated(v, organizationId)) ||
      store.trialReminderEvents.some(v => associated(v, organizationId)) ||
      store.billingOrders.some(v => associated(v, organizationId)) ||
      store.billingPaymentEvents.some(v => associated(v, organizationId)) ||
      store.ecosystemApps.some(v => associated(v, organizationId))) {
    deny("App tenant, entitlement, billing, reminder or catalog reference exists");
  }
  if (store.passwordResetRequests.some(v => userSet.has(v.userId))) {
    deny("Outstanding user account recovery state detected");
  }
  if (store.ownerInvitations.some(v => associated(v, organizationId)) ||
      store.teamInvitations.some(v => associated(v, organizationId))) {
    deny("Invitations exist; revoke or reconcile them through supported workflows");
  }
  const orgAudit = store.auditEvents.filter(e => e.organizationId === organizationId);
  if (orgAudit.some(e => ![allowedMarkerType,memberTag].includes(e.type))) {
    deny("Unexpected audit history: manual review required");
  }
  if (store.auditEvents.some(e => e.organizationId !== organizationId && userSet.has(e.actorUserId))) {
    deny("Synthetic user appears as actor in another organization's audit history");
  }
  // Future schema fields can contain organization/user links that are unknown
  // to this module. Fail closed rather than silently orphaning those records.
  const ownedIdentifiers = [organizationId, ...registered];
  const scan = (record, label) => {
    let raw;
    try { raw = JSON.stringify(record); }
    catch { deny("Uninspectable " + label + " record; cleanup blocked"); }
    if (typeof raw === "string" && ownedIdentifiers.some(key => raw.includes(key))) {
      deny("Related reference in " + label + "; manual review required");
    }
  };
  for (const [collection, value] of Object.entries(store)) {
    if (["users", "organizations", "memberships", "auditEvents"].includes(collection)) continue;
    scan(value, collection);
  }
  // Do not skip references in surviving user, organization or membership records.
  // Only the exact manifest-owned records will be deleted; any surviving record
  // containing a synthetic identity must prevent deletion.
  for (const item of store.users) {
    if (!userSet.has(item.id)) scan(item, "surviving user");
  }
  for (const item of store.organizations) {
    if (item.id !== organizationId) scan(item, "surviving organization");
  }
  for (const item of store.memberships) {
    if (item.organizationId !== organizationId) scan(item, "surviving membership");
  }
  for (const item of store.auditEvents) {
    if (item.organizationId !== organizationId) scan(item, "other-organization audit");
  }

  const memberIds = sorted(registered);
  const fingerprint = sha256(JSON.stringify({
    v:1,organizationId, markerId:marker.id, operatorUserId, memberIds,
    memberCount:orgMemberships.length, orgCreatedAt:organizations[0].createdAt,
    markerCreatedAt:marker.createdAt, orgAuditIds:sorted(orgAudit.map(e=>e.id)),
  }));
  return Object.freeze({
    state:"eligible-hub-only", organizationId, organizationName:organizations[0].name,
    markerId: marker.id, memberIds, memberCount:memberIds.length,
    previewHash:fingerprint, externalTenants:0, billingReferences:0,
    note:"Preview only; the endpoint is disabled unless explicitly enabled at release.",
  });
}

export function removeSentinelCleanup(store, {
  organizationId, operatorUserId, confirmName, previewHash, deletedAt, auditId,
} = {}) {
  const result = previewSentinelCleanup(store, {organizationId,operatorUserId});
  if (confirmName !== `DELETE ${result.organizationName}` ||
      typeof previewHash !== "string" || previewHash !== result.previewHash) {
    deny("Exact deletion phrase and matching fresh preview hash are required");
  }
  if (typeof deletedAt !== "string" || Number.isNaN(Date.parse(deletedAt)) ||
      typeof auditId !== "string" || !uuid.test(auditId)) deny("Invalid deletion audit metadata");
  const users = new Set(result.memberIds);
  const nextStore = structuredClone(store);
  nextStore.organizations = nextStore.organizations.filter(o => o.id !== organizationId);
  nextStore.memberships = nextStore.memberships.filter(m => m.organizationId !== organizationId);
  nextStore.users = nextStore.users.filter(u => !users.has(u.id));
  // No app mappings, billing records, entitlements, resets or invitations can exist:
  // those preconditions were proven above. Remove ONLY this org's synthetic QA audit.
  nextStore.auditEvents = nextStore.auditEvents.filter(e => e.organizationId !== organizationId);
  nextStore.auditEvents.push({
    id:auditId, actorUserId:operatorUserId, type:"sentinel_qa_tenant_deleted",
    createdAt:deletedAt,
    details:{ deletedOrganizationId:organizationId, syntheticUsersDeleted:users.size,
      markerId:result.markerId, previewHash:result.previewHash }
  });
  if(nextStore.auditEvents.length>5000) nextStore.auditEvents=retainSentinelAuditMarkers(nextStore.auditEvents);
  return {nextStore, removed: {
    organizationId, userIds:result.memberIds, memberCount:result.memberCount,
    auditId, state:"removed-from-hub-store"
  }};
}
