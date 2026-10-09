import test from "node:test";
import assert from "node:assert/strict";
import { createAgentProposal, decideAgentProposal } from "../server/agent-approval-ledger.mjs";
import { prepareSupervisedTiquetDraft } from "../server/agent-supervised-tiquet.mjs";

const now = new Date("2026-10-09T18:00:00Z");
const organizationId = "synthetic-org-00000001";
const owner = "synthetic-hub-owner-0001";
function approvedSupport() {
  const proposals = [];
  const created = createAgentProposal(proposals, {
    operation: "draft_support_reply", targetSystem: "tiquet",
    summary: "Prepare support review notes",
    rationale: "Review the ticket facts and obtain a human review before customer communication.",
    idempotencyKey: "stage4-tiquet-proposal-test-0001",
  }, { organizationId, actorUserId: owner, now });
  assert.equal(created.kind, "created");
  const decision = decideAgentProposal(proposals, {
    id: created.proposal.id, organizationId, actorUserId: owner,
    expectedRevision: 1, decision: "approve", now: new Date(+now + 1000),
  });
  assert.equal(decision.kind, "decided");
  return proposals[0];
}

test("an approved, unexpired support plan plus explicit ticket produces draft-only data", () => {
  const p = approvedSupport();
  const request = prepareSupervisedTiquetDraft(p, organizationId, owner, "ticket-1234", new Date(+now + 2000));
  assert.ok(request);
  assert.deepEqual(Object.keys(request).sort(), ["actorHubUserId", "content", "jobId", "organizationId", "proposalId"]);
  assert.equal(request.proposalId, p.id);
  assert.equal(request.jobId, "ticket-1234");
  assert.match(request.content, /NOT READY TO SEND/);
  assert.equal(Object.hasOwn(request, "recipient"), false);
  assert.equal(Object.hasOwn(request, "send"), false);
  assert.equal(Object.hasOwn(request, "publish"), false);
});

test("unsupported actions, tenant, actor, ticket and expired approvals fail closed", () => {
  const p = approvedSupport();
  const at = new Date(+now + 2000);
  assert.equal(prepareSupervisedTiquetDraft(p, "different-org-000001", owner, "ticket-1234", at), null);
  assert.equal(prepareSupervisedTiquetDraft(p, organizationId, "bad", "ticket-1234", at), null);
  assert.equal(prepareSupervisedTiquetDraft(p, organizationId, owner, "../unsafe", at), null);
  assert.equal(prepareSupervisedTiquetDraft(p, organizationId, owner, "", at), null);
  assert.equal(prepareSupervisedTiquetDraft(p, organizationId, owner, "ticket-1234", new Date(+now + 4*86400000)), null);
  assert.equal(prepareSupervisedTiquetDraft({...p, status:"pending"}, organizationId, owner, "ticket-1234", at), null);
  assert.equal(prepareSupervisedTiquetDraft({...p, targetSystem:"marketing"}, organizationId, owner, "ticket-1234", at), null);
  assert.equal(prepareSupervisedTiquetDraft({...p, executionStatus:"enabled"}, organizationId, owner, "ticket-1234", at), null);
});
