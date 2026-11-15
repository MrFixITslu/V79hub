import { validateMarketingRenameAuthorization } from "./marketing-rename-authorization.mjs";
import { createHash, randomUUID } from "node:crypto";

function canonicalJson(value) {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value).sort().map(
      key => `${JSON.stringify(key)}:${canonicalJson(value[key])}`
    ).join(",")}}`;
  }
  return JSON.stringify(value);
}

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

    await this.pool.query(`
      CREATE TABLE IF NOT EXISTS v79_hub_organization_name_outbox (
        id TEXT PRIMARY KEY,
        event_id TEXT NOT NULL,
        organization_id TEXT NOT NULL,
        destination TEXT NOT NULL CHECK (destination IN ('tiquet', 'pos')),
        organization_name TEXT NOT NULL,
        name_revision BIGINT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending'
          CHECK (status IN ('pending', 'processing', 'delivered', 'dead_letter')),
        attempts INTEGER NOT NULL DEFAULT 0,
        next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        lease_until TIMESTAMPTZ,
        last_error TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        delivered_at TIMESTAMPTZ,
        UNIQUE (event_id, destination)
      )
    `);

    await this.pool.query(`
      ALTER TABLE v79_hub_organization_name_outbox
      ADD COLUMN IF NOT EXISTS request_hash TEXT
    `);

    await this.pool.query(`
      ALTER TABLE v79_hub_organization_name_outbox
      ADD COLUMN IF NOT EXISTS lease_token TEXT
    `);

    await this.pool.query(`
      CREATE INDEX IF NOT EXISTS v79_hub_org_name_outbox_ready
      ON v79_hub_organization_name_outbox (status, next_attempt_at)
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
  async renameOrganizationWithOutbox({
    organizationId,
    name,
    eventId,
    auditEvent,
    destinations = ["tiquet", "pos"],
    marketingAuthorization = null,
  }) {
    const normalizedName = String(name || "").trim();
    const normalizedId = String(organizationId || "").trim();
    const normalizedEventId = String(eventId || "").trim();

    if (!normalizedId || !normalizedEventId || !normalizedName) {
      throw new Error("Organisation rename requires an ID, event ID and name.");
    }
    if (normalizedName.length > 120) {
      throw new Error("Organisation name must not exceed 120 characters.");
    }
    if (!Array.isArray(destinations)) {
      throw new Error("Organisation rename destinations must be an array.");
    }

    const allowedDestinations = [...new Set(destinations)];
    if (
      allowedDestinations.length === 0 ||
      allowedDestinations.some(item => !["tiquet", "pos"].includes(item))
    ) {
      throw new Error("Organisation rename destinations must be Tiquet and/or POS.");
    }
    if (!auditEvent || typeof auditEvent !== "object" || Array.isArray(auditEvent)) {
      throw new Error("Organisation rename requires an audit event.");
    }

    const requestHash = createHash("sha256").update(canonicalJson({
      organizationId: normalizedId,
      name: normalizedName,
      eventId: normalizedEventId,
      auditEvent,
      destinations: [...allowedDestinations].sort(),
    })).digest("hex");

    const client = await this.pool.connect();
    try {
      await client.query("BEGIN");

      const locked = await client.query(
        "SELECT revision, state FROM v79_hub_state WHERE store_key = $1 FOR UPDATE",
        [this.storeKey],
      );
      if (!locked.rowCount) {
        throw new Error("Hub PostgreSQL store has not been initialized.");
      }

      const current = locked.rows[0];
      const currentRevision = Number(current.revision);
      const state = structuredClone(current.state);

      // Check the owner and tenant against the locked database state.
      if (marketingAuthorization) {
        validateMarketingRenameAuthorization(
          state,
          { ...marketingAuthorization, organizationId: normalizedId },
          { checkExpectedName: false },
        );
        if (
          auditEvent.organizationId !== normalizedId ||
          auditEvent.actorUserId !== marketingAuthorization.hubOwnerUserId
        ) {
          throw new Error("Organisation rename audit identity mismatch.");
        }
      }

      const prior = await client.query(
        `SELECT organization_id, organization_name, destination, request_hash
         FROM v79_hub_organization_name_outbox
         WHERE event_id = $1`,
        [normalizedEventId],
      );

      if (prior.rowCount) {
        const matches = prior.rows.every(row =>
          row.organization_id === normalizedId &&
          row.organization_name === normalizedName
          && row.request_hash === requestHash
        );
        if (
          !matches ||
          prior.rowCount !== allowedDestinations.length ||
          allowedDestinations.some(destination =>
            !prior.rows.some(row => row.destination === destination)
          )
        ) {
          throw new Error("Organisation rename event ID was reused with different data.");
        }

        await client.query("COMMIT");
        return {
          applied: false,
          duplicate: true,
          revision: currentRevision,
          state,
        };
      }

      // Check the expected name after duplicate detection. This allows
      // an identical successful request to be retried safely.
      if (marketingAuthorization) {
        validateMarketingRenameAuthorization(
          state,
          { ...marketingAuthorization, organizationId: normalizedId },
        );
      }

      if (!Array.isArray(state.organizations)) {
        throw new Error("Hub organisation state is unavailable.");
      }

      const organization = state.organizations.find(item => item.id === normalizedId);
      if (!organization) {
        throw new Error("Organisation was not found.");
      }

      if (!Array.isArray(state.auditEvents)) {
        throw new Error("Hub audit event state is unavailable.");
      }

      const nextRevision = currentRevision + 1;
      organization.name = normalizedName;
      organization.nameRevision = nextRevision;
      state.auditEvents.push(structuredClone(auditEvent));

      await client.query(
        `UPDATE v79_hub_state
         SET state = $2::jsonb, revision = revision + 1, updated_at = NOW()
         WHERE store_key = $1`,
        [this.storeKey, JSON.stringify(state)],
      );

      for (const destination of allowedDestinations) {
        await client.query(
          `INSERT INTO v79_hub_organization_name_outbox
           (id, event_id, organization_id, destination, organization_name, name_revision, request_hash)
           VALUES ($1, $2, $3, $4, $5, $6, $7)`,
          [
            `${normalizedEventId}:${destination}`,
            normalizedEventId,
            normalizedId,
            destination,
            normalizedName,
            nextRevision,
            requestHash,
          ],
        );
      }

      await client.query("COMMIT");
      return {
        applied: true,
        duplicate: false,
        revision: nextRevision,
        state,
      };
    } catch (error) {
      await client.query("ROLLBACK").catch(() => {});
      throw error;
    } finally {
      client.release();
    }
  }


  async claimOrganizationNameDelivery(destination, {
    leaseSeconds = 90,
    maxAttempts = 8,
  } = {}) {
    if (!["tiquet", "pos"].includes(destination)) {
      throw new Error("Invalid outbox destination.");
    }
    if (!Number.isInteger(leaseSeconds) || leaseSeconds < 5 || leaseSeconds > 300 ||
        !Number.isInteger(maxAttempts) || maxAttempts < 1 || maxAttempts > 30) {
      throw new Error("Invalid outbox lease settings.");
    }

    const client = await this.pool.connect();
    try {
      await client.query("BEGIN");

      // Expired final attempts become visible as dead letters.
      await client.query(`
        UPDATE v79_hub_organization_name_outbox
        SET status = 'dead_letter',
            lease_token = NULL,
            lease_until = NULL,
            updated_at = NOW(),
            last_error = COALESCE(last_error, 'Maximum delivery attempts reached')
        WHERE destination = $1 AND attempts >= $2
          AND (
            (status = 'pending' AND next_attempt_at <= NOW()) OR
            (status = 'processing' AND lease_until <= NOW())
          )
      `, [destination, maxAttempts]);

      const ready = await client.query(`
        SELECT id
        FROM v79_hub_organization_name_outbox
        WHERE destination = $1 AND attempts < $2
          AND (
            (status = 'pending' AND next_attempt_at <= NOW()) OR
            (status = 'processing' AND lease_until <= NOW())
          )
        ORDER BY next_attempt_at, created_at, id
        FOR UPDATE SKIP LOCKED
        LIMIT 1
      `, [destination, maxAttempts]);

      if (!ready.rowCount) {
        await client.query("COMMIT");
        return null;
      }

      const leaseToken = randomUUID();
      const updated = await client.query(`
        UPDATE v79_hub_organization_name_outbox
        SET status = 'processing',
            attempts = attempts + 1,
            lease_token = $2,
            lease_until = NOW() + ($3 * INTERVAL '1 second'),
            updated_at = NOW()
        WHERE id = $1
        RETURNING id, event_id, organization_id, destination,
                  organization_name, name_revision, attempts
      `, [ready.rows[0].id, leaseToken, leaseSeconds]);

      await client.query("COMMIT");

      const row = updated.rows[0];
      return {
        id: row.id,
        eventId: row.event_id,
        organizationId: row.organization_id,
        destination: row.destination,
        name: row.organization_name,
        nameRevision: Number(row.name_revision),
        attempts: Number(row.attempts),
        leaseToken,
      };
    } catch (error) {
      await client.query("ROLLBACK").catch(() => {});
      throw error;
    } finally {
      client.release();
    }
  }

  async markOrganizationNameDelivered({ id, leaseToken }) {
    if (!id || !leaseToken) throw new Error("Delivery lease identity is required.");
    const result = await this.pool.query(`
      UPDATE v79_hub_organization_name_outbox
      SET status = 'delivered',
          delivered_at = NOW(),
          lease_token = NULL,
          lease_until = NULL,
          last_error = NULL,
          updated_at = NOW()
      WHERE id = $1 AND lease_token = $2
        AND status = 'processing' AND lease_until > NOW()
      RETURNING id
    `, [id, leaseToken]);
    if (result.rowCount !== 1) {
      throw new Error("Outbox lease lost; delivery acknowledgement rejected.");
    }
    return true;
  }

  async markOrganizationNameFailed({
    id, leaseToken, attempts, error, maxAttempts = 8,
  }) {
    if (!id || !leaseToken ||
        !Number.isInteger(attempts) || attempts < 1 ||
        !Number.isInteger(maxAttempts) || maxAttempts < 1 || maxAttempts > 30) {
      throw new Error("Invalid failed delivery details.");
    }

    const delaySeconds = Math.min(3600, 15 * (2 ** Math.min(attempts - 1, 10)));
    const message = String(error?.message || error || "Destination unavailable").slice(0, 400);

    const result = await this.pool.query(`
      UPDATE v79_hub_organization_name_outbox
      SET status = CASE
            WHEN attempts >= $3 THEN 'dead_letter'
            ELSE 'pending'
          END,
          next_attempt_at = NOW() + ($4 * INTERVAL '1 second'),
          lease_token = NULL,
          lease_until = NULL,
          last_error = $5,
          updated_at = NOW()
      WHERE id = $1 AND lease_token = $2
        AND status = 'processing' AND lease_until > NOW()
      RETURNING id, status
    `, [id, leaseToken, maxAttempts, delaySeconds, message]);

    if (result.rowCount !== 1) {
      throw new Error("Outbox lease lost; retry update rejected.");
    }
    return result.rows[0].status;
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
