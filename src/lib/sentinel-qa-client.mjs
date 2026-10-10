// Browser-side orchestration, shared with disposable transport tests.
// Return only redacted status. Never return or persist the API's one-time passwords.
export async function createSupervisedQa(request, baseline) {
  const result = await request("organizations", { confirm: "CREATE ISOLATED SENTINEL QA" });
  const current = await request("status");
  const organization = current.organizations?.[0];
  if (!result.organization || current.organizations?.length !== 1 ||
      organization.id !== result.organization.id || organization.name !== result.organization.name ||
      !organization.eligible || organization.memberCount !== 3 ||
      current.syntheticUserCount !== 3 || current.syntheticMembershipCount !== 3 ||
      current.userCount !== baseline.userCount + 3 || current.organizationCount !== baseline.organizationCount + 1) {
    throw new Error("Creation response requires operator review; the exact temporary manifest could not be verified.");
  }
  return current;
}

export async function cleanupSupervisedQa(request, preview, confirmation) {
  if (preview.state !== "eligible-hub-only" || preview.externalTenants !== 0 ||
      preview.billingReferences !== 0 || confirmation !== "DELETE " + preview.organizationName) {
    throw new Error("Exact eligible preview and deletion phrase are required.");
  }
  const result = await request("organizations/" + encodeURIComponent(preview.organizationId) + "/cleanup", {
    confirmName: confirmation, previewHash: preview.previewHash,
  });
  const current = await request("status");
  if (!result.success || result.organizationId !== preview.organizationId ||
      result.syntheticUsersDeleted !== preview.memberCount ||
      !Array.isArray(current.organizations) ||
      current.organizations.some(o => o.id === preview.organizationId) ||
      current.syntheticUserCount !== 0 || current.syntheticMembershipCount !== 0 ||
      current.latestCleanup?.auditId !== result.auditId ||
      current.latestCleanup.organizationId !== preview.organizationId ||
      current.latestCleanup.syntheticUsersDeleted !== preview.memberCount) {
    throw new Error("Cleanup response requires operator review; absence could not be fully verified.");
  }
  return current;
}
