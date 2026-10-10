
/**
 * Pure policy validator for a PROPOSED Phase 3A disposable VM manifest.
 * No VM creation, downloads, connections or changes are performed.
 */
export function validateIsolatedAgentStagingPlan(plan) {
  const errors = [];
  if (!plan || typeof plan !== "object" || Array.isArray(plan)) return { ready:false, errors:["plan must be an object"] };
  const mustBeTrue = {
    disposableVm: "VM must be disposable and in a separate cloud account/project",
    syntheticDataOnly: "Only synthetic tenant data may be used",
    denyProductionLan: "Production LAN/Tailscale connections must be blocked",
    privateAppNetwork: "Application and database must use a private, non-public network",
    outboundWritesBlocked: "External emails, payments, customer writes and social posting must be blocked",
    ephemeralKeysGeneratedInsideVm: "Separate test-only keys must be generated inside the VM",
    noProductionMounts: "Production volumes and backups must not be mounted",
    ownerMfaRequired: "Real owner-password+TOTP staging flow must remain enabled",
    destructionPlanConfirmed: "VM and temporary disks must have a verified deletion plan",
    authorizedExecutor: "Staging launcher must have an explicitly permitted execution route",
    independentBudgetApproved: "Founder must approve provider and upper cost cap",
  };
  for (const [key,message] of Object.entries(mustBeTrue)) {
    if (plan[key] !== true) errors.push(message);
  }
  const sha = /^[0-9a-f]{40}$/i;
  for (const key of ["hubCommit","tiquetCommit"]) if (!sha.test(String(plan[key] || ""))) {
    errors.push(key+" must be a pinned 40-character commit SHA");
  }
  for (const key of ["hubOrigin", "tiquetOrigin", "databaseOrigin"]) {
    const value=String(plan[key] || "").trim().toLowerCase();
    if (!value || /v79sl\.com|192\.168\.|10\.1\.211\.|localhost:5432|host\.docker\.internal/.test(value)) {
      errors.push(key+" must be a synthetic private staging address, not a production endpoint");
    }
    if (/^https?:\/\//.test(value) || /\b(public|internet|0\.0\.0\.0)\b/.test(value)) {
      errors.push(key+" must not expose a public URL or bind address");
    }
  }
  const budget=plan.maxCostUsd;
  if (!(typeof budget === "number" && Number.isFinite(budget) && budget > 0 && budget <= 100)) {
    errors.push("maxCostUsd must be a finite, explicitly approved amount no greater than 100");
  }
  if (typeof plan.destroyByUtc !== "string" || !/Z$/.test(plan.destroyByUtc) ||
      !Number.isFinite(Date.parse(plan.destroyByUtc))) {
    errors.push("destroyByUtc must be an explicit UTC deletion deadline");
  } else {
    const now=Date.now(), exp=Date.parse(plan.destroyByUtc);
    if (exp <= now || exp > now + 48*3600_000) errors.push("deletion deadline must be within 48 hours");
  }
  if (plan.productionEnvFile || plan.productionSshKey || plan.productionBackupPath ||
      plan.productionTailscaleKey || plan.allowPublicIngress || plan.activateBilling ||
      plan.enableAgentWrites || plan.mergeMain || plan.deployProduction) {
    errors.push("production secrets, public ingress, writes, billing or merge/deploy directives are forbidden");
  }
  if (plan.hostKind !== "dedicated-cloud-vm") errors.push("hostKind must be dedicated-cloud-vm");
  if (typeof plan.provider !== "string" || !/^[a-z0-9][a-z0-9 -]{2,40}$/i.test(plan.provider)) {
    errors.push("Cloud provider must be explicitly named");
  }
  // Reference file paths must never escape the proposed staging work directory.
  if (plan.localOutputPath !== undefined) {
    if (typeof plan.localOutputPath !== "string" || !/^\/tmp\/v79-agent-stage-[a-z0-9-]{8,64}$/i.test(plan.localOutputPath)) {
      errors.push("localOutputPath must be a unique /tmp/v79-agent-stage-* location");
    }
  }
  return { ready: errors.length===0, errors };
}
