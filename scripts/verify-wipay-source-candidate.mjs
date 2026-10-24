import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";

const root = process.cwd();
const manifest = JSON.parse(readFileSync(resolve(root, "docs/launch/wipay-prelive-source-candidate-20261024.json"), "utf8"));

function gitBlobHash(bytes) {
  return createHash("sha1").update("blob " + bytes.length + "\0").update(bytes).digest("hex");
}
function git(...args) {
  return execFileSync("git", args, { cwd: root, encoding: "utf8", timeout: 15000 }).trim();
}
function requireSha(value, label) {
  assert.match(String(value), /^[0-9a-f]{40}$/, label + " must be an immutable Git SHA");
}
assert.equal(manifest.schema, "vision79.hub.wipay.source_candidate.v1");
assert.equal(manifest.decision, "DRAFT_SOURCE_ATTESTATION_NOT_PRODUCTION_APPROVAL");
for (const name of ["merge_authorized", "production_deployment_authorized", "live_payment_activation_authorized",
  "merchant_endpoint_xcd_settlement_verified", "installed_server_parity_verified", "real_provider_transaction_performed"]) {
  assert.equal(manifest.release_gates[name], false, "Fail closed: " + name);
}
assert.equal(manifest.release_gates.immutable_r18_test_must_remain_unchanged, true);
assert.equal(manifest.release_gates.full_existing_ci_must_not_be_relabelled_pass, true);
assert.equal(manifest.release_gates.owner_approval_required, true);
const base = manifest.accepted_previous;
requireSha(base.source_commit, "accepted source");
requireSha(base.server_git_blob, "accepted server blob");
requireSha(base.immutable_test_git_blob, "accepted R18 test blob");
assert.equal(git("rev-parse", base.source_commit + ":server.ts"), base.server_git_blob,
  "The accepted R18 source fingerprint has changed; stop.");
assert.equal(gitBlobHash(readFileSync(resolve(root, base.immutable_test))), base.immutable_test_git_blob,
  "Do not revise the accepted R18 pin test to greenlight new source.");
assert.ok(readFileSync(resolve(root, base.immutable_test), "utf8").includes(base.server_git_blob),
  "Accepted R18 check must still enforce the original server hash.");
assert.equal(manifest.candidate.branch, "feature/wipay-response-contract-prelive-20261024");
const paths = Object.entries(manifest.candidate.files);
assert.ok(paths.length >= 14, "Missing candidate source fingerprint inventory");
for (const [p, expected] of paths) {
  assert.ok(!p.startsWith("/") && !p.includes("..") && !p.includes("\\"),
    "Source paths must be repository relative.");
  requireSha(expected, p);
  assert.equal(gitBlobHash(readFileSync(resolve(root, p))), expected,
    "Candidate source drift: " + p + "; review and explicitly re-pin before release.");
}
const workflow = readFileSync(resolve(root, ".github/workflows/v79-ci-cd.yml"), "utf8");
assert.match(workflow, /workflow_dispatch:/);
assert.match(workflow, /approved_sha:/);
assert.match(workflow, /V79_HUB_APPROVED_SHA/);
assert.match(workflow, /github\.ref == 'refs\/heads\/main'/);
console.log("SOURCE_CANDIDATE_FINGERPRINTS=PASS_" + paths.length);
console.log("HISTORICAL_R18_BASELINE=UNCHANGED");
console.log("SOURCE_CANDIDATE=UNAPPROVED REVIEW_ONLY");
console.log("MERGE=NOT_AUTHORIZED DEPLOY=NOT_AUTHORIZED WIPAY_LIVE=NO_GO");
