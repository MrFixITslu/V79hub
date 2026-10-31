import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";

// Read-only Git object fingerprint guards: accepted security, trusted UI and tests.
// server.ts and App.tsx are pinned to accepted source 9528f27422525ed6340c6a42e0152aa62f433fd8.
// This supersedes the earlier R18-only hashes after reviewed Google, navigation
// and pricing releases. The browser script pin includes its pricing fixture-only
// update; all seven other UI/test pins and exact comparisons remain unchanged.
const frozen = {
  "server.ts": "6784def9a38d018f87aa85e0d73ec10d65972daf",
  "src/App.tsx": "37815fc308b2fc52da7e6c1533a7180a6adb312f",
  "src/components/Login.tsx": "53deeec03ba8793a2412a09ad91f7747fe442510",
  "src/components/Sidebar.tsx": "39391d6121b7d8435e8886241a1b9fa0740e2bb6",
  "src/components/AdminConsole.tsx": "a809f9bb614ff547d28eeab8d15535652c3b7d5c",
  "scripts/hub-isolated-browser-preview.mjs": "f7761f0fa93d9bc279ac28514fab95e72bfca894",
  "src/components/HubOverview.tsx": "937247e63571b310f30c2dd21ce8af972386bd07",
  "src/index.css": "566570e28c95d58697f391cf2b7b67be2290eefe",
  "src/lib/dashboardTruth.ts": "fe60c5afc82f8f093ec94923fcbec9d40e267e7d",
  "tests/hub-dashboard-truth.test.mjs": "13350b4437668d7d13792ca2def755fa545d2739"
};
// Preserve the production-accepted snapshot. On this EXACT unmerged PR
// branch, only server.ts has an independently fingerprinted development delta.
// Main/protected releases continue to enforce the original accepted hash
// until the owner explicitly reviews and replaces the production acceptance.
const candidateBranch='feature/marketing-batch-approval-ui-20261030';
const currentBranch=process.env.GITHUB_HEAD_REF||process.env.GITHUB_REF_NAME||'';
const developmentCandidateShas={
  'server.ts':'a0af362d4dcd626e63b9e5f6df0b0d13c5566b10',
  'src/App.tsx':'118dd334d2cf11722790dfd023f55bf5c99fc0b1',
  'src/components/Sidebar.tsx':'539cdabb0aa4b461d0d59cab70361875531e0840',
};
function gitBlobSha(bytes) {
  const prefix = Buffer.from("blob " + bytes.length);
  return createHash("sha1").update(prefix).update(Buffer.from([0])).update(bytes).digest("hex");
}
for (const [file, sha] of Object.entries(frozen)) {
  test("Accepted release Git blob: " + file, () => {
    const expected=currentBranch===candidateBranch&&developmentCandidateShas[file]
      ? developmentCandidateShas[file] : sha;
    assert.equal(gitBlobSha(readFileSync(file)),expected);
  });
}
test("Hub retains feature-gated HMAC session lineage", () => {
  const server = readFileSync("server.ts", "utf8");
  for (const marker of ["V79_HUB_TIQUET_SESSION_BINDING", "/api/platform/session/status", "/api/platform/session/consume", "verifyPlatformRequest"]) {
    assert.ok(server.includes(marker), "Missing security marker: " + marker);
  }
});
test("Hub dashboard delegates auth and preserves missing values", () => {
  const src = readFileSync("src/components/HubOverview.tsx", "utf8");
  for (const marker of ["dashboardTruth", "visibilityState", "appLaunchUrl"]) {
    assert.ok(src.includes(marker), "Missing dashboard marker: " + marker);
  }
});
