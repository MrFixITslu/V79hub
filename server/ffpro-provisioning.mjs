import crypto from "node:crypto";

export function ffproTenantMapping(store, organizationId) {
  return (store.appTenantMappings || []).find(mapping =>
    mapping.organizationId === organizationId && mapping.appId === "app-ffpro"
  ) || null;
}

export function ffproProvisioningTarget(store, organizationId) {
  const organization = (store.organizations || []).find(org =>
    org.id === organizationId && org.status === "active"
  );
  if (!organization) throw new Error("Organization is not active.");

  const entitlement = (store.appEntitlements || []).find(entry =>
    entry.organizationId === organizationId &&
    entry.appId === "app-ffpro" &&
    entry.enabled === true
  );
  if (!entitlement) throw new Error("FFPRO is not enabled for this organization.");

  const mapping = ffproTenantMapping(store, organizationId);
  if (!mapping || !["pending", "active"].includes(mapping.status)) {
    throw new Error("FFPRO tenant mapping is not ready for provisioning.");
  }
  if (mapping.status === "active" && mapping.externalTenantId && mapping.externalTenantId !== organizationId) {
    throw new Error("FFPRO tenant mapping does not match the Hub organization.");
  }

  const owners = (store.memberships || []).filter(member =>
    member.organizationId === organizationId &&
    member.status === "active" &&
    member.role === "owner"
  );
  if (owners.length !== 1) throw new Error("Organization must have exactly one active owner.");

  const owner = (store.users || []).find(user => user.id === owners[0].userId);
  if (!owner) throw new Error("Organization owner identity is missing.");
  const email = String(owner.email || owner.username || "").trim().toLowerCase();
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
    throw new Error("Organization owner must have a verified email for FFPRO.");
  }

  return { organization, owner, ownerEmail: email, mapping };
}

export function activateFfproTenantMapping(store, organizationId, externalTenantId, financeUserId, actorUserId, now = new Date().toISOString()) {
  if (externalTenantId !== organizationId) throw new Error("FFPRO tenant identity mismatch.");
  if (typeof financeUserId !== "string" || !financeUserId.trim()) throw new Error("FFPRO finance owner identity is missing.");
  const next = structuredClone(store);
  const mapping = ffproTenantMapping(next, organizationId);
  if (!mapping || !["pending", "active"].includes(mapping.status)) {
    throw new Error("FFPRO tenant mapping is not ready for activation.");
  }
  if (mapping.externalTenantId && mapping.externalTenantId !== externalTenantId) {
    throw new Error("FFPRO tenant mapping conflicts with the provisioned tenant.");
  }

  mapping.status = "active";
  mapping.externalTenantId = externalTenantId;
  mapping.updatedAt = now;
  mapping.externalOwnerId = financeUserId;

  next.auditEvents.push({
    id: crypto.randomUUID(),
    organizationId,
    actorUserId,
    type: "ffpro_tenant_provisioned",
    createdAt: now,
    details: { appId: "app-ffpro", externalTenantId, financeUserId },
  });
  if (next.auditEvents.length > 5000) next.auditEvents = next.auditEvents.slice(-5000);
  return next;
}

export function ffproTenantLaunchReady(store, organizationId, legacyOrganizationId) {
  if (organizationId === legacyOrganizationId) return true;
  const mapping = ffproTenantMapping(store, organizationId);
  return Boolean(
    mapping &&
    mapping.status === "active" &&
    mapping.externalTenantId === organizationId &&
    typeof mapping.externalOwnerId === "string" &&
    mapping.externalOwnerId.length > 0
  );
}
