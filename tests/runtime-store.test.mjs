import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { newDb } from "pg-mem";
import { PostgresStoreRepository, migrateJsonState } from "../server/postgres-store.mjs";
import { createHubStorePersistence } from "../server/runtime-store.mjs";

function normalize(state) {
  return {
    users: Array.isArray(state.users) ? state.users : [],
    organizations: Array.isArray(state.organizations) ? state.organizations : [],
    ownerInvitations: Array.isArray(state.ownerInvitations) ? state.ownerInvitations : [],
  };
}

test("JSON runtime persistence preserves unknown legacy fields and writes atomically", async t => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "v79-runtime-json-"));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const storeFile = path.join(dir, "v79_store.json");
  fs.writeFileSync(storeFile, JSON.stringify({
    legacySetting: { keep: true },
    users: [],
    organizations: [{ id: "org-a" }],
    ownerInvitations: [],
  }));

  const persistence = createHubStorePersistence({ backend: "json", storeFile });
  const loaded = await persistence.load(normalize, () => ({ users: [], organizations: [], ownerInvitations: [] }));
  loaded.ownerInvitations.push({ id: "invite-1" });
  await persistence.save(loaded);

  const disk = JSON.parse(fs.readFileSync(storeFile, "utf8"));
  assert.deepEqual(disk.legacySetting, { keep: true });
  assert.equal(disk.ownerInvitations.length, 1);
  assert.equal(fs.existsSync(storeFile + ".tmp"), false);
});

test("PostgreSQL runtime persistence loads migrated state, advances revisions and never rewrites JSON", async t => {
  const memory = newDb({ autoCreateForeignKeyIndices: true, noAstCoverageCheck: true });
  const adapter = memory.adapters.createPg();
  const pool = new adapter.Pool();
  t.after(() => pool.end());

  const repository = new PostgresStoreRepository(pool);
  await migrateJsonState(repository, {
    legacySetting: { keep: true },
    users: [],
    organizations: [{ id: "org-a" }],
    ownerInvitations: [],
  });

  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "v79-runtime-pg-"));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const storeFile = path.join(dir, "v79_store.json");
  fs.writeFileSync(storeFile, JSON.stringify({ ownerInvitations: [] }));
  const before = fs.readFileSync(storeFile, "utf8");

  const persistence = createHubStorePersistence({ backend: "postgres", storeFile, pool });
  const loaded = await persistence.load(normalize, () => ({ users: [], organizations: [], ownerInvitations: [] }));
  assert.equal(persistence.revision(), 1);
  loaded.ownerInvitations.push({ id: "invite-1" });
  await persistence.save(loaded);
  assert.equal(persistence.revision(), 2);

  const current = await repository.load();
  assert.deepEqual(current.state.legacySetting, { keep: true });
  assert.equal(current.state.ownerInvitations.length, 1);
  assert.equal(fs.readFileSync(storeFile, "utf8"), before);
});

test("PostgreSQL runtime fails closed until the migration has initialized state", async t => {
  const memory = newDb({ autoCreateForeignKeyIndices: true, noAstCoverageCheck: true });
  const adapter = memory.adapters.createPg();
  const pool = new adapter.Pool();
  t.after(() => pool.end());

  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "v79-runtime-empty-"));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const persistence = createHubStorePersistence({
    backend: "postgres",
    storeFile: path.join(dir, "v79_store.json"),
    pool,
  });

  await assert.rejects(
    persistence.load(normalize, () => ({ users: [], organizations: [], ownerInvitations: [] })),
    /Run npm run store:migrate:postgres/i,
  );
});


test("PostgreSQL runtime rejects stale snapshots captured before queued writes", async t => {
  const memory = newDb({ autoCreateForeignKeyIndices: true, noAstCoverageCheck: true });
  const adapter = memory.adapters.createPg();
  const pool = new adapter.Pool();
  t.after(() => pool.end());

  const repository = new PostgresStoreRepository(pool);
  await migrateJsonState(repository, {
    users: [],
    organizations: [],
    ownerInvitations: [],
  });

  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "v79-runtime-stale-"));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const persistence = createHubStorePersistence({
    backend: "postgres",
    storeFile: path.join(dir, "unused.json"),
    pool,
  });

  const loaded = await persistence.load(normalize, () => ({}));
  const first = persistence.save({
    ...loaded,
    ownerInvitations: [{ id: "first" }],
  });
  const stale = persistence.save({
    ...loaded,
    users: [{ id: "stale-user" }],
  });

  await first;
  await assert.rejects(stale, /revision conflict/i);

  const current = await repository.load();
  assert.equal(current.revision, 2);
  assert.deepEqual(current.state.ownerInvitations, [{ id: "first" }]);
  assert.deepEqual(current.state.users, []);
  assert.equal(persistence.revision(), 2);
});

test("PostgreSQL runtime serialises rename with saves and rejects an older queued snapshot", async t => {
  const memory = newDb({ autoCreateForeignKeyIndices: true, noAstCoverageCheck: true });
  const adapter = memory.adapters.createPg();
  const pool = new adapter.Pool();
  t.after(() => pool.end());

  const repository = new PostgresStoreRepository(pool);
  await migrateJsonState(repository, {
    users: [],
    organizations: [{ id: "org-a", name: "Old Name" }],
    ownerInvitations: [],
    auditEvents: [],
  });

  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "v79-runtime-rename-"));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const persistence = createHubStorePersistence({
    backend: "postgres",
    storeFile: path.join(dir, "unused.json"),
    pool,
  });

  const loaded = await persistence.load(normalize, () => ({}));

  const first = persistence.save({
    ...loaded,
    ownerInvitations: [{ id: "preserved-invite" }],
  });

  const rename = persistence.renameOrganizationWithOutbox({
    organizationId: "org-a",
    name: "New Name",
    eventId: "runtime-rename-1",
    auditEvent: { id: "audit-runtime-1", action: "organization.name.changed" },
  });

  const stale = persistence.save({
    ...loaded,
    ownerInvitations: [{ id: "stale-invite" }],
  });

  await first;
  const renamed = await rename;
  assert.equal(renamed.applied, true);
  assert.equal(renamed.state.organizations[0].name, "New Name");
  assert.equal(persistence.revision(), 3);

  await assert.rejects(stale, /revision conflict/i);

  const current = await repository.load();
  assert.equal(current.revision, 3);
  assert.equal(current.state.organizations[0].name, "New Name");
  assert.deepEqual(current.state.ownerInvitations, [{ id: "preserved-invite" }]);
  assert.equal(current.state.auditEvents.length, 1);
});
