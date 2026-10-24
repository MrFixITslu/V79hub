// Disposable separate Node process for a real PostgreSQL concurrent callback test.
// Reads synthetic JSON from stdin; no WiPay endpoint, no production connection.
import { Pool } from "pg";
import { PostgresStoreRepository } from "../server/postgres-store.mjs";
import { reconcileWipayInPostgres } from "../server/wipay-atomic-ledger.mjs";

let raw = "";
for await (const chunk of process.stdin) raw += chunk;
const input = JSON.parse(raw);
const pool = new Pool({ connectionString: process.env.WIPAY_TEST_DATABASE_URL, max: 2 });
try {
  const repository = new PostgresStoreRepository(pool, { storeKey: input.storeKey });
  const result = await reconcileWipayInPostgres({
    repository,
    orderId: input.orderId,
    query: input.query,
    config: input.config,
    now: () => "2026-10-24T14:30:00.000Z",
    applyEntitlement: (state, order) => {
      // Synthetic crash injection: terminate mid-transaction after the order has
      // been marked paid in the uncommitted snapshot; PostgreSQL must roll back.
      if (input.crashBeforeCommit === true) process.exit(52);
      if (order.kind === "subscription") {
        const plan = state.organizationPlans.find(item => item.organizationId === order.organizationId);
        if (!plan) throw new Error("Missing matching organization plan");
        plan.status = "active";
        plan.paidThroughAt = "2026-11-24T14:30:00.000Z";
        plan.updatedAt = "2026-10-24T14:30:00.000Z";
      }
    },
  });
  process.stdout.write(JSON.stringify({ decision: result.result.decision, reason: result.result.reason }));
} catch (err) {
  process.stderr.write("Transaction failed: " + err.name + "\n");
  process.exitCode = 1;
} finally {
  await pool.end();
}
