import test from "node:test";
import assert from "node:assert/strict";
import { parseSignedMissionAggregateCandidate } from "../src/sentinel-signed-aggregate.js";

const now = Date.parse("2026-10-10T23:40:00Z");
const specimen = () => ({
  schemaVersion: 1,
  source: "local-mission-control",
  observedAt: "2026-10-10T23:39:40.000Z",
  monitorMode: "staging",
  counts: { servicesObserved: 3, up: 1, down: 1, degraded: 1, unknown: 0 },
});

test("only aggregate service-state totals survive and remain unverified", () => {
  const result = parseSignedMissionAggregateCandidate(specimen(), now);
  assert.equal(result.state, "candidate_unverified");
  assert.equal(result.sourceVerified, false);
  assert.equal(result.readyForExecutiveUse, false);
  assert.deepEqual(result.counts, specimen().counts);
});

test("reject any raw per-service fields, names, QA records and private network addresses", () => {
  const p = specimen();
  for (const extra of [
    { services: [{ name: "Secret Client", address: "10.0.0.3" }] },
    { qa: { results: [{ name: "login flow" }] } },
    { incidents: [{ description: "Private issue" }] },
  ]) {
    const result = parseSignedMissionAggregateCandidate({ ...p, ...extra }, now);
    assert.equal(result.state, "invalid");
    assert.ok(!JSON.stringify(result).includes("10.0.0.3"));
    assert.ok(!JSON.stringify(result).includes("Secret Client"));
  }
});

test("reject extra counts and inconsistent totals, unknown or oversized counts", () => {
  const p = specimen();
  const bad = [
    { ...p.counts, observedAddress: "192.168.1.2" },
    { ...p.counts, servicesObserved: 4 },
    { ...p.counts, up: -1 },
    { ...p.counts, down: 0.1 },
    { ...p.counts, unknown: 25 },
    { ...p.counts, degraded: "100" },
  ];
  for (const counts of bad) {
    assert.equal(parseSignedMissionAggregateCandidate({ ...p, counts }, now).state, "invalid");
  }
});

test("zero observed services is unknown data, not healthy", () => {
  const p = specimen();
  const result = parseSignedMissionAggregateCandidate({
    ...p,
    counts: { servicesObserved: 0, up: 0, down: 0, degraded: 0, unknown: 0 },
  }, now);
  assert.equal(result.state, "no_data");
});

test("stale, unknown, normalized impossible calendar dates and future reports fail", () => {
  const p = specimen();
  const cases = [
    ["2026-10-10T23:00:00.000Z", "stale"],
    ["2026-02-30T23:00:00.000Z", "unknown_time"],
    ["2026-10-11T00:00:00.000Z", "unknown_time"],
    ["2026-10-10T23:30:00Z", "unknown_time"],
  ] as const;
  for (const [observedAt, status] of cases) {
    assert.equal(parseSignedMissionAggregateCandidate({ ...p, observedAt }, now).state, status);
  }
});

test("a monitor claiming live status does not become actionable without owner-signed source proof", () => {
  const result = parseSignedMissionAggregateCandidate({ ...specimen(), monitorMode: "live" }, now);
  assert.equal(result.state, "candidate_unverified");
  assert.equal(result.sourceVerified, false);
  assert.equal(result.readyForExecutiveUse, false);
});
