import test from "node:test";
import assert from "node:assert/strict";
import { createAgentApprovalAuditChain, verifyAgentApprovalAuditLinkage } from "../server/agent-approval-audit-chain.mjs";

const audit = createAgentApprovalAuditChain("synthetic-test-only-hmac-key-1234567890", {
  now: () => new Date("2026-10-09T12:00:00Z"),
  uuid: (() => { let i = 0; return () => "synthetic-event-" + (++i); })(),
});
const fakeProposal = (changes = {}) => ({
  id: "01234567-89ab-4cde-8000-0123456789ab",
  organizationId: "synthetic-owner-org", operation: "draft_operational_report",
  targetSystem: "hub", status: "pending", revision: 1,
  executionStatus: "disabled", ...changes,
});

test("keyed proposal audit survives serialised reload and records only bounded metadata", () => {
  const events = [];
  const e1 = audit.append(events, fakeProposal(), "synthetic-user");
  const e2 = audit.append(events, fakeProposal({ status: "approved", revision: 2 }), "synthetic-user");
  assert.equal(events.length, 2);
  assert.equal(e2.previousMac, e1.mac);
  assert.equal(e1.executionStatus, "disabled");
  assert.equal(events[0].rationale, undefined);
  assert.equal(audit.verify(structuredClone(JSON.parse(JSON.stringify(events)))), true);
  assert.deepEqual(audit.health(events), { integrity: "verified", count: 2, capacity: 10000 });
});

test("editing, swapping, inserting or deleting an intermediate event invalidates the audit chain", () => {
  const events = [];
  audit.append(events, fakeProposal(), "synthetic-user");
  audit.append(events, fakeProposal({ status: "approved", revision: 2 }), "synthetic-user");
  const altered = structuredClone(events);
  altered[0].status = "rejected";
  assert.equal(audit.verify(altered), false);
  const swapped = [events[1], events[0]];
  assert.equal(audit.verify(swapped), false);
  const removedFirst = [events[1]];
  assert.equal(audit.verify(removedFirst), false);
  const duplicated = [events[0], events[0]];
  assert.equal(audit.verify(duplicated), false);
  const inserted = [{ ...events[0], mac: "a".repeat(64) }, ...events];
  assert.equal(audit.verify(inserted), false);
  assert.throws(() => audit.append(altered, fakeProposal(), "synthetic-user"), /integrity/);
  assert.equal(altered.length, 2, "failed integrity checks must not mutate history");
});

test("wrong signing key and missing signing key fail closed", () => {
  const events = [];
  audit.append(events, fakeProposal(), "synthetic-user");
  const different = createAgentApprovalAuditChain("different-only-test-signing-key-123456");
  assert.equal(different.verify(events), false);
  assert.equal(different.health(events).integrity, "unavailable");
  const missing = createAgentApprovalAuditChain("");
  assert.equal(missing.verify([]), false);
  assert.throws(() => missing.append([], fakeProposal(), "synthetic-user"), /integrity/);
});

test("only decision-only proposal metadata is eligible for signed append", () => {
  for (const invalid of [
    fakeProposal({ executionStatus: "executed" }),
    fakeProposal({ status: "dispatch" }),
    fakeProposal({ revision: 0 }),
    fakeProposal({ organizationId: "" }),
  ]) {
    const items = [];
    assert.throws(() => audit.append(items, invalid, "synthetic-user"), /Invalid/);
    assert.equal(items.length, 0);
  }
});

test("audit append rejects saturation without losing the prior record", () => {
  const events = [];
  audit.append(events, fakeProposal(), "synthetic-user");
  const intact = events[0];
  const corrupt = [intact, { ...intact, id: "tampered" }];
  assert.throws(() => audit.append(corrupt, fakeProposal(), "synthetic-user"), /integrity/);
  assert.equal(events.length, 1);
  assert.equal(events[0], intact);
});

test("approval audit linkage detects a deleted signed tail or edited proposal snapshot", () => {
  const events = [];
  const pending = fakeProposal();
  const approved = fakeProposal({ status: "approved", revision: 2 });
  audit.append(events, pending, "synthetic-user");
  audit.append(events, approved, "synthetic-user");
  assert.equal(verifyAgentApprovalAuditLinkage(events, [approved]), true);
  const truncated = events.slice(0,1);
  assert.equal(audit.verify(truncated), true,
    "an internally valid shortened chain alone cannot detect its missing tail");
  assert.equal(verifyAgentApprovalAuditLinkage(truncated, [approved]), false);
  assert.equal(verifyAgentApprovalAuditLinkage(events, [pending]), false);
  assert.equal(verifyAgentApprovalAuditLinkage(events, []), false);
  assert.equal(verifyAgentApprovalAuditLinkage(events, [{ ...approved, operation: "draft_finance_review" }]), false);
  assert.equal(verifyAgentApprovalAuditLinkage([], []), true);
});
