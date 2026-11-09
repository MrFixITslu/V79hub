import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";

// R18 remains recorded in full for audit and rollback review. R19 owner approval
// was given on 9 November 2026 for precisely the two reviewed source Git blobs.
// This is still an exact-hash release gate: no bypasses or wildcard allowances.
const r18Accepted = Object.freeze({
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
});

const r19OwnerApproved = Object.freeze({
  "server.ts": "9e0022b0fb83288dc2162e3ffd5a0b49bd4556bd",
  "src/App.tsx": "d7f2f681ed2afa2858ff9ed31e6605e47ec43c1f",
});

// Pin the new route's authorisation guard and red-team unit tests too.
const r19SupportFiles = Object.freeze({
  "server/organization-name.mjs": "9135a55ace25a742e4d416d4c62171e251fcbb23",
  "tests/organization-name.test.mjs": "ecc6692dd824da32ef9dde59501ee1d548810b63",
});

test("R19 owner-approved overlay changes exactly two previously protected source files", () => {
  assert.deepEqual(Object.keys(r19OwnerApproved).sort(), ["server.ts", "src/App.tsx"].sort());
  for (const [name, approvedSha] of Object.entries(r19OwnerApproved)) {
    assert.ok(Object.hasOwn(r18Accepted, name), "Source file must already be R18-protected: " + name);
    assert.notEqual(r18Accepted[name], approvedSha, "R19 approval must represent a reviewed change: " + name);
  }
});

const frozen = Object.freeze({ ...r18Accepted, ...r19OwnerApproved, ...r19SupportFiles });
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
