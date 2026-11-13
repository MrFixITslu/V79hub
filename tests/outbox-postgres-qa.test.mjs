import test from "node:test";
import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import pg from "pg";
import { PostgresStoreRepository } from "../server/postgres-store.mjs";

if (!process.env.V79_OUTBOX_QA_URL) {
  throw new Error("Isolated QA PostgreSQL URL is required.");
}

const pool = new pg.Pool({
  connectionString: process.env.V79_OUTBOX_QA_URL,
  max: 6,
});
test.after(async () => pool.end());

async function setup(destinations = ["tiquet", "pos"]) {
  const repo = new PostgresStoreRepository(pool, {
    storeKey: randomUUID(),
  });
  await repo.ensureSchema();
  await repo.initialize({
    organizations: [{ id: "org-a", name: "Old Name" }],
    auditEvents: [],
  });

  await repo.renameOrganizationWithOutbox({
    organizationId: "org-a",
    name: "New Name",
    eventId: randomUUID(),
    auditEvent: { id: randomUUID(), type: "organization.name.changed" },
    destinations,
  });
  return repo;
}

test("Tiquet failure does not block POS delivery", async () => {
  const repo = await setup();
  const pos = await repo.claimOrganizationNameDelivery("pos");
  const tiquet = await repo.claimOrganizationNameDelivery("tiquet");

  assert.ok(pos);
  assert.ok(tiquet);
  assert.notEqual(pos.id, tiquet.id);

  await repo.markOrganizationNameDelivered({
    id: pos.id, leaseToken: pos.leaseToken,
  });
  assert.equal(await repo.claimOrganizationNameDelivery("pos"), null);

  assert.equal(await repo.markOrganizationNameFailed({
    id: tiquet.id,
    leaseToken: tiquet.leaseToken,
    attempts: tiquet.attempts,
    error: "Tiquet unavailable",
  }), "pending");

  await pool.query(
    `UPDATE v79_hub_organization_name_outbox
     SET next_attempt_at = NOW() - INTERVAL '1 second'
     WHERE id = $1`,
    [tiquet.id],
  );

  const retry = await repo.claimOrganizationNameDelivery("tiquet");
  assert.ok(retry);
  assert.equal(retry.attempts, 2);
  assert.notEqual(retry.leaseToken, tiquet.leaseToken);

  await repo.markOrganizationNameDelivered({
    id: retry.id, leaseToken: retry.leaseToken,
  });

  const rows = await pool.query(
    `SELECT destination, status
     FROM v79_hub_organization_name_outbox
     WHERE id = ANY($1::text[])`,
    [[pos.id, tiquet.id]],
  );
  assert.equal(rows.rowCount, 2);
  assert.ok(rows.rows.every(row => row.status === "delivered"));
});

test("expired lease rejects old worker acknowledgement", async () => {
  const repo = await setup(["pos"]);
  const first = await repo.claimOrganizationNameDelivery("pos");
  assert.ok(first);

  await pool.query(
    `UPDATE v79_hub_organization_name_outbox
     SET lease_until = NOW() - INTERVAL '1 second'
     WHERE id = $1`,
    [first.id],
  );

  const second = await repo.claimOrganizationNameDelivery("pos");
  assert.ok(second);
  assert.notEqual(first.leaseToken, second.leaseToken);

  await assert.rejects(
    repo.markOrganizationNameDelivered({
      id: first.id, leaseToken: first.leaseToken,
    }),
    /lease lost/i,
  );

  await repo.markOrganizationNameDelivered({
    id: second.id, leaseToken: second.leaseToken,
  });
});

test("maximum failed attempts produce a dead letter", async () => {
  const repo = await setup(["pos"]);

  for (let attempt = 1; attempt <= 2; attempt++) {
    const job = await repo.claimOrganizationNameDelivery("pos", {
      maxAttempts: 2,
    });
    assert.ok(job);
    assert.equal(job.attempts, attempt);

    const status = await repo.markOrganizationNameFailed({
      id: job.id,
      leaseToken: job.leaseToken,
      attempts: job.attempts,
      error: "Destination offline",
      maxAttempts: 2,
    });
    assert.equal(status, attempt === 2 ? "dead_letter" : "pending");

    if (attempt === 1) {
      await pool.query(
        `UPDATE v79_hub_organization_name_outbox
         SET next_attempt_at = NOW() - INTERVAL '1 second'
         WHERE id = $1`,
        [job.id],
      );
    }
  }

  assert.equal(
    await repo.claimOrganizationNameDelivery("pos", { maxAttempts: 2 }),
    null,
  );
});

test("concurrent workers cannot claim the same delivery", async () => {
  const repo = await setup(["pos"]);
  const claims = await Promise.all([
    repo.claimOrganizationNameDelivery("pos"),
    repo.claimOrganizationNameDelivery("pos"),
  ]);

  const claimed = claims.filter(Boolean);
  assert.equal(claimed.length, 1);

  await repo.markOrganizationNameDelivered({
    id: claimed[0].id,
    leaseToken: claimed[0].leaseToken,
  });
});
