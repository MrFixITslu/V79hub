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
