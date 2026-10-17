import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (path) => readFileSync(new URL(`../${path}`, import.meta.url), "utf8");

test("template redesign preserves Hub-managed app launch endpoints", () => {
  const source = read("src/components/AppSwitcher.tsx");
  for (const path of ["/api/apps/ffpro/launch", "/api/apps/tiquet/launch", "/api/apps/marketing/launch", "/api/apps/pos/launch"]) {
    assert.ok(source.includes(path), `missing existing managed launch endpoint ${path}`);
  }
  assert.match(source, /if \(app\.launchReady === false\) return null/);
  assert.match(source, /filteredApps\.map/);
});

test("dashboard remains permission-scoped and source-backed", () => {
  const dashboard = read("src/components/HubOverview.tsx");
  const sidebar = read("src/components/Sidebar.tsx");
  assert.match(dashboard, /fetch\("\/api\/dashboard\/summary"/);
  assert.match(dashboard, /visibleAppCards = appCards\.filter/);
  assert.match(dashboard, /status === "ok"/);
  assert.match(dashboard, /Performance overview/);
  assert.match(sidebar, /user\.platformOperator/);
  assert.match(sidebar, /visible: can\("connections"\)/);
});

test("redesigned sign-in preserves login, MFA and account recovery", () => {
  const login = read("src/components/Login.tsx");
  for (const token of ["/api/auth/login", "onSubmit={handleLogin}", "onSubmit={completeMfa}", "onSubmit={requestReset}", "onSubmit={completeReset}"]) {
    assert.ok(login.includes(token), `missing existing identity workflow ${token}`);
  }
  assert.match(login, /hub-login-story/);
});

test("app shortcut opens My Apps not overview and remains role-aware", () => {
  const app = read("src/App.tsx");
  assert.match(app, /onNavigateToEcosystem=\{\(\) => setCurrentView\("connections"\)\}/);
  assert.match(app, /canView\("security"\)/);
  assert.match(app, /canView\("billing"\)/);
});
