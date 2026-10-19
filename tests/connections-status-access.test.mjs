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
  assert.match(scoped, /canReadConnectionsStatus\\(\\{/);
  assert.match(scoped, /assigned: hasHubPermission\\(session\\.userId, session\\.organizationId, "connections"\\)/);
  assert.match(scoped, /verifiedPlatformOwner: isPlatformOperatorIdentity\\(session\\.userId, session\\.organizationId\\)/);
  assert.match(scoped, /return res\\.status\\(403\\)\\.json\\(\\{ error: "Permission denied" \\}\\)/);
  assert.doesNotMatch(scoped, /requirePermission\\("connections"\\)/);
  assert.match(source, /function isPlatformOperatorIdentity\\(userId: string, organizationId: string\\)/);
});
test("browser My Apps visibility and status URL remain unchanged", () => {
  assert.match(frontend, /isAdmin && \\["connections", "team", "security", "billing"\\]\\.includes\\(view\\)/);
  assert.match(sidebar, /user\\.platformOperator === true && \\["connections", "team", "security", "billing"\\]\\.includes\\(view\\)/);
  assert.match(connections, /fetch\\("\\/api\\/connections\\/status"/);
});
