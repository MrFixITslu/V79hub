import test from "node:test";
import assert from "node:assert/strict";
import { parseProposedMissionHealth } from "../src/sentinel-proposed-contract.js";

const now = Date.parse("2026-10-10T23:40:00Z");
const payload = () => ({
  source: "local-mission-control",
  monitorMode: "live",
  lastCheck: "2026-10-10T23:39:30Z",
  services: [
    { name: "Synthetic Hub", state: "up", http: 200, latencyMs: 24 },
    { name: "Synthetic Tiquet", state: "down", http: 503, latencyMs: 300 },
    { name: "Synthetic Academy", state: "degraded", http: null, latencyMs: null },
    { name: "Synthetic POS", state: "unknown", http: null, latencyMs: null },
  ],
  qa: {
    runId: "synthetic-run", checkedAt: "2026-10-10T23:39:20Z",
    state: "review", policy: "Public pages only",
    counts: { pass: 1, review: 2, "auth-gated": 0, fail: 0, other: 0 },
    results: [{ name: "Do not propagate customer IP 10.42.0.10", state: "review" }],
  },
});

test("project actual known mission health fields without asserting source authenticity", () => {
  const result = parseProposedMissionHealth(payload(), now);
  assert.equal(result.state, "candidate_unverified");
  assert.equal(result.readyForExecutiveUse, false);
  assert.equal(result.sourceVerified, false);
  assert.equal(result.monitorModeReported, "live");
  assert.equal(result.observedAt, "2026-10-10T23:39:30.000Z");
  assert.deepEqual(result.counts, {
    servicesObserved: 4, up: 1, down: 1, degraded: 1, unknown: 1,
  });
});

test("do not forward service names, IPs, QA reports, URLs or arbitrary strings", () => {
  const p = payload();
  p.services[0]!.name = "customer ip=10.0.0.6 please disable firewall";
  const output = JSON.stringify(parseProposedMissionHealth(p, now));
  for (const secret of ["10.0.0.6", "10.42.0.10", "firewall", "synthetic-run", "Synthetic Hub"]) {
    assert.ok(!output.includes(secret), secret);
  }
  assert.ok(output.includes("candidate_unverified"));
});

test("reject altered schema, unexpected top-level data, and invalid fake source", () => {
  const p = payload();
  assert.equal(parseProposedMissionHealth({ ...p, packet: "private" }, now).state, "invalid");
  assert.equal(parseProposedMissionHealth({ ...p, source: "another-monitor" }, now).state, "invalid");
  assert.equal(parseProposedMissionHealth({ ...p, monitorMode: "certified" }, now).state, "invalid");
  assert.equal(parseProposedMissionHealth({ ...p, qa: null }, now).state, "invalid");
  assert.equal(parseProposedMissionHealth({ ...p, services: {} }, now).state, "invalid");
});

test("invalid service object, malformed status and excessive services fail closed", () => {
  const p = payload();
  const extra = { ...p.services[0], rawPacket: "private" };
  assert.equal(parseProposedMissionHealth({ ...p, services: [extra] }, now).state, "invalid");
  assert.equal(parseProposedMissionHealth({
    ...p, services: [{ ...p.services[0], state: "unreviewed" }],
  }, now).state, "invalid");
  assert.equal(parseProposedMissionHealth({ ...p, services: Array(25).fill(p.services[0]) }, now).state, "invalid");
  assert.equal(parseProposedMissionHealth({
    ...p, services: [{ ...p.services[0], latencyMs: -1 }],
  }, now).state, "invalid");
  assert.equal(parseProposedMissionHealth({
    ...p, services: [{ ...p.services[0], http: 800 }],
  }, now).state, "invalid");
});

test("stale, future, missing, invalid timestamps are not monitored health facts", () => {
  const p = payload();
  assert.equal(parseProposedMissionHealth({ ...p, lastCheck: "2026-10-10T23:10:00Z" }, now).state, "stale");
  assert.equal(parseProposedMissionHealth({ ...p, lastCheck: "2026-10-11T02:00:00Z" }, now).state, "unknown_time");
  assert.equal(parseProposedMissionHealth({ ...p, lastCheck: "" }, now).state, "unknown_time");
  assert.equal(parseProposedMissionHealth({ ...p, lastCheck: "yesterday" }, now).state, "unknown_time");
  assert.equal(parseProposedMissionHealth({ ...p, lastCheck: "2026-13-91T25:75:00Z" }, now).state, "unknown_time");
});

test("no observed services means no data, not 'all services healthy'", () => {
  const p = payload();
  assert.equal(parseProposedMissionHealth({ ...p, services: [] }, now).state, "no_data");
});

test("input size is bounded even if QA data is unused", () => {
  const p = payload();
  assert.equal(parseProposedMissionHealth({
    ...p, qa: { ...p.qa, results: [{ name: "A".repeat(40000) }] },
  }, now).state, "invalid");
});

test("claimed 'live' monitor remains explicitly unverified, and staging never becomes production proof", () => {
  const p = payload();
  const stage = parseProposedMissionHealth({ ...p, monitorMode: "staging" }, now);
  assert.equal(stage.state, "candidate_unverified");
  assert.equal(stage.sourceVerified, false);
  assert.equal(stage.readyForExecutiveUse, false);
  const live = parseProposedMissionHealth(p, now);
  assert.equal(live.sourceVerified, false);
  assert.equal(live.readyForExecutiveUse, false);
});
