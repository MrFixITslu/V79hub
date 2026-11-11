#!/usr/bin/env node
/**
 * Read-only release gate. Compares this checkout's protected files against
 * SHA-256 digests observed from the running 11 Nov 2026 Hub container.
 * Does NOT inspect or mutate the server, secrets, customer data or Git state.
 *
 * Usage: node scripts/reconciliation/verify-live-file-digests.mjs
 * Until exact live source is recovered, a FAIL is expected and must NOT
 * be bypassed by changing the recorded production digests.
 */
import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import { dirname, resolve, relative, isAbsolute } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const manifestPath = resolve(root, "docs/reconciliation/hub-live-source-baseline-20261111.json");
const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
const entries = Object.entries(manifest.production?.filesSha256 ?? {});
if (manifest.schema !== "v79.hub.live-source-observation.v1" || entries.length < 10) {
  throw new Error("Missing or incomplete production source observation");
}
let match = 0;
let mismatch = 0;
for (const [path, expected] of entries) {
  const absolute = resolve(root, path);
  const rel = relative(root, absolute);
  if (!rel || rel.startsWith("..") || isAbsolute(rel) ||
      !/^[a-f0-9]{64}$/i.test(expected)) {
    throw new Error("Invalid source baseline entry");
  }
  if (!existsSync(absolute)) {
    console.log(`MISSING ${path}`);
    mismatch++;
    continue;
  }
  const actual = createHash("sha256").update(readFileSync(absolute)).digest("hex");
  if (actual === expected) {
    console.log(`MATCH ${path}`);
    match++;
  } else {
    console.log(`DIFFERENT ${path}`);
    mismatch++;
  }
}
console.log(`LIVE_SOURCE_MATCHED=${match} LIVE_SOURCE_UNMATCHED=${mismatch}`);
console.log("READ_ONLY=YES DEPLOYMENT=NO");
if (mismatch !== 0) {
  console.error("RELEASE_HOLD=YES: candidate source is NOT the observed live Hub");
  process.exitCode = 1;
} else {
  console.log("FILE_HASHES_MATCH=YES; this alone is NOT release or browser acceptance");
}
