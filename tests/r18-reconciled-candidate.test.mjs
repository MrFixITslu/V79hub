import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";

// Read-only Git object fingerprint guards: frozen security, trusted UI and test files.
const frozen = {
  "server.ts": "4d208cd2d55b2d39381c2096615d99b56f893a84",
  "src/App.tsx": "606f46be879eca62931aec9720ac3a2d846556f8",
  "src/components/Login.tsx": "53deeec03ba8793a2412a09ad91f7747fe442510",
  "src/components/Sidebar.tsx": "39391d6121b7d8435e8886241a1b9fa0740e2bb6",
  "src/components/AdminConsole.tsx": "a809f9bb614ff547d28eeab8d15535652c3b7d5c",
  "scripts/hub-isolated-browser-preview.mjs": "03ca0fd1f4e5191f784bca4db19226105b714284",
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
  test("R18 frozen Git blob: " + file, () => {
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
