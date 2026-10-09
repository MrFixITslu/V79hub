import test from "node:test";
import assert from "node:assert/strict";
import { createAgentProposal, decideAgentProposal } from "../server/agent-approval-ledger.mjs";
import { prepareSupervisedMarketingDraft } from "../server/agent-supervised-marketing.mjs";

const now = new Date("2026-10-09T18:00:00Z");
const org = "synthetic-org-00000001";
const owner = "synthetic-hub-owner-0001";
const base = {
  operation: "draft_marketing_campaign",
  targetSystem: "marketing",
  summary: "Review beta campaign messaging",
  rationale: "Review source claims and wording before marketing publication.",
  idempotencyKey: "stage4-marketing-approval-test-0001",
};

function fixture(operation = base.operation, system = base.targetSystem) {
  const list = [];
  const created = createAgentProposal(list, {
    ...base, operation, targetSystem: system,
  }, { organizationId: org, actorUserId: owner, now });
  assert.equal(created.kind, "created");
  return { list, proposal: created.proposal };
}
function approve(list, proposal) {
  const result = decideAgentProposal(list, {
    id: proposal.id,
    organizationId: org, actorUserId: owner, expectedRevision: 1,
    decision: "approve", now: new Date(+now + 1000),
  });
  assert.equal(result.kind, "decided");
}

test("requires a separate approval before any supervised draft payload exists", () => {
  const { list, proposal } = fixture();
  assert.equal(prepareSupervisedMarketingDraft(proposal, org, owner, now), null);
  approve(list, proposal);
  const request = prepareSupervisedMarketingDraft(list[0], org, owner, new Date(+now + 2000));
  assert.ok(request);
  assert.equal(request.organizationId, org);
  assert.equal(request.actorHubUserId, owner);
  assert.equal(request.proposalId, proposal.id);
  assert.equal(request.title, base.summary);
  assert.match(request.brief, /NOT READY TO SEND/);
  assert.equal(Object.hasOwn(request, "status"), false);
  assert.equal(Object.hasOwn(request, "publish"), false);
  assert.equal(Object.hasOwn(request, "scheduledFor"), false);
});

test("cross-tenant, unsupported target, expiration and mutated plans fail closed", () => {
  const { list, proposal } = fixture();
  approve(list, proposal);
  assert.equal(prepareSupervisedMarketingDraft(list[0], "other-tenant-000001", owner, new Date(+now + 2000)), null);
  assert.equal(prepareSupervisedMarketingDraft(list[0], org, "short", new Date(+now + 2000)), null);
  assert.equal(prepareSupervisedMarketingDraft(list[0], org, owner, new Date(+now + 4 * 86400000)), null);
  assert.equal(prepareSupervisedMarketingDraft({ ...list[0], targetSystem: "tiquet" }, org, owner, new Date(+now + 2000)), null);
  assert.equal(prepareSupervisedMarketingDraft({ ...list[0], executionStatus: "enabled" }, org, owner, new Date(+now + 2000)), null);
  assert.equal(prepareSupervisedMarketingDraft({ ...list[0], rationale: "Invalid\\rcontrol" }, org, owner, new Date(+now + 2000)), null);
});

test("non-Marketing approvals must never generate a Marketing draft request", () => {
  const { list, proposal } = fixture("draft_support_reply", "tiquet");
  approve(list, proposal);
  assert.equal(prepareSupervisedMarketingDraft(list[0], org, owner, new Date(+now + 2000)), null);
});
