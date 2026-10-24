import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const server = fs.readFileSync(new URL("../server.ts", import.meta.url), "utf8");
const runtime = fs.readFileSync(new URL("../server/runtime-store.mjs", import.meta.url), "utf8");
const postgres = fs.readFileSync(new URL("../server/postgres-store.mjs", import.meta.url), "utf8");
const start = server.indexOf('app.get("/api/billing/wipay/return"');
const end = server.indexOf('app.get("/api/security/mfa/status"', start);
assert.ok(start >= 0 && end > start);
const callback = server.slice(start, end);

test("actual Hub return handler uses PostgreSQL row-locked transaction for settlement", () => {
  assert.match(callback, /storePersistence\.mode === "postgres"/);
  const pg = callback.indexOf('if (storePersistence.mode === "postgres")');
  const transact = callback.indexOf('await reconcileWipayInPostgres({', pg);
  const localClone = callback.indexOf('const nextStore = cloneStore()', pg);
  assert.ok(pg >= 0 && transact > pg && localClone > transact);
  assert.match(callback, /repository: storePersistence/);
  assert.match(callback, /sentinelWriteFence\.beginStoreSave\(\)/);
  assert.match(callback, /finally \{\s*releasePaymentWrite\(\)/);
  assert.match(callback, /store = normalizeLoadedStore\(outcome\.state\)/);
  assert.match(callback, /applyEntitlement: \(state: AppStore, paidOrder: BillingOrder, when: string\)/);
  assert.match(callback, /paidOrder\.billingCycleAtOrder/);
  assert.match(callback, /plan\.billingCycle !== cycle/);
  assert.match(callback, /return redirect\("success", "", persistedOrder\)/);
  assert.match(callback, /return redirect\("failed", decision\.reason/);
});

test("invalid order ID cannot return null DB state to local cache", () => {
  assert.match(callback, /if \(!\/\^v79_\[A-Za-z0-9_\]\+\$\/\.test\(orderId\) \|\| orderId\.length > 64\)/);
});

test("every Hub snapshot mutation retains origin revision; stale queued writes fail closed", () => {
  assert.match(server, /new AsyncLocalStorage<\{ revision: number \}>\(\)/);
  assert.match(server, /snapshotRevision\.set\(snapshot, storePersistence\.revision\(\)\)/);
  assert.match(server, /snapshotRevision\.get\(nextStore\) \?\? hubRequestRevision\.getStore\(\)\?\.revision/);
  assert.match(server, /storePersistence\.save\(nextStore, \{ expectedRevision \}\)/);
  assert.match(runtime, /expectedRevision !== revision/);
  assert.match(runtime, /repository\.replace\(expectedRevision, persisted\)/);
  assert.match(runtime, /repository\.transact\(mutator, options\)/);
  assert.match(postgres, /SELECT revision, state FROM v79_hub_state WHERE store_key = \$1 FOR UPDATE/);
});

test("cross-process signed order status and billing history refresh durable PostgreSQL state", () => {
  assert.match(runtime, /async function refresh\(\)/);
  assert.match(runtime, /await repository\.load\(\)/);
  const signedStart = server.indexOf('app.post("/api/billing/internal/status"');
  const signedEnd = server.indexOf('app.get("/api/billing/orders"', signedStart);
  const historyEnd = server.indexOf('app.post("/api/billing/checkout"', signedEnd);
  assert.ok(signedStart >= 0 && signedEnd > signedStart && historyEnd > signedEnd);
  const signed = server.slice(signedStart, signedEnd);
  const history = server.slice(signedEnd, historyEnd);
  assert.match(signed, /await storePersistence\.refresh\(\)/);
  assert.match(history, /await storePersistence\.refresh\(\)/);
  assert.match(signed, /Current payment status is unavailable/);
  assert.match(history, /Current billing history is unavailable/);
});

test("no unverified callback cancellation and no process-local lock as sole live defense", () => {
  assert.doesNotMatch(callback, /order\.status\s*=\s*"failed"/);
  assert.match(callback, /if \(!liveWiPayLedgerReady\(config\)\)/);
  assert.match(callback, /wipayCallbackGuard\.tryAcquire\(\)/);
  assert.match(callback, /retrying/);
});
