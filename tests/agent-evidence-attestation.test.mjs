import test from "node:test";
import assert from "node:assert/strict";
import { createAgentEvidenceAttestations } from "../server/agent-evidence-attestation.mjs";

const timestamp = "2026-10-09T10:00:00.000Z";
const owner = { organizationId: "owner-org", userId: "founder-user" };
const draft = {
  operation: "draft_inventory_review", targetSystem: "pos",
  summary: "Review current inventory thresholds",
  rationale: "Review signed aggregate POS inventory evidence before drafting any purchasing request.",
  evidenceRef: "pos:criticalReplenishmentItems",
  idempotencyKey: "synthetic-attestation-test-key-0001",
};
const finding = () => ({
  id: draft.evidenceRef, system: draft.targetSystem,
  title: draft.summary, nextStep: draft.rationale,
  evidence: { source: "signed_product_summary", metric: "criticalReplenishmentItems",
    value: 4, reportedAt: timestamp },
});
const response = () => ({
  investigation: { mode: "read-only", dataStatus: "available", findings: [finding()] },
  evidence: { mode: "read-only", records: [{
    system: "pos", state: "available", source: "signed_product_summary", reportedAt: timestamp,
    metrics: [{ key: "criticalReplenishmentItems", value: 4 }],
  }] },
});
const setup = () => {
  let clock = Date.parse("2026-10-09T10:01:00.000Z");
  let serial = 0;
  const service = createAgentEvidenceAttestations({
    now: () => clock,
    nonce: () => "synthetic-receipt-token-" + String(++serial).padStart(4,"0"),
  });
  return { service, advance: minutes => clock += minutes * 60_000 };
};

test("only a matching fresh, available ledger metric mints an owner-scoped receipt", () => {
  const { service } = setup();
  const result = service.decorate(response(), owner);
  const token = result.investigation.findings[0].evidenceAttestation;
  assert.match(token, /^synthetic-receipt-token-/);
  assert.equal(service.verify({ ...draft, evidenceAttestation: token }, owner).valid, true);
  assert.equal(service.verify({ ...draft, evidenceAttestation: token },
    { ...owner, organizationId: "other-tenant" }).valid, false);
  assert.equal(service.verify({ ...draft, evidenceAttestation: token },
    { ...owner, userId: "another-owner" }).valid, false);
  assert.equal(service.verify({ ...draft, evidenceAttestation: token,
    rationale: "A modified review rationale must never reuse old evidence." }, owner).valid, false);
  assert.equal(service.verify({ ...draft }, owner).valid, false);
  assert.equal(service.verify({ ...draft, evidenceRef: undefined }, owner).valid, true);
});

test("no receipt is issued for missing, stale, spoofed, or contradictory source evidence", () => {
  const { service } = setup();
  const variations = [
    value => { value.evidence.records[0].state = "stale"; },
    value => { value.evidence.records[0].metrics[0].value = 5; },
    value => { value.evidence.records[0].source = "unsourced_model_text"; },
    value => { value.investigation.findings[0].system = "tiquet"; },
    value => { value.investigation.findings[0].id = "tiquet:unknown"; },
    value => { value.investigation.findings[0].evidence.reportedAt = "2026-10-08T08:00:00.000Z"; },
    value => { value.investigation.dataStatus = "unavailable"; },
  ];
  for (const transform of variations) {
    const payload = response(); transform(payload);
    const result = service.decorate(payload, owner);
    assert.equal(result.investigation.findings[0].evidenceAttestation, undefined);
  }
});

test("caller-forged attestation is stripped from every forwarded finding", () => {
  const { service } = setup();
  const payload = response();
  payload.investigation.findings[0].evidenceAttestation = "forged-client-token";
  payload.evidence.records[0].state = "unavailable";
  const value = service.decorate(payload, owner);
  assert.equal(value.investigation.findings[0].evidenceAttestation, undefined);
});

test("a receipt cannot be reused for a different idempotency key or after expiry", () => {
  const { service, advance } = setup();
  const token = service.decorate(response(), owner).investigation.findings[0].evidenceAttestation;
  const input = { ...draft, evidenceAttestation: token };
  assert.equal(service.verify(input, owner).valid, true);
  assert.equal(service.bindIdempotencyKey(token, input.idempotencyKey), true);
  assert.equal(service.verify({ ...input, idempotencyKey: "different-attestation-key-0001" }, owner).valid, false);
  assert.equal(service.verify(input, owner).valid, true, "same-key retries remain idempotent");
  advance(11);
  assert.equal(service.verify(input, owner).valid, false);
});

test("bounded in-memory receipt capacity and missing source scope fail closed", () => {
  const service = createAgentEvidenceAttestations({
    now: () => Date.parse("2026-10-09T10:01:00.000Z"),
    maxEntries: 1,
    nonce: () => "synthetic-receipt-token-capacity",
  });
  const first = service.decorate(response(), owner);
  const second = service.decorate(response(), owner);
  assert.ok(first.investigation.findings[0].evidenceAttestation);
  assert.equal(second.investigation.findings[0].evidenceAttestation, undefined);
  const third = service.decorate(response(), { organizationId: "owner-org" });
  assert.equal(third.investigation.findings[0].evidenceAttestation, undefined);
});
