/**
 * Local-only exclusion for the WiPay return handler's read/verify/commit window.
 *
 * Limits: applies to one Node.js process. It does NOT serialize other store
 * writers, coordinate separate Hub instances, replace PostgreSQL revisions,
 * or prove the payment ledger durable after a crash. Live release requires
 * durable/multi-process acceptance independently of these local tests.
 */
export function createWipayCallbackGuard() {
  let active = false;
  return Object.freeze({
    tryAcquire() {
      if (active) return null;
      active = true;
      let released = false;
      return () => {
        if (released) return;
        released = true;
        active = false;
      };
    },
    isBusy() {
      return active;
    },
  });
}

/**
 * Read-only callback decision. Caller must perform it inside the local guard
 * against the latest store snapshot and commit at most once after verification.
 * Any terminal order other than an already verified, matching paid order is
 * denied; a failed/cancelled order is never silently re-opened by a late return.
 */
export function assessWipayCallback({ order, verification, orders }) {
  if (!order || order.provider !== "wipay") {
    return { decision: "reject", reason: "wrong_payment_provider" };
  }
  if (order.status === "paid") {
    const sameVerifiedTransaction = Boolean(
      verification?.ok &&
      verification.transactionId &&
      order.providerTransactionId &&
      verification.transactionId === order.providerTransactionId,
    );
    return sameVerifiedTransaction
      ? { decision: "already_paid", reason: "already_processed" }
      : { decision: "reject", reason: "order_already_paid" };
  }
  if (order.status !== "pending") {
    return { decision: "reject", reason: "order_not_pending" };
  }
  if (!verification?.ok || !verification.transactionId) {
    return { decision: "reject", reason: verification?.reason || "provider_return_invalid" };
  }
  if ((orders || []).some(other =>
    other.id !== order.id &&
    other.provider === "wipay" &&
    other.providerTransactionId === verification.transactionId
  )) {
    return { decision: "reject", reason: "transaction_replay" };
  }
  return { decision: "accept", reason: "verified" };
}
