#!/usr/bin/env node
// Explicitly disposable STAGING ONLY. Never supports production DB names or TCP.
import { Pool } from "pg";
import { prepareApprovedLegacyCutover } from "../server/legacy-cutover.mjs";

const APPLY = process.argv.includes("--apply-staging");
const dbName = process.env.PGDATABASE || "";
const socket = process.env.PGHOST || "";
if (process.env.V79_STAGING_MIGRATION !== "I_UNDERSTAND_STAGING_ONLY" ||
    dbName !== "v79_01_staging_hub" || !socket.includes("/v79-staging-v79-01-20261008/") ||
    process.argv.includes("--seed-synthetic")) {
  console.error("STAGING SAFETY GUARD: refused.");
  process.exit(2);
}
const pool = new Pool({ host: socket, port: 5432, database: dbName, user: "postgres", max: 1,
  connectionTimeoutMillis: 2500 });
const conn=await pool.connect();
try {
  await conn.query("BEGIN");
  const guard = await conn.query(
    "SELECT current_database() AS name, inet_server_addr() AS address");
  const sentinel = await conn.query(
    "SELECT marker FROM v79_staging_sentinel WHERE id=1 FOR UPDATE");
  if (guard.rows[0]?.name !== dbName || guard.rows[0]?.address !== null ||
      sentinel.rows[0]?.marker !== "SYNTHETIC_ONLY_V79_01") {
    throw new Error("Database is not isolated marked staging.");
  }
  const state = await conn.query(
    "SELECT revision, state FROM v79_hub_state WHERE store_key='main' FOR UPDATE");
  if (state.rowCount !== 1) throw new Error("Staging store is not initialised.");
  const original = state.rows[0].state;
  // Activation timestamp is provided explicitly by the staging operator.
  const activationAt = process.env.V79_STAGING_ACTIVATED_AT || new Date().toISOString();
  const result = prepareApprovedLegacyCutover(original, {
    ownerOrganizationId: "vision79-owner",
    verifiedOwnerUserId: "founder-user",
    customerOrganizationId: "existing-customer",
    activationAt,
  });
  if (APPLY && !result.alreadyApplied) {
    const updated=await conn.query(
      "UPDATE v79_hub_state SET state=$1::jsonb, revision=revision+1, updated_at=NOW() WHERE store_key='main' AND revision=$2 RETURNING revision",
      [JSON.stringify(result.planned),state.rows[0].revision]);
    if (updated.rowCount !== 1) throw new Error("Staging revision changed unexpectedly.");
  }
  if (APPLY) await conn.query("COMMIT");
  else await conn.query("ROLLBACK");
  console.log(JSON.stringify({
    mode: APPLY ? "STAGING_APPLY_ONLY" : "STAGING_DRY_RUN",
    alreadyApplied: result.alreadyApplied,
    trialStartedAt: result.summary.trialStart,
    trialEndsAt: result.summary.trialEnd,
    retainedCustomerAppCount: result.summary.retainedEntitlements,
    productionDataTouched: false,
  }));
} catch (error) {
  await conn.query("ROLLBACK").catch(()=>{});
  console.error("STAGING_FAILURE:",error.message);
  process.exitCode=1;
} finally {
  conn.release();
  await pool.end();
}
