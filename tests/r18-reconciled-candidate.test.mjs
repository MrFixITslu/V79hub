import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";

// Strict Git blob guards for the owner-authorised R3 source candidate.
// Previous accepted values and immutable recovered provenance are recorded in
// docs/launch/hub-r3-source-acceptance-20261119.json.
// This is source acceptance only, not production release approval.
const frozen = {
  "server.ts": "7d8b791f7416ebc9f36fabb70473c674e7c973ed",
  "src/App.tsx": "1cc808958b331124f7c0476a065e44bc80ccd831",
  "src/components/Login.tsx": "98cf523d2bc8b8ac8ff5c75896e9913a37e353a5",
  "src/components/Sidebar.tsx": "e3ac9f4eb15345cf00786ec51755fdbf5515dda6",
  "src/components/AdminConsole.tsx": "e21c2fe167c53f180ce0f2b1dff8071bf834b0b7",
  "scripts/hub-isolated-browser-preview.mjs": "f7761f0fa93d9bc279ac28514fab95e72bfca894",
  "src/components/HubOverview.tsx": "088094e8afd16832499454b729a2d42e9318c629",
  "src/index.css": "05395ab058ef7b4a58140b94a761a2d7052b306e",
  "src/lib/dashboardTruth.ts": "fe60c5afc82f8f093ec94923fcbec9d40e267e7d",
  "tests/hub-dashboard-truth.test.mjs": "13350b4437668d7d13792ca2def755fa545d2739",
  "server/google-login.mjs": "ee9f40c65ba661c2fb9b0e3e67f1f07ea64a0602",
  "server/pos-team-acknowledgement.mjs": "1415a351786d6478e73830d6ce5647a26c712a61",
  "src/components/GoogleSignIn.tsx": "1f597890e965edb4ac3a95bfb7087aea9937c3ab",
  "scripts/hub-r3-isolated-browser-preview.mjs": "2cdd84705eb50f9d2c42ab47c119e8e33d07c56d",
  "tests/google-login-verifier.test.mjs": "c90279b5bc7a8b166a8a53c1fd3cb82d8c463e78"
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
