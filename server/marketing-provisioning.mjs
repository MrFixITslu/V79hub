import crypto from "node:crypto";

export function marketingTenantMapping(store, organizationId) {
  return (store.appTenantMappings || []).find(mapping =>
    mapping.organizationId === organizationId && mapping.appId === "app-marketing"
  ) || null;
}

export function marketingProvisioningTarget(store, organizationId) {
  const organization = (store.organizations || []).find(org =>
    org.id === organizationId && org.status === "active"
  );
  if (!organization) throw new Error("Organization is not active.");

  const entitlement = (store.appEntitlements || []).find(entry =>
    entry.organizationId === organizationId &&
    entry.appId === "app-marketing" &&
    entry.enabled === true
  );
  if (!entitlement) throw new Error("Marketing is not enabled for this organization.");

  const mapping = marketingTenantMapping(store, organizationId);
  if (!mapping || !["pending", "active"].includes(mapping.status)) {
    throw new Error("Marketing tenant mapping is not ready for provisioning.");
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
    throw new Error("Organization owner must have a verified email for Marketing.");
  }

  return { organization, owner, ownerEmail: email, mapping };
}

export function activateMarketingTenantMapping(
  store,
  organizationId,
  returnedOrganizationId,
  businessId,
  userId,
  actorUserId,
  now = new Date().toISOString(),
) {
  if (returnedOrganizationId !== organizationId) throw new Error("Marketing Hub organization identity mismatch.");
  if (typeof businessId !== "string" || !businessId.trim()) throw new Error("Marketing business identity is missing.");
  if (typeof userId !== "string" || !userId.trim()) throw new Error("Marketing owner identity is missing.");

  const next = structuredClone(store);
  const mapping = marketingTenantMapping(next, organizationId);
  if (!mapping || !["pending", "active"].includes(mapping.status)) {
    throw new Error("Marketing tenant mapping is not ready for activation.");
  }
  if (mapping.externalTenantId && mapping.externalTenantId !== businessId) {
    throw new Error("Marketing tenant mapping conflicts with the provisioned business.");
  }
  if (mapping.externalOwnerId && mapping.externalOwnerId !== userId) {
    throw new Error("Marketing tenant mapping conflicts with the provisioned owner.");
  }

  mapping.status = "active";
  mapping.externalTenantId = businessId;
  mapping.externalOwnerId = userId;
  mapping.updatedAt = now;

  next.auditEvents.push({
    id: crypto.randomUUID(),
    organizationId,
    actorUserId,
    type: "marketing_tenant_provisioned",
    createdAt: now,
    details: { appId: "app-marketing", businessId, userId },
  });
  if (next.auditEvents.length > 5000) next.auditEvents = next.auditEvents.slice(-5000);

  return next;
}

export function marketingTenantLaunchReady(store, organizationId, legacyOrganizationId) {
  if (organizationId === legacyOrganizationId) return true;
  const mapping = marketingTenantMapping(store, organizationId);
  return Boolean(
    mapping &&
    mapping.status === "active" &&
    typeof mapping.externalTenantId === "string" &&
    mapping.externalTenantId.length > 0 &&
    typeof mapping.externalOwnerId === "string" &&
    mapping.externalOwnerId.length > 0
  );
}
