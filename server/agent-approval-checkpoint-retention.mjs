import { constants } from "node:fs";
import { lstat, mkdir, open, readFile, readdir, rmdir } from "node:fs/promises";
import path from "node:path";

// OUTSIDE the Hub runtime: a small operator-managed checkpoint retention tool.
// The checkpoint contains no names, tenants, event bodies, emails or keys.
// Local files are NOT immutable/offsite merely because O_EXCL is used.
const SCHEMA = "v79-agent-approval-audit-checkpoint-v1";
const GENESIS = "0".repeat(64);
const EPOCH = /^[a-z][a-z0-9-]{0,23}$/;
const HEX_MAC = /^[a-f0-9]{64}$/;

export function safeAuditCheckpoint(input) {
  if (!input || typeof input !== "object" || Array.isArray(input) ||
      Object.keys(input).some(key => ![
        "schema", "count", "headMac", "executionEnabled",
        "independentRetentionConfigured",
      ].includes(key)) ||
      input.schema !== SCHEMA || !Number.isSafeInteger(input.count) ||
      input.count < 0 || input.count > 10000 ||
      typeof input.headMac !== "string" || !HEX_MAC.test(input.headMac) ||
      (input.count === 0) !== (input.headMac === GENESIS) ||
      (Object.hasOwn(input, "executionEnabled") && input.executionEnabled !== false) ||
      (Object.hasOwn(input, "independentRetentionConfigured") &&
       input.independentRetentionConfigured !== false)) {
    throw new Error("Invalid decision-only audit checkpoint.");
  }
  return { schema: SCHEMA, count: input.count, headMac: input.headMac };
}

// This does not prove a longer chain derives from the anchor; that proof
// requires replaying/validating all signed events with the separate audit key.
export function compareAuditCheckpointToAnchor(anchor, current) {
  let earlier, now;
  try {
    earlier = safeAuditCheckpoint(anchor);
    now = safeAuditCheckpoint(current);
  } catch {
    return "invalid";
  }
  if (now.count < earlier.count) return "rollback-detected";
  if (now.count > earlier.count) return "unanchored-growth";
  return now.headMac === earlier.headMac ? "match" : "fork-detected";
}

function recordedFile(epoch, count) {
  return `${epoch}-${String(count).padStart(8, "0")}.json`;
}

function exactArchivedRecord(value, epoch, count) {
  if (!value || typeof value !== "object" || Array.isArray(value) ||
      Object.keys(value).sort().join("|") !== "count|epoch|headMac|schema" ||
      value.epoch !== epoch || value.count !== count) {
    throw new Error("Checkpoint vault contains an invalid archive record.");
  }
  return safeAuditCheckpoint(value);
}

async function assertPrivateFile(filename) {
  const details = await lstat(filename);
  if (!details.isFile() || (details.mode & 0o077) !== 0 ||
      (typeof process.getuid === "function" && details.uid !== process.getuid())) {
    throw new Error("Checkpoint vault contains an untrusted or accessible file.");
  }
}

async function readLatest(directory, epoch) {
  const list = await readdir(directory);
  const pattern = new RegExp(`^${epoch}-(\\d{8})\\.json$`);
  const indexes = [];
  for (const name of list) {
    if (!name.startsWith(epoch + "-")) continue;
    const match = pattern.exec(name);
    if (!match || Number(match[1]) > 10000) {
      throw new Error("Checkpoint vault contains an unexpected archive filename.");
    }
    indexes.push(Number(match[1]));
  }
  if (!indexes.length) return null;
  indexes.sort((a, b) => a - b);
  let previous = -1;
  let latest = null;
  for (const count of indexes) {
    if (count <= previous) throw new Error("Checkpoint vault has duplicate indices.");
    const filename = path.join(directory, recordedFile(epoch, count));
    await assertPrivateFile(filename);
    let stored;
    try { stored = JSON.parse(await readFile(filename, "utf8")); }
    catch { throw new Error("Checkpoint vault contains unreadable data."); }
    latest = exactArchivedRecord(stored, epoch, count);
    previous = count;
  }
  return latest;
}

/**
 * Operator-only explicit retention of an externally exported MFA checkpoint.
 * Caller MUST provide a pre-created, private, independent directory.
 * The function never fetches a Hub route, reads secrets or mutates Hub data.
 */
export async function retainAuditCheckpoint({
  directory, hubDataDirectory, epoch, checkpoint,
} = {}) {
  if (typeof directory !== "string" || !path.isAbsolute(directory) ||
      typeof hubDataDirectory !== "string" || !path.isAbsolute(hubDataDirectory) ||
      typeof epoch !== "string" || !EPOCH.test(epoch)) {
    throw new Error("Explicit private external checkpoint destination and epoch required.");
  }
  const target = path.resolve(directory);
  const hub = path.resolve(hubDataDirectory);
  if (target === hub || target.startsWith(hub + path.sep) ||
      hub.startsWith(target + path.sep)) {
    throw new Error("Checkpoint destination must be outside Hub data.");
  }
  const details = await lstat(target);
  if (!details.isDirectory() || (details.mode & 0o077) !== 0 ||
      (typeof process.getuid === "function" && details.uid !== process.getuid())) {
    throw new Error("Checkpoint destination is not an owner-only directory.");
  }
  const next = safeAuditCheckpoint(checkpoint);
  const lock = path.join(target, ".agent-audit-lock");
  // No automatic stale-lock deletion; crash or competing writer fails closed.
  await mkdir(lock, { mode: 0o700 });
  try {
    const prior = await readLatest(target, epoch);
    if (prior) {
      const comparison = compareAuditCheckpointToAnchor(prior, next);
      if (comparison === "match") return { status: "already-retained", epoch, ...next };
      if (comparison !== "unanchored-growth") {
        throw new Error("Checkpoint rollback or fork detected: " + comparison);
      }
    }
    const filename = path.join(target, recordedFile(epoch, next.count));
    const record = { epoch, ...next };
    const handle = await open(filename,
      constants.O_CREAT | constants.O_EXCL | constants.O_WRONLY | constants.O_NOFOLLOW,
      0o600);
    try {
      await handle.writeFile(JSON.stringify(record) + "\n", "utf8");
      await handle.sync();
    } finally {
      await handle.close();
    }
    // Sync the directory metadata as well as the individual checkpoint file.
    const directoryHandle = await open(target, constants.O_RDONLY);
    try { await directoryHandle.sync(); }
    finally { await directoryHandle.close(); }
    return { status: "retained-locally", epoch, ...next };
  } finally {
    await rmdir(lock);
  }
}
