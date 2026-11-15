import test from "node:test";
import assert from "node:assert/strict";
import { newDb } from "pg-mem";
import {
  PostgresStoreRepository,
  StoreRevisionConflictError,
  migrateJsonState,
} from "../server/postgres-store.mjs";

async function repositoryFixture(t) {
  const memory = newDb({ autoCreateForeignKeyIndices: true, noAstCoverageCheck: true });
  const adapter = memory.adapters.createPg();
  const pool = new adapter.Pool();
  t.after(() => pool.end());
  const repository = new PostgresStoreRepository(pool);
  await repository.ensureSchema();
  return repository;
}

test("PostgreSQL store initializes once and preserves JSON state", async t => {
  const repository = await repositoryFixture(t);
  const state = { organizations: [{ id: "org-a" }], memberships: [] };
  const first = await migrateJsonState(repository, state);
  assert.equal(first.imported, true);
  assert.equal(first.current.revision, 1);
  assert.deepEqual(first.current.state, state);
  state.organizations[0].id = "mutated-outside";
  const loaded = await repository.load();
  assert.equal(loaded.state.organizations[0].id, "org-a");

  const second = await migrateJsonState(repository, { organizations: [{ id: "org-b" }] });
  assert.equal(second.imported, false);
  assert.equal(second.current.revision, 1);
  assert.equal(second.current.state.organizations[0].id, "org-a");
});

test("revisioned replacement rejects stale writers", async t => {
  const repository = await repositoryFixture(t);
  await repository.initialize({ value: 1 });

  const current = await repository.load();
  const updated = await repository.replace(current.revision, { value: 2 });
  assert.equal(updated.revision, 2);
  assert.deepEqual(updated.state, { value: 2 });

  await assert.rejects(
    repository.replace(current.revision, { value: 99 }),
    error => {
      assert.equal(error instanceof StoreRevisionConflictError, true);
      assert.equal(error.expected, 1);
      assert.equal(error.actual, 2);
      return true;
    },
  );

  const finalState = await repository.load();
  assert.equal(finalState.revision, 2);
  assert.deepEqual(finalState.state, { value: 2 });
});

test("transaction mutates one locked state revision atomically", async t => {
  const repository = await repositoryFixture(t);
  await repository.initialize({ auditEvents: [], counter: 0 });

  const committed = await repository.transact(state => {
    state.counter += 1;
    state.auditEvents.push({ type: "increment" });
    return { applied: true };
  });

  assert.equal(committed.revision, 2);
  assert.deepEqual(committed.result, { applied: true });
  assert.equal(committed.state.counter, 1);
  assert.deepEqual(committed.state.auditEvents, [{ type: "increment" }]);

  const loaded = await repository.load();
  assert.equal(loaded.revision, 2);
  assert.equal(loaded.state.counter, 1);
});

test("organisation rename and independent delivery records commit atomically", async t => {
  const repository = await repositoryFixture(t);
  await repository.initialize({
    organizations: [{ id: "org-a", name: "Old Name" }],
    auditEvents: [],
  });

  const input = {
    organizationId: "org-a",
    name: "New Name",
    eventId: "rename-event-1",
    auditEvent: { id: "audit-1", action: "organization.name.changed" },
    destinations: ["tiquet", "pos"],
  };

  const result = await repository.renameOrganizationWithOutbox(input);
  assert.equal(result.applied, true);
  assert.equal(result.duplicate, false);
  assert.equal(result.revision, 2);
  assert.equal(result.state.organizations[0].name, "New Name");
  assert.equal(result.state.organizations[0].nameRevision, 2);
  assert.equal(result.state.auditEvents.length, 1);

  const queued = await repository.pool.query(
    "SELECT destination, status, name_revision FROM v79_hub_organization_name_outbox ORDER BY destination",
  );
  assert.equal(queued.rowCount, 2);
  assert.deepEqual(queued.rows.map(row => row.destination), ["pos", "tiquet"]);
  assert.ok(queued.rows.every(row => row.status === "pending"));
  assert.ok(queued.rows.every(row => Number(row.name_revision) === 2));

  const duplicate = await repository.renameOrganizationWithOutbox(input);
  assert.equal(duplicate.applied, false);
  assert.equal(duplicate.duplicate, true);
  assert.equal(duplicate.revision, 2);

  // Same event ID with altered data must never be accepted.
  for (const changed of [
    { ...input, name: "Tampered Name" },
    { ...input, auditEvent: { id: "different-audit" } },
    { ...input, destinations: ["tiquet"] },
  ]) {
    await assert.rejects(
      repository.renameOrganizationWithOutbox(changed),
      /event ID was reused with different data/,
    );
  }

  // A legacy row without a request hash must fail closed.
  await repository.pool.query(
    `UPDATE v79_hub_organization_name_outbox
     SET request_hash = NULL
     WHERE event_id = $1 AND destination = $2`,
    [input.eventId, "pos"],
  );
  await assert.rejects(
    repository.renameOrganizationWithOutbox(input),
    /event ID was reused with different data/,
  );

  const finalState = await repository.load();
  assert.equal(finalState.state.organizations[0].name, "New Name");
  assert.equal(finalState.state.auditEvents.length, 1);

  const finalQueue = await repository.pool.query(
    "SELECT id FROM v79_hub_organization_name_outbox",
  );
  assert.equal(finalQueue.rowCount, 2);
});

test("organisation rename rolls back state and queue when organisation is missing", async t => {
  const repository = await repositoryFixture(t);
  await repository.initialize({ organizations: [], auditEvents: [] });

  await assert.rejects(
    repository.renameOrganizationWithOutbox({
      organizationId: "missing",
      name: "New Name",
      eventId: "rename-event-missing",
      auditEvent: { id: "audit-missing" },
    }),
    /Organisation was not found/,
  );

  const current = await repository.load();
  assert.equal(current.revision, 1);
  assert.deepEqual(current.state.organizations, []);

  const queued = await repository.pool.query(
    "SELECT id FROM v79_hub_organization_name_outbox",
  );
  assert.equal(queued.rowCount, 0);
});

test("migration rejects a non-object JSON source", async t => {
  const repository = await repositoryFixture(t);
  await assert.rejects(
    migrateJsonState(repository, []),
    /migration source must be an object/i,
  );
});
