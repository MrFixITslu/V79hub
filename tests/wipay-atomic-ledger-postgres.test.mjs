import test from "node:test";
import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { spawn } from "node:child_process";
import { Pool } from "pg";
import { PostgresStoreRepository, StoreRevisionConflictError } from "../server/postgres-store.mjs";
import { reconcileWipayInPostgres } from "../server/wipay-atomic-ledger.mjs";
import { createHubStorePersistence } from "../server/runtime-store.mjs";
import { getWipayConfig, createWipayCheckout } from "../server/wipay-provider.mjs";
import { wipayResponseHash } from "../server/billing-contract.mjs";

const databaseUrl = process.env.WIPAY_TEST_DATABASE_URL;
if (!databaseUrl) {
  test("isolated PostgreSQL test is opt-in; no external DB or merchant is contacted", { skip: true }, () => {});
} else {
  const config = getWipayConfig({
    WIPAY_ENABLED: "1", WIPAY_ENV: "live",
    WIPAY_PAYMENT_URL: "https://merchant-checkout.invalid/test-only",
    WIPAY_ACCOUNT_NUMBER: "SYNTHETIC-ACCOUNT-0000",
    WIPAY_API_KEY: "SYNTHETIC-WIPAY-KEY",
    WIPAY_COUNTRY_CODE: "LC", WIPAY_CURRENCY: "XCD",
    WIPAY_RESPONSE_URL: "https://hub.example.test/api/billing/wipay/return",
    V79_BILLING_STATE_SECRET: "synthetic-isolated-32-character-secret-wipay",
  });
  assert.equal(config.ready, true, JSON.stringify(config.problems));
  const order = id => ({
    id, organizationId: "synthetic-org", sourceApp: "hub",
    kind: "subscription", payerEmail: "test@example.com", description: "Synthetic monthly plan",
    amount: 249, currency: "XCD", provider: "wipay",
    providerEnvironment: "live", status: "pending", createdAt: "2026-10-24T14:00:00.000Z",
    updatedAt: "2026-10-24T14:00:00.000Z",
  });
  function queryFor(subject, transactionId, extras = {}) {
    const form = createWipayCheckout({ order: subject, config });
    return {
      order_id: subject.id, status: "success", transaction_id: transactionId,
      total: subject.amount.toFixed(2), currency: subject.currency,
      hash: wipayResponseHash(transactionId, subject.amount.toFixed(2), config.apiKey),
      data: form.fields.data, ...extras,
    };
  }
  function child(storeKey, orderId, query, options = {}) {
    return new Promise((resolve, reject) => {
      const child = spawn(process.execPath, ["tests/wipay-atomic-ledger-child.mjs"], {
        cwd: process.cwd(),
        env: { ...process.env, WIPAY_TEST_DATABASE_URL: databaseUrl },
        stdio: ["pipe", "pipe", "pipe"],
      });
      let out = "", error = "";
      child.stdout.on("data", x => { out += x; });
      child.stderr.on("data", x => { error += x; });
      child.on("error", reject);
      child.on("close", code => {
        if (code !== 0) return reject(new Error("Synthetic child failed with exit " + code + ": " + error));
        try { resolve(JSON.parse(out)); } catch (err) { reject(err); }
      });
      child.stdin.end(JSON.stringify({ storeKey, orderId, query, config, ...options }));
    });
  }
  async function fixture(t, orders) {
    const pool = new Pool({ connectionString: databaseUrl, max: 5 });
    t.after(() => pool.end());
    const key = "wipay_isolated_" + randomUUID();
    const repository = new PostgresStoreRepository(pool, { storeKey: key });
    await repository.ensureSchema();
    const initialized = await repository.initialize({
      billingOrders: orders, billingPaymentEvents: [],
      organizationPlans: [{
        organizationId: "synthetic-org", planName: "Starter", status: "trial",
        billingCycle: "monthly", paidThroughAt: null,
      }],
      auditEvents: [],
    });
    assert.equal(initialized.initialized, true);
    return { repository, key };
  }

  test("real separate Node processes serialize same signed callback: one fulfillment and one already-paid", async t => {
    const a = order("v79_synthetic_a");
    const { repository, key } = await fixture(t, [a]);
    const query = queryFor(a, "LC-SYNTHETIC-TX-1");
    const responses = await Promise.all([
      child(key, a.id, query),
      child(key, a.id, query),
    ]);
    assert.deepEqual(responses.map(r => r.decision).sort(), ["accepted", "already_paid"]);
    const persisted = await repository.load();
    assert.equal(persisted.state.billingOrders[0].status, "paid");
    assert.equal(persisted.state.billingPaymentEvents.length, 1);
    assert.equal(persisted.state.organizationPlans[0].status, "active");
    assert.equal(persisted.state.organizationPlans[0].paidThroughAt, "2026-11-24T14:30:00.000Z");

    // Simulate the process restarting: another separate reader finds the persisted settlement.
    const restarted = await child(key, a.id, query);
    assert.equal(restarted.decision, "already_paid");
    assert.equal((await repository.load()).state.billingPaymentEvents.length, 1);
    // A stale non-transactional writer must fail the existing revision CAS rather than overwrite this payment.
    await assert.rejects(repository.replace(1, { billingOrders: [order(a.id)], billingPaymentEvents: [] }),
      StoreRevisionConflictError);
  });

  test("same signed WiPay transaction cannot settle two separate orders in different processes", async t => {
    const a = order("v79_synthetic_b1"), b = order("v79_synthetic_b2");
    const { repository, key } = await fixture(t, [a, b]);
    const id = "LC-SYNTHETIC-SHARED-TX";
    const results = await Promise.all([
      child(key, a.id, queryFor(a, id)),
      child(key, b.id, queryFor(b, id)),
    ]);
    assert.deepEqual(results.map(r => r.decision).sort(), ["accepted", "reject"]);
    assert.ok(results.some(r => r.reason === "transaction_replay"));
    const saved = (await repository.load()).state;
    assert.equal(saved.billingOrders.filter(o => o.status === "paid").length, 1);
    assert.equal(saved.billingPaymentEvents.length, 1);
  });

  test("invalid browser failure cannot cancel a pending order or set an entitlement", async t => {
    const a = order("v79_synthetic_c");
    const { repository, key } = await fixture(t, [a]);
    const query = queryFor(a, "LC-UNVERIFIED-TX", {
      status: "failed", hash: "00".repeat(16),
    });
    const result = await child(key, a.id, query);
    assert.equal(result.decision, "reject");
    const saved = (await repository.load()).state;
    assert.equal(saved.billingOrders[0].status, "pending");
    assert.equal(saved.billingPaymentEvents.length, 0);
    assert.equal(saved.organizationPlans[0].status, "trial");
  });

  test("failed mutation rolls back order, event, entitlement and permits supervised reconciliation", async t => {
    const a = order("v79_synthetic_d");
    const { repository, key } = await fixture(t, [a]);
    const query = queryFor(a, "LC-SYNTHETIC-ROLLBACK");
    await assert.rejects(
      reconcileWipayInPostgres({
        repository, orderId: a.id, query, config,
        applyEntitlement: () => { throw new Error("synthetic-entitlement-failure"); },
      }), /synthetic-entitlement-failure/,
    );
    let saved = (await repository.load()).state;
    assert.equal(saved.billingOrders[0].status, "pending");
    assert.equal(saved.billingPaymentEvents.length, 0);
    assert.equal(saved.organizationPlans[0].status, "trial");
    const second = await child(key, a.id, query);
    assert.equal(second.decision, "accepted");
    saved = (await repository.load()).state;
    assert.equal(saved.billingOrders[0].status, "paid");
    assert.equal(saved.billingPaymentEvents.length, 1);
  });

  test("abrupt process death mid-transaction rolls back and a new process can safely reconcile", async t => {
    const a = order("v79_synthetic_crash");
    const { repository, key } = await fixture(t, [a]);
    const query = queryFor(a, "LC-SYNTHETIC-CRASH-RECOVER");
    await assert.rejects(child(key, a.id, query, { crashBeforeCommit: true }), /exit 52/);
    const afterCrash = (await repository.load()).state;
    assert.equal(afterCrash.billingOrders[0].status, "pending");
    assert.equal(afterCrash.billingPaymentEvents.length, 0);
    assert.equal(afterCrash.organizationPlans[0].status, "trial");
    const recovered = await child(key, a.id, query);
    assert.equal(recovered.decision, "accepted");
    const repeat = await child(key, a.id, query);
    assert.equal(repeat.decision, "already_paid");
    const final = (await repository.load()).state;
    assert.equal(final.billingPaymentEvents.length, 1);
    assert.equal(final.organizationPlans[0].status, "active");
  });

  test("Hub transactional callback updates revision and blocks an older ordinary Hub writer", async t => {
    const a = order("v79_synthetic_stalewriter");
    const { repository, key } = await fixture(t, [a]);
    const pool = new Pool({ connectionString: databaseUrl, max: 3 });
    t.after(() => pool.end());
    const persistence = createHubStorePersistence({
      backend: "postgres", storeFile: "/unused/synthetic-store.json",
      pool, storeKey: key,
    });
    const olderState = await persistence.load(state => structuredClone(state), () => ({}));
    const competingWriterState = structuredClone(olderState);
    const result = await reconcileWipayInPostgres({
      repository: persistence, orderId: a.id, query: queryFor(a, "LC-STALE-CAS"),
      config, applyEntitlement: (state, paidOrder) => {
        state.organizationPlans[0].status = "active";
        state.organizationPlans[0].paidThroughAt = "2026-11-24T14:30:00.000Z";
      },
    });
    assert.equal(result.result.decision, "accepted");
    assert.equal(persistence.revision(), 2);
    await assert.rejects(persistence.save(competingWriterState), /Stale|revision conflict/);
    const current = (await repository.load()).state;
    assert.equal(current.billingOrders[0].status, "paid");
    assert.equal(current.billingPaymentEvents.length, 1);

    // A second Hub worker loaded revision one: its old ordinary store save
    // must fail the database CAS rather than overwrite that paid state.
    const otherPool = new Pool({ connectionString: databaseUrl, max: 2 });
    t.after(() => otherPool.end());
    const other = createHubStorePersistence({
      backend: "postgres", storeFile: "/unused/synthetic-2.json",
      pool: otherPool, storeKey: key,
    });
    const newer = await other.load(x => structuredClone(x), () => ({}));
    // Server-side revision is 2, so an intentionally old snapshot must have
    // been acquired before another transaction below.
    await repository.transact(next => { next.auditEvents.push({ type: "synthetic-commit" }); });
    await assert.rejects(other.save(newer), /revision conflict|Stale/);
    assert.equal((await repository.load()).state.billingOrders[0].status, "paid");
  });

  test("pending save queued during Hub payment settlement cannot overwrite confirmed funds", async t => {
    const a = order("v79_synthetic_queuedsave");
    const { repository, key } = await fixture(t, [a]);
    const pool = new Pool({ connectionString: databaseUrl, max: 3 });
    t.after(() => pool.end());
    const persistence = createHubStorePersistence({
      backend: "postgres", storeFile: "/unused/synthetic-3.json",
      pool, storeKey: key,
    });
    const initial = await persistence.load(x => structuredClone(x), () => ({}));
    let unblock;
    let transactionEntered;
    const entered = new Promise(resolve => { transactionEntered = resolve; });
    const gate = new Promise(resolve => { unblock = resolve; });
    const payment = persistence.transact(async state => {
      transactionEntered();
      await gate;
      state.billingOrders[0].status = "paid";
      state.billingOrders[0].providerTransactionId = "LC-QUEUED-TEST";
      state.billingPaymentEvents.push({ orderId: a.id, transactionId: "LC-QUEUED-TEST" });
      return { decision: "accepted" };
    });
    await entered;
    // A normal Hub handler captured an out-of-date clone before commit.
    const stale = persistence.save({ ...initial, auditEvents: [{ type: "stale" }] });
    unblock();
    assert.equal((await payment).result.decision, "accepted");
    await assert.rejects(stale, /Stale/);
    const final = (await repository.load()).state;
    assert.equal(final.billingOrders[0].status, "paid");
    assert.equal(final.billingPaymentEvents.length, 1);
    assert.equal(final.auditEvents.length, 0);
  });

  test("invalid payment return remains read-only with no PostgreSQL revision increment", async t => {
    const a = order("v79_synthetic_no_write");
    const { repository, key } = await fixture(t, [a]);
    const q = queryFor(a, "LC-INVALID");
    const outcome = await reconcileWipayInPostgres({
      repository, orderId: a.id,
      query: { ...q, hash: "0".repeat(32) }, config,
    });
    assert.equal(outcome.result.decision, "reject");
    assert.equal(outcome.skipped, true);
    assert.equal(outcome.revision, 1);
    assert.equal((await repository.load()).revision, 1);
  });

  test("environment mismatches fail closed without a stored payment", async t => {
    const a = { ...order("v79_synthetic_e"), providerEnvironment: "sandbox" };
    const { repository, key } = await fixture(t, [a]);
    const result = await child(key, a.id, queryFor({ ...a, providerEnvironment: "live" }, "LC-ENV-MISMATCH"));
    assert.equal(result.decision, "reject");
    assert.equal(result.reason, "environment_mismatch");
    assert.equal((await repository.load()).state.billingOrders[0].status, "pending");
  });
}
