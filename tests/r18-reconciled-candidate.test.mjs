// Read-only Git object fingerprint guards: accepted security, reviewed Vision79 UI and tests.
// Founder authorized Vision79 UI-only visual release on 25 October 2026. Exactly
// Sidebar, HubOverview and index.css have updated blobs; server.ts, App.tsx,
// Login.tsx, AdminConsole, signed launcher and trusted metrics remain pinned.
// Original reviewed UI source SHA values are retained below for audit and do
// not grant permission to weaken auth/MFA or skip runtime acceptance.
const priorAcceptedUiBlobs = Object.freeze({
  "src/components/Sidebar.tsx": "39391d6121b7d8435e8886241a1b9fa0740e2bb6",
  "src/components/HubOverview.tsx": "937247e63571b310f30c2dd21ce8af972386bd07",
  "src/index.css": "566570e28c95d58697f391cf2b67be2290eefe"
});
const frozen = {
  "server.ts": "6784def9a38d018f87aa85e0d73ec10d65972daf",
  "src/App.tsx": "37815fc308b2fc52da7e6c1533a7180a6adb312f",
  "src/components/Login.tsx": "53deeec03ba8793a2412a09ad91f7747fe442510",
  "src/components/Sidebar.tsx": "503c16341b23ef63fab502857df3efc420263ce6",
  "src/components/AdminConsole.tsx": "a809f9bb614ff547d28eeab8d15535652c3b7d5c",
  "scripts/hub-isolated-browser-preview.mjs": "f7761f0fa93d9bc279ac28514fab95e72bfca894",
  "src/components/HubOverview.tsx": "c77a141517a5c29591c54d980d459ba7a646deeb",
  "src/index.css": "ee82a85c1376b1a457068d95475acbb105de99ce",
  "src/lib/dashboardTruth.ts": "fe60c5afc82f8f093ec94923fcbec9d40e267e7d",
  "tests/hub-dashboard-truth.test.mjs": "13350b4437668d7d13792ca2def755fa545d2739"
};
function gitBlobSha(bytes) {
  const prefix = Buffer.from("blob " + bytes.length);
  return createHash("sha1").update(prefix).update(Buffer.from([0])).update(bytes).digest("hex");
}
test("Visual update revises precisely the three reviewed UI pins", () => {
  assert.deepEqual(Object.keys(priorAcceptedUiBlobs).sort(), [
    "src/components/HubOverview.tsx",
    "src/components/Sidebar.tsx",
    "src/index.css",
  ]);
  for (const [name, prior] of Object.entries(priorAcceptedUiBlobs)) {
    assert.notEqual(prior, frozen[name], "Visual candidate must differ from accepted image UI: " + name);
  }
});
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
