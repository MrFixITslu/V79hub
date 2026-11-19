import fs from "node:fs";
import { Pool } from "pg";
import { PostgresStoreRepository } from "./postgres-store.mjs";

export function createHubStorePersistence({
  backend = "json",
  storeFile,
  databaseUrl = "",
  pool = null,
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
  const repository = activePool ? new PostgresStoreRepository(activePool) : null;
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

  /**
   * @template T
   * @param {() => Promise<T>} task
   * @returns {Promise<T>}
   */
  function enqueuePersistence(task) {
    const operation = persistChain.catch(() => {}).then(task);
    persistChain = operation.then(() => {}, () => {});
    return operation;
  }

  function save(nextStore) {
    const snapshot = structuredClone(nextStore);
    const expectedRevision = revision;

    return enqueuePersistence(async () => {
      const persisted = { ...envelope, ...snapshot };

      if (mode === "postgres") {
        const updated = await repository.replace(expectedRevision, persisted);
        revision = updated.revision;
        envelope = structuredClone(updated.state);
        return structuredClone(updated.state);
      }

      const tempFile = storeFile + ".tmp";
      fs.writeFileSync(tempFile, JSON.stringify(persisted, null, 2), { encoding: "utf8", mode: 0o600 });
      fs.renameSync(tempFile, storeFile);
      fs.chmodSync(storeFile, 0o600);
      envelope = persisted;
      return structuredClone(persisted);
    });
  }

  function renameOrganizationWithOutbox(input) {
    if (mode !== "postgres") {
      throw new Error("Organisation rename outbox requires the PostgreSQL backend.");
    }

    return enqueuePersistence(async () => {
      const result = await repository.renameOrganizationWithOutbox(input);
      revision = result.revision;
      envelope = structuredClone(result.state);
      return {
        ...result,
        state: structuredClone(result.state),
      };
    });
  }

  async function close() {
    await persistChain.catch(() => {});
    if (ownsPool) await activePool.end();
  }

  return {
    mode,
    load,
    save,
    renameOrganizationWithOutbox,
    deliveryRepository: repository,
    close,
    revision: () => revision,
    envelope: () => structuredClone(envelope),
  };
}
