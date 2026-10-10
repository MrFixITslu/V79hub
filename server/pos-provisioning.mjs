export function posTenantMapping(store, organizationId) {
  return (store.appTenantMappings || []).find(mapping =>
    mapping.organizationId === organizationId && mapping.appId === "app-v79pos"
  ) || null;
}

export function posProvisioningTarget(store, organizationId) {
  const organization = (store.organizations || []).find(org =>
    org.id === organizationId && org.status === "active"
  );
  if (!organization) throw new Error("Organization is not active.");

  const entitlement = (store.appEntitlements || []).find(entry =>
    entry.organizationId === organizationId &&
    entry.appId === "app-v79pos" &&
    entry.enabled === true
  );
  if (!entitlement) throw new Error("POS is not enabled for this organization.");

  const mapping = posTenantMapping(store, organizationId);
  if (!mapping || !["pending", "active"].includes(mapping.status)) {
    throw new Error("POS tenant mapping is not ready for provisioning.");
  }
  if (mapping.status === "active" && mapping.externalTenantId && mapping.externalTenantId !== organizationId) {
    throw new Error("POS tenant mapping does not match the Hub organization.");
  }

  const owners = (store.memberships || []).filter(member =>
    member.organizationId === organizationId &&
    member.status === "active" &&
    member.role === "owner"
  );
  if (owners.length !== 1) throw new Error("Organization must have exactly one active owner.");

  const owner = (store.users || []).find(user => user.id === owners[0].userId);
  if (!owner) throw new Error("Organization owner identity is missing.");

  return { organization, owner, mapping };
}

export function activatePosTenantMapping(store, organizationId, externalTenantId, actorUserId, now = new Date().toISOString()) {
  if (externalTenantId !== organizationId) throw new Error("POS tenant identity mismatch.");
  const next = structuredClone(store);
  const mapping = posTenantMapping(next, organizationId);
  if (!mapping || !["pending", "active"].includes(mapping.status)) {
    throw new Error("POS tenant mapping is not ready for activation.");
  }
  if (mapping.externalTenantId && mapping.externalTenantId !== externalTenantId) {
    throw new Error("POS tenant mapping conflicts with the provisioned tenant.");
  }

  mapping.status = "active";
  mapping.externalTenantId = externalTenantId;
  mapping.updatedAt = now;

  next.auditEvents.push({
    id: crypto.randomUUID(),
    organizationId,
    actorUserId,
    type: "pos_tenant_provisioned",
    createdAt: now,
    details: { appId: "app-v79pos", externalTenantId },
  });
  if (next.auditEvents.length > 5000) next.auditEvents = next.auditEvents.slice(-5000);
  return next;
}

export function posTenantLaunchReady(store, organizationId, legacyOrganizationId) {
  if (organizationId === legacyOrganizationId) return true;
  const mapping = posTenantMapping(store, organizationId);
  return Boolean(
    mapping &&
    mapping.status === "active" &&
    mapping.externalTenantId === organizationId
  );
}
