import crypto from "node:crypto";
import { verifyWipayReturn } from "./wipay-provider.mjs";
import { assessWipayCallback } from "./wipay-callback-guard.mjs";

/**
 * Transactional WiPay reconciliation against the persisted Hub state.
 *
 * Requires PostgresStoreRepository.transact (SELECT ... FOR UPDATE). Never
 * accept an unauthenticated browser return as permission to change a pending
 * order to failed. The optional applyEntitlement function must be synchronous,
 * modify only the supplied transaction state, and perform no external I/O.
 *
 * This is an isolated integration building block until the HTTP handler and
 * ALL competing store writers are reconciled and tested together.
 */
export async function reconcileWipayInPostgres({
  repository,
  orderId,
  query,
  config,
  now = () => new Date().toISOString(),
  applyEntitlement = (_state, _order, _when) => {},
} = {}) {
  if (!repository || typeof repository.transact !== "function") {
    throw new Error("A transactional PostgreSQL repository is required.");
  }
  if (config?.environment !== "live" && config?.environment !== "sandbox") {
    throw new Error("Explicit WiPay environment is required.");
  }
  if (!/^[a-zA-Z0-9_]{1,64}$/.test(String(orderId || "")) ||
      String(query?.order_id || "") !== orderId) {
    return { result: { decision: "reject", reason: "order_mismatch" }, state: null };
  }

  return repository.transact(state => {
    if (!Array.isArray(state.billingOrders) || !Array.isArray(state.billingPaymentEvents)) {
      throw new Error("Hub billing ledger is missing.");
    }
    const order = state.billingOrders.find(item => item.id === orderId);
    if (!order || order.provider !== "wipay") {
      return { decision: "reject", reason: "order_not_found" };
    }
    const verified = verifyWipayReturn({ query, expectedOrder: order, config });
    const check = assessWipayCallback({ order, verification: verified, orders: state.billingOrders });
    if (check.decision !== "accept") {
      // No modifications for invalid/replayed/terminal callbacks. Verification
      // failures are surfaced but never cancel a pending order.
      return { decision: check.decision, reason: check.reason, orderId: order.id };
    }
    const time = now();
    if (typeof time !== "string" || !Number.isFinite(Date.parse(time))) {
      throw new Error("Invalid payment timestamp.");
    }
    order.status = "paid";
    order.providerTransactionId = verified.transactionId;
    order.providerMessage = verified.message || "WiPay payment verified";
    order.paidAt = time;
    order.updatedAt = time;
    if (order.providerEnvironment === "live") {
      const effect = applyEntitlement(state, order, time);
      if (effect && typeof effect.then === "function") {
        throw new Error("Financial entitlement mutation must be synchronous.");
      }
    }
    state.billingPaymentEvents.push({
      id: crypto.randomUUID(),
      provider: "wipay",
      orderId: order.id,
      transactionId: verified.transactionId,
      status: "success",
      verified: true,
      reason: "verified",
      amount: verified.amount,
      currency: verified.currency,
      createdAt: time,
    });
    if (state.billingPaymentEvents.length > 5000) {
      state.billingPaymentEvents = state.billingPaymentEvents.slice(-5000);
    }
    return { decision: "accepted", reason: "verified", orderId: order.id,
      providerEnvironment: order.providerEnvironment };
  }, { skipWriteWhen: result => result?.decision !== "accepted" });
}
