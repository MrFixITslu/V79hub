import fs from "node:fs";
import { Pool } from "pg";
import { PostgresStoreRepository } from "./postgres-store.mjs";

export function createHubStorePersistence({
  backend = "json",
  storeFile,
  databaseUrl = "",
  pool = null,
  storeKey = "main",
} = {}) {
  const mode = String(backend || "json").trim().toLowerCase();
  if (!["json", "postgres"].includes(mode)) {
    throw new Error("V79_HUB_STORE_BACKEND must be json or postgres.");
  }
  if (!storeFile) throw new Error("Hub store file path is required.");
  if (mode === "postgres" && !pool && !String(databaseUrl || "").trim()) {
    throw new Error("DATABASE_URL is required when V79_HUB_STORE_BACKEND=postgres.");
  }

  const activePool = mode === "postgres"
    ? (pool || new Pool({ connectionString: String(databaseUrl) }))
    : null;
  const ownsPool = Boolean(activePool && !pool);
  const repository = activePool ? new PostgresStoreRepository(activePool, { storeKey }) : null;
  let revision = 0;
  let envelope = {};
  let persistChain = Promise.resolve();

  async function load(normalize, initialFactory) {
    if (typeof normalize !== "function" || typeof initialFactory !== "function") {
      throw new Error("Hub store load requires normalize and initial state functions.");
    }

    if (mode === "postgres") {
      await repository.ensureSchema();
      const current = await repository.load();
      if (!current) {
        throw new Error("Hub PostgreSQL store is empty. Run npm run store:migrate:postgres before enabling the PostgreSQL backend.");
      }
      revision = current.revision;
      envelope = current.state && typeof current.state === "object" && !Array.isArray(current.state)
        ? current.state
        : {};
      return normalize(envelope);
    }

    if (fs.existsSync(storeFile)) {
      let parsed;
      try {
        parsed = JSON.parse(fs.readFileSync(storeFile, "utf8"));
      } catch (error) {
        throw new Error(`Unable to read existing Hub data at ${storeFile}; restore from backup instead of replacing it.`, { cause: error });
      }
      envelope = parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
      return normalize(parsed);
    }

    const initial = initialFactory();
    await save(initial);
    return initial;
  }

  async function save(nextStore) {
    const snapshot = structuredClone(nextStore);
    // Capture revision BEFORE queueing: a concurrent payment transaction must
    // not be overwritten by an older caller snapshot queued behind it.
    const expectedRevision = revision;
    persistChain = persistChain.catch(() => {}).then(async () => {
      const persisted = { ...envelope, ...snapshot };
      if (mode === "postgres") {
        if (expectedRevision !== revision) {
          throw new Error("Stale Hub store snapshot; reload and reconcile before retrying.");
        }
        const updated = await repository.replace(expectedRevision, persisted);
        revision = updated.revision;
        envelope = updated.state;
        return;
      }

      const tempFile = storeFile + ".tmp";
      fs.writeFileSync(tempFile, JSON.stringify(persisted, null, 2), { encoding: "utf8", mode: 0o600 });
      fs.renameSync(tempFile, storeFile);
      fs.chmodSync(storeFile, 0o600);
      envelope = persisted;
    });
    return persistChain;
  }

  async function transact(mutator, options = {}) {
    if (mode !== "postgres" || !repository) throw new Error("PostgreSQL transactions are required.");
    if (typeof mutator !== "function") throw new TypeError("Hub transaction requires a mutator.");
    // Serialize with normal Hub saves in THIS process. Separate instances
    // remain protected by the PostgreSQL row lock and revision/CAS.
    persistChain = persistChain.catch(() => {}).then(async () => {
      // A previously queued save (or another process) may have advanced the
      // revision; repository transaction always reads the latest DB row.
      const outcome = await repository.transact(mutator, options);
      revision = outcome.revision;
      envelope = outcome.state;
      return outcome;
    });
    return persistChain;
  }

  async function close() {
    await persistChain.catch(() => {});
    if (ownsPool) await activePool.end();
  }

  return {
    mode,
    load,
    save,
    transact,
    close,
    revision: () => revision,
    envelope: () => structuredClone(envelope),
  };
}
