import test from "node:test";
import assert from "node:assert/strict";
import { buildEvidenceLedger, compactFromEvidence } from "../src/evidence.js";
import { prepareExecutiveHandoff } from "../src/executive-handoff.js";
import { getWorkforceSpecialist } from "../src/workforce.js";

const NOW = Date.parse("2026-10-12T00:00:00.000Z");
const at = (offsetMs: number) => new Date(NOW + offsetMs).toISOString();
function snapshot(envelopeTime: string | null, productTime: string | null) {
  return {
    generatedAt: envelopeTime,
    hubAdmin: { users: 2, activeSessions: 1 },
    business: {
      ffpro: {
        status: "ok", sourceReportedAt: productTime,
        metrics: { currentMonthNet: -42, customerEmail: "private@example.invalid" },
      },
    },
    connections: { ffpro: { status: "online" } },
    platform: {},
  };
}
function findFFPRO(envelopeTime: string | null, productTime: string | null) {
  const ledger = buildEvidenceLedger(
    snapshot(envelopeTime, productTime), getWorkforceSpecialist("owner"), NOW);
  const source = ledger.records.find(row => row.system === "ffpro" &&
    row.source === "signed_product_summary");
  assert.ok(source);
  return { ledger, source };
}

test("G1 product observation cannot postdate collecting Hub envelope by more than 120s", () => {
  // Product observation is apparently current, but the collecting envelope
  // precedes it by 9 minutes: these two source claims cannot both be true.
  const invalid = findFFPRO(at(-600_000), at(-60_000));
  assert.equal(invalid.source.state, "unknown");
  assert.equal(invalid.source.ageSeconds, null);
  const trusted = compactFromEvidence(invalid.ledger);
  assert.deepEqual(trusted.systems.ffpro.metrics, {});
  assert.ok(!trusted.prioritySignals.some(x => x.code === "finance_negative_month_net"));
  const handoff = prepareExecutiveHandoff(invalid.ledger);
  assert.ok(!handoff.cooReport.findings.some(x => x.id === "ffpro:currentMonthNet"));
  assert.ok(!JSON.stringify(handoff).includes("private@example.invalid"));
});

test("G1 preserves exactly 120-second source/collector skew but rejects 120.001s", () => {
  const envelope = at(-500_000);
  const allowed = findFFPRO(envelope, at(-380_000));
  assert.equal(allowed.source.state, "available");
  assert.ok(prepareExecutiveHandoff(allowed.ledger).cooReport.findings.some(x =>
    x.id === "ffpro:currentMonthNet"));
  const disallowed = findFFPRO(envelope, at(-379_999));
  assert.equal(disallowed.source.state, "unknown");
  assert.deepEqual(compactFromEvidence(disallowed.ledger).systems.ffpro.metrics, {});
});

test("G1 requires an envelope collection timestamp even in direct evidence ledger calls", () => {
  const undated = findFFPRO(null, at(-60_000));
  assert.equal(undated.source.state, "unknown");
  assert.ok(!prepareExecutiveHandoff(undated.ledger).cooReport.findings.some(x =>
    x.id === "ffpro:currentMonthNet"));
});

test("G1 source freshness cutoffs use milliseconds, not rounded age seconds", () => {
  const within = findFFPRO(at(0), at(-900_000));
  assert.equal(within.source.state, "available");
  const beyond = findFFPRO(at(0), at(-900_001));
  assert.equal(beyond.source.state, "stale");
  assert.deepEqual(compactFromEvidence(beyond.ledger).systems.ffpro.metrics, {});

  const ownerWithin = buildEvidenceLedger(
    snapshot(at(-900_000), at(-900_000)), getWorkforceSpecialist("owner"), NOW
  ).records.find(x => x.source === "hub_owner_summary");
  const ownerBeyond = buildEvidenceLedger(
    snapshot(at(-900_001), at(-900_001)), getWorkforceSpecialist("owner"), NOW
  ).records.find(x => x.source === "hub_owner_summary");
  assert.equal(ownerWithin?.state, "available");
  assert.equal(ownerBeyond?.state, "unknown");
});
