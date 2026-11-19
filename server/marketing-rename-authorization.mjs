export class MarketingRenameAccessError extends Error {
  constructor(message, code = "denied") {
    super(message);
    this.name = "MarketingRenameAccessError";
    this.code = code;
  }
}

export function validateMarketingRenameAuthorization(
  state,
  {
    organizationId,
    hubOwnerUserId,
    marketingBusinessId,
    marketingUserId,
    expectedName,
  },
  { checkExpectedName = true } = {},
) {
  const deny = message => {
    throw new MarketingRenameAccessError(message);
  };

  const organization = (state.organizations || []).find(
    item => item.id === organizationId && item.status === "active",
  );
  if (!organization) deny("Organisation is not active.");

  const entitlement = (state.appEntitlements || []).find(
    item =>
      item.organizationId === organizationId &&
      item.appId === "app-marketing" &&
      item.enabled === true,
  );
  if (!entitlement) deny("Marketing entitlement is not active.");

  const mapping = (state.appTenantMappings || []).find(
    item =>
      item.organizationId === organizationId &&
      item.appId === "app-marketing" &&
      item.status === "active",
  );
  if (
    !mapping ||
    !mapping.externalTenantId ||
    !mapping.externalOwnerId ||
    mapping.externalTenantId !== marketingBusinessId ||
    mapping.externalOwnerId !== marketingUserId
  ) {
    deny("Marketing tenant identity mismatch.");
  }

  const owners = (state.memberships || []).filter(
    item =>
      item.organizationId === organizationId &&
      item.status === "active" &&
      item.role === "owner",
  );
  if (owners.length !== 1 || owners[0].userId !== hubOwnerUserId) {
    deny("Organisation owner identity mismatch.");
  }

  const owner = (state.users || []).find(
    item => item.id === hubOwnerUserId,
  );
  if (!owner) deny("Organisation owner record is missing.");

  if (checkExpectedName && organization.name !== expectedName) {
    throw new MarketingRenameAccessError(
      "Organisation name changed since this request was created.",
      "conflict",
    );
  }

  return { organization, owner };
}
