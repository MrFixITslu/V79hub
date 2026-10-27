import fs from "node:fs/promises";
import path from "node:path";
import { createHmac, timingSafeEqual } from "node:crypto";
import { Pool } from "pg";
import { PostgresStoreRepository } from "./postgres-store.mjs";
import { initialWorkState } from "./workforce-actions.mjs";

// A separate transactional ledger avoids whole-Hub stale snapshot overwrites.
// All state, payloads, approvals and receipts are authenticated together.
export function createWorkActionStore({ file, secret, backend = "json", databaseUrl = "", pool = null }) {
  const key = String(secret || "");
  if (key.length < 32) throw new Error("Workforce audit key requires at least 32 characters");
  if (!["json", "postgres"].includes(backend)) throw new Error("Invalid workforce store backend");
  // PostgreSQL JSONB reorders object keys. Authenticate semantic JSON rather
  // than JavaScript insertion order, including every nested payload/receipt.
  const canonical = state => JSON.stringify(state, (_key, value) => value && typeof value === "object" && !Array.isArray(value)
    ? Object.fromEntries(Object.keys(value).sort().map(k => [k, value[k]])) : value);
  const mac = state => createHmac("sha256", key).update(canonical(state)).digest("hex");
  const seal = state => ({ state, mac: mac(state) });
  function open(envelope) {
    if (!envelope?.state || !/^[a-f0-9]{64}$/.test(envelope.mac || "") ||
        !timingSafeEqual(Buffer.from(mac(envelope.state)), Buffer.from(envelope.mac))) throw new Error("Workforce ledger integrity failure");
    const s = envelope.state;
    if (s.version !== 1 || typeof s.paused !== "boolean" || ![s.jobs, s.tasks, s.events].every(Array.isArray)) throw new Error("Malformed workforce ledger");
    return structuredClone(s);
  }
  const activePool = backend === "postgres" ? (pool || new Pool({ connectionString: databaseUrl })) : null;
  const repo = activePool ? new PostgresStoreRepository(activePool, { storeKey: "workforce-actions-v1" }) : null;
  let ready;
  async function pgReady() {
    ready ??= (async () => { await repo.ensureSchema(); await repo.initialize(seal(initialWorkState())); })();
    await ready;
  }
  async function fileRead() {
    try { return open(JSON.parse(await fs.readFile(file, "utf8"))); }
    catch (e) { if (e.code === "ENOENT") return initialWorkState(); throw e; }
  }
  async function transact(fn) {
    if (repo) {
      await pgReady();
      const updated = await repo.transact(async envelope => {
        const state = open(envelope), result = await fn(state);
        Object.assign(envelope, seal(state)); return structuredClone(result);
      });
      return updated.result;
    }
    await fs.mkdir(path.dirname(file), { recursive: true, mode: 0o700 });
    // No expiry-based lock stealing: an interrupted writer stops execution
    // until an operator verifies no active process and removes the lock.
    const lock = file + ".lock";
    await fs.mkdir(lock, { mode: 0o700 });
    try {
      const state = await fileRead(), result = await fn(state);
      const temp = file + ".tmp";
      await fs.writeFile(temp, JSON.stringify(seal(state)), { mode: 0o600 });
      const handle = await fs.open(temp, "r+");
      try { await handle.sync(); } finally { await handle.close(); }
      await fs.rename(temp, file);
      const parent = await fs.open(path.dirname(file), "r");
      try { await parent.sync(); } finally { await parent.close(); }
      return structuredClone(result);
    } finally { await fs.rmdir(lock); }
  }
  async function read() {
    if (repo) {
      // Opening a status panel must not initialize or migrate persisted data.
      const current = await repo.load();
      return current ? open(current.state) : initialWorkState();
    }
    return fileRead();
  }
  async function readAuthenticatedSnapshot() {
    if (repo) {
      const current = await repo.load();
      return current ? open(current.state) : null;
    }
    try { return open(JSON.parse(await fs.readFile(file, "utf8"))); }
    catch (e) { if (e.code === "ENOENT") return null; throw e; }
  }
  return { transact, read, readAuthenticatedSnapshot, close: async () => { if (activePool && !pool) await activePool.end(); } };
}
