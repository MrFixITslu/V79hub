#!/usr/bin/env node
/**
 * V79 read-only Hub + Academy container parity observation.
 *
 * Uses ONLY: docker inspect --type container NAME
 * Does NOT: exec into containers, read databases/files, inspect networks,
 * publish, restart, build, deploy, run a payment, or print environment values.
 *
 * Evidence is NOT release authorization. Do not run against a live server
 * without operator approval for an inspection.
 */
import { execFileSync } from "node:child_process";
import { pathToFileURL } from "node:url";

const allowedContainer = /^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$/;
const sha256 = /^sha256:[a-f0-9]{64}$/;
const gitSha = /^[a-f0-9]{40}$/;
const envKey = /^[A-Z][A-Z0-9_]*$/;
const keys = [
  "V79_HUB_STORE_BACKEND", "DATABASE_URL",
  "WIPAY_ENABLED", "WIPAY_ENV", "WIPAY_PAYMENT_URL",
  "WIPAY_API_KEY", "WIPAY_ACCOUNT_NUMBER", "WIPAY_RESPONSE_URL",
  "V79_BILLING_STATE_SECRET", "V79_ACADEMY_BILLING_SECRET",
  "V79_HUB_BILLING_URL", "V79_ACADEMY_BILLING_CURRENCY",
];
function envFlags(entries) {
  const values = new Map();
  for (const item of Array.isArray(entries) ? entries : []) {
    // Environment values may contain = and sensitive data. Never emit them.
    const index = typeof item === "string" ? item.indexOf("=") : -1;
    if (index < 1) continue;
    const key = item.slice(0, index);
    if (envKey.test(key) && keys.includes(key)) values.set(key, item.slice(index + 1));
  }
  const flags = Object.fromEntries(keys.map(key => [key, Boolean(values.get(key))]));
  const backend = values.get("V79_HUB_STORE_BACKEND");
  const paymentEnv = values.get("WIPAY_ENV");
  const paymentEnabled = values.get("WIPAY_ENABLED");
  return {
    // Keep allowlisted enums only. Never print user-supplied or arbitrary values.
    flags,
    backend: backend === "postgres" || backend === "json" ? backend : "UNVERIFIED",
    wipay_environment: paymentEnv === "sandbox" || paymentEnv === "live" ? paymentEnv : "UNVERIFIED",
    wipay_enabled: paymentEnabled === "1" ? true : paymentEnabled === "0" ? false : "UNVERIFIED",
  };
}
export function summarizeContainerInspection(name, raw) {
  if (!allowedContainer.test(name)) throw Error("Invalid container name");
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) throw Error("Invalid Docker inspection record");
  const image = raw.Image;
  const state = raw.State || {};
  const labels = raw.Config?.Labels || {};
  const revision = labels["org.opencontainers.image.revision"];
  const flags = envFlags(raw.Config?.Env);
  return {
    name,
    state: state.Running === true ? "RUNNING" : state.Running === false ? "NOT_RUNNING" : "UNKNOWN",
    health: ["healthy", "unhealthy", "starting"].includes(state.Health?.Status)
      ? state.Health.Status : "NO_HEALTHCHECK_EVIDENCE",
    image_id: typeof image === "string" && sha256.test(image) ? image : "UNVERIFIED",
    build_revision: typeof revision === "string" && gitSha.test(revision) ? revision : "UNVERIFIED",
    mount_count: Array.isArray(raw.Mounts) ? raw.Mounts.length : null,
    observed: flags,
    // Never claim merchant/account approval from container config alone.
    provider_merchant_activation: "NOT_VERIFIED",
    database_data_integrity: "NOT_TESTED",
    customer_data_accessed: false,
  };
}
export function inspectContainerReadOnly(name, runner = execFileSync) {
  if (!allowedContainer.test(name)) throw Error("Invalid container name");
  let raw;
  try {
    raw = runner("docker", ["inspect", "--type", "container", name], {
      encoding: "utf8", timeout: 12000,
      stdio: ["ignore", "pipe", "ignore"], maxBuffer: 4_194_304,
    });
  } catch {
    // Docker errors can contain file paths or other private data. Redact.
    throw Error("Docker inspection unavailable; operator may need read-only Docker permissions.");
  }
  let parsed;
  try { parsed = JSON.parse(raw); } catch { throw Error("Invalid Docker inspection output."); }
  if (!Array.isArray(parsed) || parsed.length !== 1) throw Error("Unexpected Docker inspection record count.");
  return summarizeContainerInspection(name, parsed[0]);
}
function usage() {
  return "Read-only usage: node scripts/wipay-runtime-parity-readonly.mjs --hub CONTAINER --academy CONTAINER";
}
function runCli(argv) {
  if (argv.length === 1 && argv[0] === "--help") {
    process.stdout.write(usage() + "\n"); return 0;
  }
  if (argv.length !== 4 || argv[0] !== "--hub" || argv[2] !== "--academy") {
    throw Error(usage());
  }
  const hubName = argv[1], academyName = argv[3];
  if (!allowedContainer.test(hubName) || !allowedContainer.test(academyName) ||
      hubName === academyName) throw Error("Two distinct valid container names required.");
  const hub = inspectContainerReadOnly(hubName);
  const academy = inspectContainerReadOnly(academyName);
  const result = {
    schema: "vision79.wipay.operator_readonly_observation.v1",
    observed_at_utc: new Date().toISOString(),
    mode: "READ_ONLY_LOCAL_DOCKER_INSPECT",
    release_approval: "NOT_GRANTED",
    historic_r18_release_pins_changed: false,
    production_change: "NONE",
    hub,
    academy,
    preconditions: {
      hub_healthy: hub.state === "RUNNING" && hub.health === "healthy",
      hub_postgres_configured: hub.observed.backend === "postgres" && hub.observed.flags.DATABASE_URL,
      academy_running: academy.state === "RUNNING",
      wipay_live_activation_safe: false,
      operator_go_live_authorization: false,
    },
    next: "Independent image/restore/merchant review required. Never derive a live GO from this report.",
  };
  process.stdout.write(JSON.stringify(result, null, 2) + "\n");
  return 0;
}
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try { process.exitCode = runCli(process.argv.slice(2)); }
  catch (error) {
    process.stderr.write("PREFLIGHT=NO_GO " + String(error.message || "unknown").replace(/[\r\n]/g, " ").slice(0,220) + "\n");
    process.exitCode = 2;
  }
}
