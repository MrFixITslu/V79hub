import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";

// Read-only Git object fingerprint guards: accepted security, trusted UI and tests.
// App.tsx and remaining files retain their accepted source pins from
// 9528f27422525ed6340c6a42e0152aa62f433fd8.
// server.ts was independently compared against that exact accepted blob on
// 2026-11-08: only a 15-line additive owner-MFA step-up route/import was found,
// with no removed lines. Its separate owner access, origin, TOTP attempt limit,
// and persistence rollback tests passed. Preserve exact hash enforcement here;
// never refresh a pin without reviewing the corresponding source delta.
const frozen = {
  "server.ts": "f682410fa85481bcfc6d0e181c27bc31515d4370",
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
function gitBlobSha(bytes) {
  const prefix = Buffer.from("blob " + bytes.length);
  return createHash("sha1").update(prefix).update(Buffer.from([0])).update(bytes).digest("hex");
}
for (const [file, sha] of Object.entries(frozen)) {
  test("Accepted release Git blob: " + file, () => {
    assert.equal(gitBlobSha(readFileSync(file)), sha);
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
