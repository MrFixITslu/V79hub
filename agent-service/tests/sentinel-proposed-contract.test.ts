import test from "node:test";
import assert from "node:assert/strict";
import { parseProposedSentinelSummary } from "../src/sentinel-proposed-contract.js";

const now = Date.parse("2026-10-10T23:40:00Z");
const payload = () => ({
  schemaVersion: 1, organizationId: "v79owner",
  observedAt: "2026-10-10T23:39:30Z",
  counts: {
    monitoredDevices: 6, unreachableDevices: 1,
    criticalOpenIncidents: 2, warningOpenIncidents: 3,
  },
});

test("valid synthetic V79 owner aggregate remains unverified and not executable", () => {
  const candidate = parseProposedSentinelSummary(payload(), "v79owner", now);
  assert.equal(candidate.state, "candidate_unverified");
  assert.equal(candidate.readyForExecutiveUse, false);
  assert.deepEqual(candidate.counts, payload().counts);
  assert.ok(!JSON.stringify(candidate).includes("organizationId"));
  assert.ok(!JSON.stringify(candidate).includes("signed"));
});

test("synthetic cross-organization, invalid owner, and extra customer data fail closed", () => {
  assert.equal(parseProposedSentinelSummary(payload(), "customer_other", now).state, "invalid");
  assert.equal(parseProposedSentinelSummary(payload(), "bad", now).state, "invalid");
  assert.equal(parseProposedSentinelSummary({ ...payload(), tenantData: "private" }, "v79owner", now).state, "invalid");
  const x = payload() as ReturnType<typeof payload> & { customerEmail?: string };
  x.customerEmail = "sensitive@example.invalid";
  const result = parseProposedSentinelSummary(x, "v79owner", now);
  assert.equal(result.state, "invalid");
  assert.ok(!JSON.stringify(result).includes("sensitive@example.invalid"));
});

test("no packet bodies, IP addresses, incident text or unallowlisted counters permitted", () => {
  const data = payload();
  const withPacket = { ...data, counts: { ...data.counts, rawPacket: "binary-customer-traffic" } };
  assert.equal(parseProposedSentinelSummary(withPacket, "v79owner", now).state, "invalid");
  const withIp = { ...data, counts: { ...data.counts, sourceIP: "10.0.0.42" } };
  assert.equal(parseProposedSentinelSummary(withIp, "v79owner", now).state, "invalid");
  assert.ok(!JSON.stringify(parseProposedSentinelSummary(withIp,"v79owner",now)).includes("10.0.0.42"));
});

test("bad counts, negative numbers, fake values, and inconsistent device aggregates rejected", () => {
  assert.equal(parseProposedSentinelSummary({
    ...payload(), counts: { ...payload().counts, criticalOpenIncidents: -1 },
  }, "v79owner", now).state, "invalid");
  assert.equal(parseProposedSentinelSummary({
    ...payload(), counts: { ...payload().counts, warningOpenIncidents: "999" },
  }, "v79owner", now).state, "invalid");
  assert.equal(parseProposedSentinelSummary({
    ...payload(), counts: { ...payload().counts, monitoredDevices: 0, unreachableDevices: 1 },
  }, "v79owner", now).state, "invalid");
  assert.equal(parseProposedSentinelSummary({
    ...payload(), counts: { ...payload().counts, monitoredDevices: 1_000_001 },
  }, "v79owner", now).state, "invalid");
});

test("stale, future-dated, undated, malformed and unparseable observations never become candidates", () => {
  assert.equal(parseProposedSentinelSummary({
    ...payload(), observedAt: "2026-10-10T23:10:00Z",
  }, "v79owner", now).state, "stale");
  assert.equal(parseProposedSentinelSummary({
    ...payload(), observedAt: "2026-10-11T00:10:00Z",
  }, "v79owner", now).state, "unknown_time");
  assert.equal(parseProposedSentinelSummary({
    ...payload(), observedAt: "not-a-date",
  }, "v79owner", now).state, "unknown_time");
  assert.equal(parseProposedSentinelSummary({
    ...payload(), observedAt: null,
  }, "v79owner", now).state, "unknown_time");
});

test("zero is a valid synthetic observation, not proof of real-time Sentinel health", () => {
  const x = payload();
  x.counts = { monitoredDevices: 0, unreachableDevices: 0, criticalOpenIncidents: 0, warningOpenIncidents: 0 };
  const result = parseProposedSentinelSummary(x,"v79owner",now);
  assert.equal(result.state,"candidate_unverified");
  assert.equal(result.readyForExecutiveUse,false);
  assert.equal(result.counts?.criticalOpenIncidents,0);
});
