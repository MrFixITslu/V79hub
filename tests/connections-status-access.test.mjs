import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { canReadConnectionsStatus } from "../server/connections-status-access.mjs";

const source = readFileSync(new URL("../server.ts", import.meta.url), "utf8");
const frontend = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const sidebar = readFileSync(new URL("../src/components/Sidebar.tsx", import.meta.url), "utf8");
const connections = readFileSync(new URL("../src/components/WorkspaceConnections.tsx", import.meta.url), "utf8");

test("user with explicit connections permission stays allowed", () => {
  assert.equal(canReadConnectionsStatus({ assigned: true, verifiedPlatformOwner: false }), true);
});
test("verified platform owner with legacy restricted permissions is allowed", () => {
  assert.equal(canReadConnectionsStatus({ assigned: false, verifiedPlatformOwner: true }), true);
});
test("unauthorized users stay blocked; truthy strings are not sufficient", () => {
  for (const x of [undefined, null, false, "true", 1, {}, []]) {
    assert.equal(canReadConnectionsStatus({ assigned: x, verifiedPlatformOwner: false }), false);
    assert.equal(canReadConnectionsStatus({ assigned: false, verifiedPlatformOwner: x }), false);
  }
  assert.equal(canReadConnectionsStatus(), false);
});
test("status route is authenticated and no global permission exception is added", () => {
  const auth = source.indexOf('app.use("/api", requireAuth);');
  const route = source.indexOf('app.get("/api/connections/status",');
  assert.ok(auth > 0 && route > auth, "session authentication must precede route");
  const scoped = source.slice(route, route + 1000);
  for (const marker of [
    'canReadConnectionsStatus({',
    'assigned: hasHubPermission(session.userId, session.organizationId, "connections")',
    'verifiedPlatformOwner: isPlatformOperatorIdentity(session.userId, session.organizationId)',
    'return res.status(403).json({ error: "Permission denied" })',
  ]) assert.ok(scoped.includes(marker), marker);
  assert.ok(!scoped.includes('requirePermission("connections")'));
  assert.ok(source.includes("function isPlatformOperatorIdentity(userId: string, organizationId: string)"));
});
test("browser My Apps visibility and status URL remain unchanged", () => {
  const navigation = readFileSync(new URL("../src/lib/hubNavigation.ts", import.meta.url), "utf8");
  assert.ok(frontend.includes("const canView = (view: ViewState) => canAccessHubView(view, user)"));
  assert.ok(navigation.includes('user.platformOperator === true &&'));
  assert.ok(navigation.includes('["connections", "team", "security", "billing"].includes(view)'));
  assert.ok(sidebar.includes('user.platformOperator === true && ["connections", "team", "security", "billing"].includes(view)'));
  assert.ok(connections.includes('fetch("/api/connections/status"'));
});
