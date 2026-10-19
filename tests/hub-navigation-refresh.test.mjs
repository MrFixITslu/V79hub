import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "tsx/esm/api";
register();
const { readHubView, hubViewUrl, canAccessHubView } = await import("../src/lib/hubNavigation.ts");
const app = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");

const owner = { platformOperator: true, permissions: ["overview"], ownerAgent: true };
const customer = { platformOperator: false, permissions: ["overview", "connections"] };
const viewer = { platformOperator: false, permissions: ["overview"] };
const views = ["overview","dashboard","connections","team","security","billing","admin","users","assistant"];

test("refresh can restore every valid page from URL", () => {
  for (const view of views) {
    const href = hubViewUrl("https://hub.v79sl.com/?campaign=pilot#safe", view);
    const next = new URL("https://hub.v79sl.com" + href);
    assert.equal(readHubView(next.search), view);
    assert.equal(next.searchParams.get("campaign"), "pilot");
    assert.equal(next.hash, "#safe");
  }
});
test("invalid and adversarial URL view selectors resolve to safe overview", () => {
  for (const bad of ["", "admin/edit", "prototype", "constructor", "__proto__", "<script>"]) {
    assert.equal(readHubView("?view=" + encodeURIComponent(bad)), "overview");
  }
  assert.equal(readHubView(""), "overview");
});
test("payment return always opens billing, and leaving billing does not reopen it", () => {
  assert.equal(readHubView("?view=connections&payment=success"), "billing");
  const next = hubViewUrl("https://hub.v79sl.com/?view=billing&payment=success&order=123", "connections");
  assert.equal(readHubView(new URL("https://hub.v79sl.com" + next).search), "connections");
  assert.ok(!next.includes("payment="));
  assert.ok(next.includes("order=123"));
});
test("invitation, team invitation and reset parameters are not erased by navigation", () => {
  for (const query of ["invite=abc", "teamInvite=abc", "reset=abc"]) {
    const after = new URL(hubViewUrl("https://hub.v79sl.com/?" + query, "security"), "https://hub.v79sl.com");
    assert.equal(after.searchParams.get(query.split("=")[0]), "abc");
  }
  assert.ok(hubViewUrl("https://hub.v79sl.com/?a=1#invite=abc","team").endsWith("#invite=abc"));
});
test("URL cannot bypass platform admin, user manager, or owner assistant permissions", () => {
  for (const view of ["admin","users","assistant","billing","security","team"]) {
    assert.equal(canAccessHubView(view, viewer), false);
    assert.equal(canAccessHubView(view, null), false);
  }
  assert.equal(canAccessHubView("admin", customer), false);
  assert.equal(canAccessHubView("users", customer), false);
  assert.equal(canAccessHubView("assistant", customer), false);
  assert.equal(canAccessHubView("connections", customer), true);
  assert.equal(canAccessHubView("connections", viewer), false);
  for (const view of views) assert.equal(canAccessHubView(view, owner), true);
});
test("frontend uses pushState on navigation, popstate on Back, replaceState on login/logout", () => {
  assert.ok(app.includes('window.addEventListener("popstate", onPopState)'));
  assert.ok(app.includes('window.removeEventListener("popstate", onPopState)'));
  assert.ok(app.includes('window.history.pushState(window.history.state, "", url)'));
  assert.ok(app.includes('window.history.replaceState(window.history.state, "", hubViewUrl(window.location.href, authorizedView))'));
  assert.ok(app.includes('const canView = (view: ViewState) => canAccessHubView(view, user)'));
  assert.ok(app.includes('if (!canAccessHubView(view, user)) return;'));
});
test("existing MFA, SSO, invite and payment return integrations are retained", () => {
  for (const marker of ['<Login onLoginSuccess={handleLoginSuccess}', '<InviteAcceptance', '<TeamInviteAcceptance',
    'onCancel={() => window.location.assign("/")}', 'const inviteToken =', 'const teamInviteToken =',
    'fetch("/api/auth/me"', 'fetch("/api/auth/logout"', 'fetch("/api/ecosystem/apps"']) {
    assert.ok(app.includes(marker), marker);
  }
});
