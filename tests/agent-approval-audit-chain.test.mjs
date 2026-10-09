import test from "node:test";
import assert from "node:assert/strict";
import { createAgentApprovalAuditChain, verifyAgentApprovalAuditLinkage, prepareAgentApprovalAuditKeyRotation } from "../server/agent-approval-audit-chain.mjs";

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

test("externally retained checkpoint detects a deleted signed tail", () => {
  const events=[];
  audit.append(events, fakeProposal(), "synthetic-user");
  const oldCheckpoint = audit.checkpoint(events);
  assert.equal(oldCheckpoint.count,1);
  assert.equal(oldCheckpoint.headMac.length,64);
  assert.equal(audit.verifyCheckpoint(events,oldCheckpoint),true);
  audit.append(events, fakeProposal({ status:"approved",revision:2 }), "synthetic-user");
  const newCheckpoint = audit.checkpoint(events);
  assert.equal(audit.verifyCheckpoint(events,newCheckpoint),true);
  assert.equal(audit.verifyCheckpoint(events,oldCheckpoint),false);
  const truncated=events.slice(0,1);
  assert.equal(audit.verify(truncated),true);
  assert.equal(audit.verifyCheckpoint(truncated,newCheckpoint),false);
  assert.equal(audit.verifyCheckpoint(events,{...newCheckpoint,count:-1}),false);
  assert.equal(audit.verifyCheckpoint(events,{...newCheckpoint,headMac:"a".repeat(64)}),false);
});

test("offline audit-key rotation re-signs a validated copy without mutating a source or its proposal snapshots", () => {
  const oldKey = "synthetic-old-offline-audit-key-0123456789";
  const newKey = "synthetic-new-offline-audit-key-9876543210";
  const source = createAgentApprovalAuditChain(oldKey);
  const target = createAgentApprovalAuditChain(newKey);
  const one = fakeProposal({ id: "synthetic-plan-1", status: "approved", revision: 2 });
  const two = fakeProposal({ id: "synthetic-plan-2", status: "pending", revision: 1 });
  const events = [];
  source.append(events, fakeProposal({id:one.id}), "synthetic-user");
  source.append(events, one, "synthetic-user");
  source.append(events, two, "synthetic-user");
  const before = structuredClone(events);
  const proposals = [one, two];
  const originalProposals = structuredClone(proposals);
  assert.equal(verifyAgentApprovalAuditLinkage(events, proposals), true);
  const result = prepareAgentApprovalAuditKeyRotation({
    events, proposals, oldKey, newKey,
  });
  assert.equal(result.events.length, 3);
  assert.equal(source.verify(result.events), false);
  assert.equal(target.verify(result.events), true);
  assert.equal(verifyAgentApprovalAuditLinkage(result.events, proposals), true);
  assert.deepEqual(events, before, "source audit remains unchanged");
  assert.deepEqual(proposals, originalProposals, "proposal snapshots remain unchanged");
  assert.notEqual(result.replacementCheckpoint.headMac, result.previousCheckpoint.headMac);
  assert.equal(result.previousCheckpoint.count, 3);
  assert.equal(result.replacementCheckpoint.count, 3);
  assert.equal(source.verifyCheckpoint(events, result.previousCheckpoint), true);
  assert.equal(target.verifyCheckpoint(result.events, result.replacementCheckpoint), true);
  assert.equal(source.verifyCheckpoint(events, result.replacementCheckpoint), false);
  for (let i = 0; i < events.length; i++) {
    for (const [key, value] of Object.entries(events[i])) {
      if (key === "mac" || key === "previousMac") continue;
      assert.deepEqual(result.events[i][key], value, "signed metadata preserved: " + key);
    }
  }
  assert.equal(JSON.stringify(result).includes(oldKey), false);
  assert.equal(JSON.stringify(result).includes(newKey), false);
});

test("audit-key rotation rejects changed, truncated or tampered histories and mismatched snapshots", () => {
  const oldKey = "synthetic-old-offline-audit-key-0123456789";
  const newKey = "synthetic-new-offline-audit-key-9876543210";
  const old = createAgentApprovalAuditChain(oldKey);
  const events = [];
  old.append(events, fakeProposal(), "synthetic-user");
  old.append(events, fakeProposal({status:"approved",revision:2}), "synthetic-user");
  const approved = fakeProposal({status:"approved",revision:2});
  const go = (patch={}) => prepareAgentApprovalAuditKeyRotation({
    events, proposals:[approved],oldKey,newKey,...patch,
  });
  assert.equal(go().events.length,2);
  const corrupt = structuredClone(events);
  corrupt[1].operation = "draft_marketing_campaign";
  assert.throws(() => go({events:corrupt}), /invalid/);
  assert.throws(() => go({events:events.slice(0,1)}), /invalid/);
  assert.throws(() => go({proposals:[fakeProposal()]}), /invalid/);
  assert.throws(() => go({proposals:[{...approved,executionStatus:"executed"}]}), /invalid/);
  assert.throws(() => go({oldKey:"incorrect-old-key-1234567890123456"}), /invalid/);
  assert.throws(() => go({oldKey,newKey:oldKey}), /Separate audit keys/);
  assert.throws(() => go({newKey:"short"}), /Separate audit keys/);
  assert.equal(old.verify(events),true,"failed rotation attempts may not alter source");
});

test("offline key rotation of a truly empty proposal history is explicitly verifiable", () => {
  const oldKey = "synthetic-old-offline-audit-key-0123456789";
  const newKey = "synthetic-new-offline-audit-key-9876543210";
  const result = prepareAgentApprovalAuditKeyRotation({
    events:[],proposals:[],oldKey,newKey,
  });
  assert.deepEqual(result.events,[]);
  assert.equal(result.previousCheckpoint.count,0);
  assert.equal(result.replacementCheckpoint.count,0);
  assert.equal(result.previousCheckpoint.headMac,result.replacementCheckpoint.headMac,
    "an empty chain cannot distinguish keys; explicit key custody is still required");
});
