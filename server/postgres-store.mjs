export class StoreRevisionConflictError extends Error {
  constructor(expected, actual) {
    super(`Hub store revision conflict: expected ${expected}, found ${actual}.`);
    this.name = "StoreRevisionConflictError";
    this.expected = expected;
    this.actual = actual;
  }
}

export class PostgresStoreRepository {
  constructor(pool, { storeKey = "main" } = {}) {
    this.pool = pool;
    this.storeKey = storeKey;
  }

  async ensureSchema() {
    await this.pool.query(`
      CREATE TABLE IF NOT EXISTS v79_hub_state (
        store_key TEXT PRIMARY KEY,
        revision BIGINT NOT NULL CHECK (revision > 0),
        state JSONB NOT NULL,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
      )
    `);
  }
  async load() {
    const result = await this.pool.query(
      "SELECT revision, state, updated_at FROM v79_hub_state WHERE store_key = $1",
      [this.storeKey],
    );
    if (!result.rowCount) return null;
    const row = result.rows[0];
    return {
      revision: Number(row.revision),
      state: structuredClone(row.state),
      updatedAt: new Date(row.updated_at).toISOString(),
    };
  }

  async initialize(state) {
    const result = await this.pool.query(
      `INSERT INTO v79_hub_state (store_key, revision, state)
       VALUES ($1, 1, $2::jsonb)
       ON CONFLICT (store_key) DO NOTHING
       RETURNING revision, state, updated_at`,
      [this.storeKey, JSON.stringify(state)],
    );
    if (!result.rowCount) return { initialized: false, current: await this.load() };
    const row = result.rows[0];
    return {
      initialized: true,
      current: {
        revision: Number(row.revision),
        state: structuredClone(row.state),
        updatedAt: new Date(row.updated_at).toISOString(),
      },
    };
  }

  async replace(expectedRevision, state) {
    const client = await this.pool.connect();
    try {
      await client.query("BEGIN");
      const locked = await client.query(
        "SELECT revision FROM v79_hub_state WHERE store_key = $1 FOR UPDATE",
        [this.storeKey],
      );
      if (!locked.rowCount) throw new Error("Hub PostgreSQL store has not been initialized.");
      const actualRevision = Number(locked.rows[0].revision);
      if (actualRevision !== expectedRevision) {
        throw new StoreRevisionConflictError(expectedRevision, actualRevision);
      }
      const updated = await client.query(
        `UPDATE v79_hub_state
         SET state = $2::jsonb, revision = revision + 1, updated_at = NOW()
         WHERE store_key = $1
         RETURNING revision, state, updated_at`,
        [this.storeKey, JSON.stringify(state)],
      );
      await client.query("COMMIT");
      const row = updated.rows[0];
      return {
        revision: Number(row.revision),
        state: structuredClone(row.state),
        updatedAt: new Date(row.updated_at).toISOString(),
      };
    } catch (error) {
      await client.query("ROLLBACK").catch(() => {});
      throw error;
    } finally {
      client.release();
    }
  }
  async transact(mutator) {
    const client = await this.pool.connect();
    try {
      await client.query("BEGIN");
      const locked = await client.query(
        "SELECT revision, state FROM v79_hub_state WHERE store_key = $1 FOR UPDATE",
        [this.storeKey],
      );
      if (!locked.rowCount) throw new Error("Hub PostgreSQL store has not been initialized.");
      const current = locked.rows[0];
      const nextState = structuredClone(current.state);
      const result = await mutator(nextState, Number(current.revision));
      const updated = await client.query(
        `UPDATE v79_hub_state
         SET state = $2::jsonb, revision = revision + 1, updated_at = NOW()
         WHERE store_key = $1
         RETURNING revision, state, updated_at`,
        [this.storeKey, JSON.stringify(nextState)],
      );
      await client.query("COMMIT");
      return {
        result,
        revision: Number(updated.rows[0].revision),
        state: structuredClone(updated.rows[0].state),
        updatedAt: new Date(updated.rows[0].updated_at).toISOString(),
      };
    } catch (error) {
      await client.query("ROLLBACK").catch(() => {});
      throw error;
    } finally {
      client.release();
    }
  }
}

export async function migrateJsonState(repository, state) {
  if (!state || typeof state !== "object" || Array.isArray(state)) {
    throw new Error("Hub JSON migration source must be an object.");
  }
  await repository.ensureSchema();
  const existing = await repository.load();
  if (existing) return { imported: false, current: existing };
  const initialized = await repository.initialize(state);
  return { imported: initialized.initialized, current: initialized.current };
}
