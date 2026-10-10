// V79-01: deterministic subscription access. No side effects or scheduler dependency.
export const TRIAL_DAYS = 14;

export function beginTrial(start = new Date()) {
  const timestamp = new Date(start).getTime();
  if (!Number.isFinite(timestamp)) throw new Error("Invalid trial start");
  return {
    accessPolicyType: "trial",
    status: "trial",
    trialStartedAt: new Date(timestamp).toISOString(),
    trialEndsAt: new Date(timestamp + TRIAL_DAYS * 24 * 60 * 60 * 1000).toISOString(),
  };
}

export function accessDecision(plan, now = Date.now(), isInternalOwner = false) {
  const time = new Date(now).getTime();
  if (!Number.isFinite(time)) return { allowed: false, reason: "invalid_time" };
  if (isInternalOwner) return { allowed: true, reason: "internal_owner" };
  if (!plan) return { allowed: false, reason: "plan_missing" };
  if (plan.status === "paused" || plan.status === "cancelled") {
    return { allowed: false, reason: "plan_" + plan.status };
  }
  if (plan.status === "trial" && plan.accessPolicyType === "trial") {
    const start = Date.parse(plan.trialStartedAt || "");
    const end = Date.parse(plan.trialEndsAt || "");
    if (!Number.isFinite(start) || !Number.isFinite(end) ||
        end - start !== TRIAL_DAYS * 86400000 || time < start) {
      return { allowed: false, reason: "trial_invalid" };
    }
    return time < end
      ? { allowed: true, reason: "trial_valid", expiresAt: plan.trialEndsAt }
      : { allowed: false, reason: "trial_expired", expiresAt: plan.trialEndsAt };
  }
  if (plan.status === "active" && plan.accessPolicyType === "paid") {
    const end = Date.parse(plan.paidThroughAt || "");
    return Number.isFinite(end) && time < end
      ? { allowed: true, reason: "paid_valid", expiresAt: plan.paidThroughAt }
      : { allowed: false, reason: "paid_expired" };
  }
  return { allowed: false, reason: "unverified_subscription" };
}

export function classifyLegacyPlan(plan, isInternalOwner = false) {
  // Pure migration proposal: never infer that legacy 'active' means payment verified.
  if (isInternalOwner) return { ...plan, accessPolicyType: "internal" };
  if (plan.accessPolicyType) return { ...plan };
  return { ...plan, accessPolicyType: "legacy_review" };
}
