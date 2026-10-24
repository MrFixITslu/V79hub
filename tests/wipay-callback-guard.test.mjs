import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { assessWipayCallback, createWipayCallbackGuard, liveWipayStoreSupported } from "../server/wipay-callback-guard.mjs";

const pending = (id, status = "pending") => ({
  id, provider: "wipay", status, providerEnvironment: "sandbox", currency: "TTD", amount: 10,
});
const valid = (transactionId = "SB-SYNTHETIC-123") => ({ ok: true, transactionId, reason: "verified" });

test("live merchant order/return is blocked on JSON persistence; sandbox remains available", () => {
  assert.equal(liveWipayStoreSupported("live", "json"), false);
  assert.equal(liveWipayStoreSupported("live", "postgres"), true);
  assert.equal(liveWipayStoreSupported("sandbox", "json"), true);
  assert.equal(liveWipayStoreSupported("sandbox", "postgres"), true);
});

test("two simultaneous callbacks cannot both enter one process read-to-commit window", async () => {
  const guard = createWipayCallbackGuard();
  const release = guard.tryAcquire();
  assert.equal(typeof release, "function");
  assert.equal(guard.isBusy(), true);
  assert.equal(guard.tryAcquire(), null, "second callback must fail closed with no snapshot");
  release();
  release(); // safe cleanup even if two error paths call finally
  assert.equal(guard.isBusy(), false);
  const retryRelease = guard.tryAcquire();
  assert.equal(typeof retryRelease, "function");
  retryRelease();
});

test("concurrent duplicate, replay to another order and failed commits do not create duplicate paid records", async () => {
  const guard = createWipayCallbackGuard();
  const ledger = [pending("v79_a"), pending("v79_b")];
  const events = [];
  let openCommit;
  const commitGate = new Promise(resolve => { openCommit = resolve; });

  async function process(id, verifier, beforeCommit = Promise.resolve(), fail = false) {
    const release = guard.tryAcquire();
    if (!release) return "busy"; // actual route returns HTTP 503 Retry-After
    try {
      const snapshot = structuredClone(ledger);
      const order = snapshot.find(x => x.id === id);
      const assessment = assessWipayCallback({ order, verification: verifier, orders: snapshot });
      if (assessment.decision !== "accept") return assessment.decision + ":" + assessment.reason;
      await beforeCommit;
      if (fail) throw new Error("simulated storage error");
      order.status = "paid";
      order.providerTransactionId = verifier.transactionId;
      ledger.splice(0, ledger.length, ...snapshot);
      events.push({ orderId: id, transactionId: verifier.transactionId });
      return "paid";
    } catch {
      return "uncertain_no_success";
    } finally {
      release();
    }
  }

  const one = process("v79_a", valid(), commitGate);
  assert.equal(await process("v79_a", valid()), "busy");
  assert.equal(await process("v79_b", valid()), "busy");
  assert.equal(events.length, 0);
  openCommit();
  assert.equal(await one, "paid");
  assert.equal(await process("v79_a", valid()), "already_paid:already_processed");
  assert.equal(await process("v79_a", { ok: false, transactionId: valid().transactionId }), "reject:order_already_paid");
  assert.equal(await process("v79_b", valid()), "reject:transaction_replay");
  assert.deepEqual(events, [{ orderId: "v79_a", transactionId: valid().transactionId }]);
  assert.equal(ledger.find(x => x.id === "v79_b").status, "pending");

  assert.equal(await process("v79_b", valid("SB-OTHER"), Promise.resolve(), true), "uncertain_no_success");
  assert.equal(guard.isBusy(), false);
  assert.equal(ledger.find(x => x.id === "v79_b").status, "pending", "unsaved clone must not grant access");
  assert.equal(await process("v79_b", valid("SB-OTHER")), "paid");
  assert.equal(events.length, 2);
});

test("cancelled/failed orders cannot be re-opened; paid return requires a valid verified signature", () => {
  const orders = [pending("v79_paid", "paid"), pending("v79_cancelled", "cancelled"), pending("v79_failed", "failed")];
  orders[0].providerTransactionId = "TX-VALID";
  assert.deepEqual(assessWipayCallback({ order: orders[0], verification: valid("TX-VALID"), orders }).decision, "already_paid");
  assert.equal(assessWipayCallback({ order: orders[0], verification: { ok: false, transactionId: "TX-VALID" }, orders }).decision, "reject");
  assert.equal(assessWipayCallback({ order: orders[0], verification: valid("TX-FOREIGN"), orders }).decision, "reject");
  for (const order of orders.slice(1)) {
    assert.deepEqual(assessWipayCallback({ order, verification: valid("TX-NEW"), orders }), {
      decision: "reject", reason: "order_not_pending",
    });
  }
});

test("Hub handler acquires guard before snapshot, returns 503 while busy, and releases on every outcome", () => {
  const source = fs.readFileSync(new URL("../server.ts", import.meta.url), "utf8");
  const first = source.indexOf('app.get("/api/billing/wipay/return"');
  const last = source.indexOf('app.get("/api/security/mfa/status"', first);
  assert.ok(first > 0 && last > first);
  const callback = source.slice(first, last);
  assert.match(callback, /if \(!liveWiPayLedgerReady\(config\)\)/);
  assert.ok(callback.indexOf("wipayCallbackGuard.tryAcquire()") < callback.indexOf("const nextStore = cloneStore()"));
  assert.match(callback, /return res\.status\(503\)\.send\(/);
  assert.match(callback, /assessWipayCallback\(\{ order, verification, orders:/);
  assert.match(callback, /catch \{[\s\S]*?Payment status is uncertain/);
  assert.match(callback, /finally \{\s*releaseCallback\(\)/);
  assert.doesNotMatch(callback, /return redirect\(sameTransaction \? "success"/);
});
