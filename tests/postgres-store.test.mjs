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

test("migration rejects a non-object JSON source", async t => {
  const repository = await repositoryFixture(t);
  await assert.rejects(
    migrateJsonState(repository, []),
    /migration source must be an object/i,
  );
});
