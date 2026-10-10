import crypto from "node:crypto";

export function tiquetTenantMapping(store, organizationId) {
  return (store.appTenantMappings || []).find(mapping =>
    mapping.organizationId === organizationId && mapping.appId === "app-tiquet"
  ) || null;
}

export function tiquetProvisioningTarget(store, organizationId) {
  const organization = (store.organizations || []).find(org =>
    org.id === organizationId && org.status === "active"
  );
  if (!organization) throw new Error("Organization is not active.");

  const entitlement = (store.appEntitlements || []).find(entry =>
    entry.organizationId === organizationId &&
    entry.appId === "app-tiquet" &&
    entry.enabled === true
  );
  if (!entitlement) throw new Error("Tiquet is not enabled for this organization.");

  const mapping = tiquetTenantMapping(store, organizationId);
  if (!mapping || !["pending", "active"].includes(mapping.status)) {
    throw new Error("Tiquet tenant mapping is not ready for provisioning.");
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
    throw new Error("Organization owner must have a verified email for Tiquet.");
  }

  return { organization, owner, ownerEmail: email, mapping };
}

export function activateTiquetTenantMapping(
  store,
  organizationId,
  returnedOrganizationId,
  accountId,
  userId,
  actorUserId,
  now = new Date().toISOString(),
) {
  if (returnedOrganizationId !== organizationId) throw new Error("Tiquet Hub organization identity mismatch.");
  if (typeof accountId !== "string" || !accountId.trim()) throw new Error("Tiquet account identity is missing.");
  if (typeof userId !== "string" || !userId.trim()) throw new Error("Tiquet owner identity is missing.");

  const next = structuredClone(store);
  const mapping = tiquetTenantMapping(next, organizationId);
  if (!mapping || !["pending", "active"].includes(mapping.status)) {
    throw new Error("Tiquet tenant mapping is not ready for activation.");
  }
  if (mapping.externalTenantId && mapping.externalTenantId !== accountId) {
    throw new Error("Tiquet tenant mapping conflicts with the provisioned account.");
  }
  if (mapping.externalOwnerId && mapping.externalOwnerId !== userId) {
    throw new Error("Tiquet tenant mapping conflicts with the provisioned owner.");
  }

  mapping.status = "active";
  mapping.externalTenantId = accountId;
  mapping.externalOwnerId = userId;
  mapping.updatedAt = now;

  next.auditEvents.push({
    id: crypto.randomUUID(),
    organizationId,
    actorUserId,
    type: "tiquet_tenant_provisioned",
    createdAt: now,
    details: { appId: "app-tiquet", accountId, userId },
  });
  if (next.auditEvents.length > 5000) next.auditEvents = next.auditEvents.slice(-5000);
  return next;
}

export function tiquetTenantLaunchReady(store, organizationId, legacyOrganizationId) {
  if (organizationId === legacyOrganizationId) return true;
  const mapping = tiquetTenantMapping(store, organizationId);
  return Boolean(
    mapping &&
    mapping.status === "active" &&
    typeof mapping.externalTenantId === "string" &&
    mapping.externalTenantId.length > 0 &&
    typeof mapping.externalOwnerId === "string" &&
    mapping.externalOwnerId.length > 0
  );
}
