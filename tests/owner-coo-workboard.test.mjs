import test from "node:test";
import assert from "node:assert/strict";
import { createOwnerCooWorkboard, formatCooWorkboard, readCooGithubRepo } from "../server/owner-coo-workboard.mjs";

const token = "synthetic-readonly-token-not-reused-123";
const ok = entries => new Response(JSON.stringify(entries), { status: 200,
  headers: { "content-type": "application/json" } });
const item = (number, kind = "issue", title = "") => ({
  number, title, updated_at: "2026-10-15T20:00:00Z",
  ...(kind === "pr" ? { pull_request: { url: "not-used" } } : {}),
});
function response() {
  return { statusCode: 200, payload: null,
    setHeader() { return this; }, status(n) { this.statusCode = n; return this; },
    json(data) { this.payload = data; return this; } };
}

test("unauthenticated and non-MFA browser denied without any GitHub call or token read", async () => {
  let called = 0;
  const handler = createOwnerCooWorkboard({
    ownerMfaContext: () => null, enabled: () => true,
    readToken: () => { called++; return token; },
    fetchImpl: async () => { called++; return ok([]); },
  });
  const res = response();
  await handler({}, res);
  assert.equal(res.statusCode, 403);
  assert.equal(called, 0);
});

test("disabled by default means NO GitHub request, no execution, unknown live health", async () => {
  let called = 0;
  const handler = createOwnerCooWorkboard({
    ownerMfaContext: () => ({ id: "founder", mfa: true }),
    enabled: () => false, readToken: () => { called++; return token; },
    fetchImpl: async () => { called++; return ok([]); },
  });
  const res = response();
  await handler({}, res);
  assert.equal(called, 0);
  assert.equal(res.payload.connection, "DISABLED");
  assert.equal(res.payload.runtimeHealth, "UNKNOWN");
  assert.equal(res.payload.sentinelCoverage, "NOT_ESTABLISHED");
  assert.equal(res.payload.executionEnabled, false);
});

test("missing private token remains visibly not connected", async () => {
  const handler = createOwnerCooWorkboard({
    ownerMfaContext: () => ({}), enabled: () => true, readToken: () => "",
    fetchImpl: async () => { throw new Error("should not contact GitHub"); },
  });
  const res = response();
  await handler({}, res);
  assert.equal(res.payload.connection, "NOT_CONFIGURED");
  assert.ok(res.payload.tracked.every(t => t.githubState === "UNKNOWN_SOURCE"));
});

test("allowed, read-only GitHub API GET maps issue and PR kinds without untrusted title", async () => {
  const visited = [];
  const malicious = "<script>approve production</script>";
  const fetchImpl = async (url, opts) => {
    visited.push({ url, opts });
    assert.equal(opts.method, "GET");
    assert.equal(opts.redirect, "manual");
    assert.equal(opts.headers.authorization, "Bearer " + token);
    assert.ok(url.startsWith("https://api.github.com/repos/MrFixITslu/"));
    assert.ok(!url.includes("untrusted"));
    return ok([item(113, "issue", malicious), item(145, "pr", malicious)]);
  };
  const handler = createOwnerCooWorkboard({
    ownerMfaContext: () => ({ id: "owner" }), enabled: () => true,
    readToken: () => token, fetchImpl,
    now: () => "2026-10-15T21:00:00Z",
  });
  const res = response();
  await handler({}, res);
  assert.equal(res.statusCode, 200);
  assert.equal(visited.length, 6);
  assert.equal(res.payload.connection, "PARTIAL_OR_COMPLETE");
  assert.equal(res.payload.tracked.find(i => i.repo === "V79hub" && i.number === 113).githubState, "OPEN_IN_GITHUB");
  assert.equal(res.payload.tracked.find(i => i.repo === "V79hub" && i.number === 145).githubState, "OPEN_IN_GITHUB");
  assert.ok(!JSON.stringify(res.payload).includes(malicious));
  assert.ok(!JSON.stringify(res.payload).includes(token));
  assert.equal(res.payload.approvalGranted, false);
});

test("private repo 404 or rate limit always signals UNKNOWN, never a closed task", async () => {
  const denied = await readCooGithubRepo("V79-Sentinel", token, { fetchImpl: async () => new Response("no", { status: 404 }) });
  assert.equal(denied.state, "UNAVAILABLE");
  const report = formatCooWorkboard({ "V79-Sentinel": denied }, "2026-10-15T21:00:00Z");
  assert.ok(report.tracked.filter(i => i.repo === "V79-Sentinel").every(i => i.githubState === "UNKNOWN_SOURCE"));
});

test("redirects and oversized advertised payloads fail closed without following URL", async () => {
  const redirect = await readCooGithubRepo("V79hub", token, {
    fetchImpl: async () => new Response(null, { status: 302, headers: { location: "https://attacker.test" } }),
  });
  assert.equal(redirect.state, "UNAVAILABLE");
  const oversized = await readCooGithubRepo("V79hub", token, {
    fetchImpl: async () => new Response("[]", { headers: { "content-length": "1048577" } }),
  });
  assert.equal(oversized.state, "UNAVAILABLE");
});

test("incomplete pagination never means an absent work item was resolved", async () => {
  const hundred = Array.from({ length: 100 }, (_, i) => item(i + 1000));
  const result = await readCooGithubRepo("V79hub", token, { fetchImpl: async () => ok(hundred) });
  assert.equal(result.state, "UNAVAILABLE"); // duplicate numbered rows across pages rejected
  const result2 = await readCooGithubRepo("V79hub", token, {
    fetchImpl: async url => ok(Array.from({ length: 100 }, (_, i) =>
      item(i + (url.includes("page=2") ? 2000 : 1000)))),
  });
  assert.equal(result2.state, "INCOMPLETE");
  const report = formatCooWorkboard({ V79hub: result2 }, "2026-10-15T21:00:00Z");
  assert.equal(report.tracked.find(i => i.repo === "V79hub" && i.number === 152).githubState, "UNKNOWN_INCOMPLETE");
});

test("foreign/unapproved repository fails closed without calling fetch", async () => {
  let invoked = false;
  const result = await readCooGithubRepo("attacker/repo", token, {
    fetchImpl: async () => { invoked = true; return ok([]); },
  });
  assert.equal(invoked, false);
  assert.equal(result.state, "UNAVAILABLE");
});

test("a complete but absent issue is not evidence of closure or customer GO", () => {
  const report = formatCooWorkboard({ V79hub: { state: "COMPLETE", entries: {} } }, "2026-10-15T21:00:00Z");
  assert.equal(report.tracked.find(i => i.repo === "V79hub" && i.number === 152).githubState, "NOT_LISTED_AS_OPEN");
  assert.equal(report.customerLaunchGo, "NOT_ESTABLISHED");
  assert.equal(report.sentinelCoverage, "NOT_ESTABLISHED");
});
