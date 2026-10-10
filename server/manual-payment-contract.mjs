import { addBillingPeriod, normalizeMoney } from "./billing-contract.mjs";

export function manualInvoiceEligibility(plan, ownerWorkspace = false) {
  if (ownerWorkspace) return { ok: false, code: "owner_workspace" };
  if (!plan || !["monthly", "annual"].includes(plan.billingCycle)) {
    return { ok: false, code: "unsupported_billing_cycle" };
  }
  if (!["trial", "active"].includes(plan.status)) return { ok: false, code: "plan_not_eligible" };
  const amount = normalizeMoney(plan.priceXcd);
  if (amount === null || amount <= 0 || amount > 1_000_000) return { ok: false, code: "missing_plan_price" };
  return { ok: true, amount, currency: "XCD", billingCycle: plan.billingCycle };
}

export function manualReceiptDecision({ order, plan, organization, orders, bankReference, evidenceNote, receivedAmount, bankStatementVerified, confirmation, now = new Date() }) {
  if (!order || order.provider !== "manual" || order.sourceApp !== "hub" ||
      order.kind !== "subscription" || order.status !== "pending" || !order.organizationId) {
    return { ok: false, code: "order_not_pending" };
  }
  if (!organization || organization.id !== order.organizationId || organization.status !== "active") {
    return { ok: false, code: "organization_not_active" };
  }
  const eligibility = manualInvoiceEligibility(plan, false);
  if (!eligibility.ok || plan.organizationId !== order.organizationId ||
      eligibility.amount !== order.amount || eligibility.currency !== order.currency ||
      eligibility.billingCycle !== order.billingCycleAtOrder) {
    return { ok: false, code: "plan_changed" };
  }
  if (confirmation !== `CONFIRM ${order.id}`) return { ok: false, code: "confirmation_required" };
  if (bankStatementVerified !== true) return { ok: false, code: "bank_statement_not_verified" };
  const reference = typeof bankReference === "string" ? bankReference.trim().toUpperCase() : "";
  const note = typeof evidenceNote === "string" ? evidenceNote.trim() : "";
  if (!/^[A-Z0-9][A-Z0-9_/. -]{5,99}$/.test(reference) ||
      note.length < 20 || note.length > 500) {
    return { ok: false, code: "independent_receipt_evidence_required" };
  }
  // Never round a mismatched or fractional-cent deposit up to the invoice.
  const rawReceipt = Number(receivedAmount);
  const receiptAmount = normalizeMoney(receivedAmount);
  if (!Number.isFinite(rawReceipt) ||
      Math.abs(rawReceipt * 100 - Math.round(rawReceipt * 100)) > 1e-7 ||
      receiptAmount === null || receiptAmount !== order.amount) {
    return { ok: false, code: "receipt_amount_mismatch" };
  }
  const paidReference = "manual:" + reference;
  if ((orders || []).some(item => item.id !== order.id && item.status === "paid" &&
      String(item.providerTransactionId || "").toUpperCase() === paidReference.toUpperCase())) {
    return { ok: false, code: "bank_reference_already_used" };
  }
  const time = new Date(now);
  if (!Number.isFinite(time.getTime())) return { ok: false, code: "invalid_time" };
  const existingPaidThrough = plan.accessPolicyType === "paid" ? Date.parse(plan.paidThroughAt || "") : NaN;
  const base = Number.isFinite(existingPaidThrough) && existingPaidThrough > time.getTime()
    ? new Date(existingPaidThrough) : time;
  const paidThroughAt = addBillingPeriod(base, plan.billingCycle).toISOString();
  return { ok: true, bankReference: reference, evidenceNote: note, paidReference,
    paidAt: time.toISOString(), paidThroughAt, renewalDate: paidThroughAt.slice(0,10) };
}
