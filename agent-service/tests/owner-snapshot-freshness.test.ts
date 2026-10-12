import test from "node:test";
import assert from "node:assert/strict";
import { verifySignedOwnerSnapshot } from "../src/evidence.js";
import type { AgentContext } from "../src/context.js";

const owner: AgentContext = {
  userId: "synthetic-owner-identity",
  email: "synthetic-owner@example.invalid",
  organizationId: "synthetic-v79-org",
  organizationName: "Synthetic V79",
  allowedSystems: [],
  ownerAgent: true,
  hubAdmin: true,
};
const now = Date.parse("2026-10-11T23:00:00.000Z");
const stamp = (secondsDelta: number) => new Date(now + secondsDelta * 1000).toISOString();
function makeSnapshot(generatedAt: unknown, organizationId = owner.organizationId): unknown {
  return {
    owner: { email: owner.email, organizationId },
    generatedAt,
    // Product source timestamp by itself must not rescue an invalid envelope.
    business: { ffpro: { status: "ok", sourceReportedAt: stamp(0), metrics: { currentMonthNet: -12 } } },
  };
}

test("G1 Hub envelope accepts bounded current timestamps without losing tenant scope", () => {
  for (const delta of [-900, -30, 0, 100, 120]) {
    assert.doesNotThrow(() => verifySignedOwnerSnapshot(makeSnapshot(stamp(delta)), owner, now),
      "Allowed source age/skew: " + delta);
  }
  assert.throws(() => verifySignedOwnerSnapshot(
    makeSnapshot(stamp(0), "another-synthetic-org"), owner, now), /owner scope mismatch/);
  assert.throws(() => verifySignedOwnerSnapshot(
    makeSnapshot(stamp(0)), { ...owner, ownerAgent: false }, now), /owner scope mismatch/);
});

test("G1 Hub envelope rejects stale/future time even when nested source says current", () => {
  for (const delta of [-901, -86400, 121, 3600, 86400]) {
    assert.throws(() => verifySignedOwnerSnapshot(makeSnapshot(stamp(delta)), owner, now),
      /outside the allowed freshness window/, "Disallowed source age/skew: " + delta);
  }
});

test("G1 Hub envelope rejects missing, nonsensical or unauthorized observation time", () => {
  for (const stampValue of [null, undefined, 0, {}, "not-a-date", "", "2026-19-99"]) {
    assert.throws(() => verifySignedOwnerSnapshot(makeSnapshot(stampValue), owner, now),
      /collection time is invalid/);
  }
  assert.throws(() => verifySignedOwnerSnapshot(null, owner, now), /Missing signed owner evidence/);
});
