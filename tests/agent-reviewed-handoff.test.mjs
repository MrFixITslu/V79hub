import test from "node:test";
import assert from "node:assert/strict";
import { prepareReviewedHandoff } from "../server/agent-reviewed-handoff.mjs";
import { createAgentProposal, decideAgentProposal } from "../server/agent-approval-ledger.mjs";

const now = new Date("2026-10-09T18:00:00Z");
const actor = { organizationId: "synthetic-owner", actorUserId: "synthetic-user", now };
const fresh = (operation, targetSystem) => {
  const proposals = [];
  const created = createAgentProposal(proposals, {
    operation, targetSystem,
    summary: "Review support and growth follow-ups",
    rationale: "Confirm verified details before producing any outward-facing draft.",
    idempotencyKey: "reviewed-handoff-test-safe-0001",
  }, actor);
  assert.equal(created.kind, "created");
  return { proposals, created: created.proposal };
};

test("only an approved, scoped support brief is manually copyable", () => {
  const { proposals, created } = fresh("draft_support_reply", "tiquet");
  assert.equal(prepareReviewedHandoff(created, actor.organizationId, now), null);
  const decided = decideAgentProposal(proposals, {
    id:created.id, organizationId:actor.organizationId, actorUserId:actor.actorUserId,
    expectedRevision:1, decision:"approve", now:new Date(+now+1000),
  });
  assert.equal(decided.kind, "decided");
  const result = prepareReviewedHandoff(proposals[0], actor.organizationId, new Date(+now+2000));
  assert.equal(result.mode, "manual-handoff");
  assert.equal(result.kind, "support-review-brief");
  assert.equal(result.targetSystem, "tiquet");
  assert.equal(result.executionEnabled, false);
  assert.equal(result.externalDraftCreated, false);
  assert.equal(result.sent, false);
  assert.match(result.text, /NOT READY TO SEND/);
  assert.equal(prepareReviewedHandoff(proposals[0], "another-tenant", new Date(+now+2000)), null);
  assert.equal(prepareReviewedHandoff(proposals[0], actor.organizationId, new Date(+now+4*86400000)), null);
});

test("marketing creates only an internal brief and never schedules or publishes", () => {
  const { proposals, created } = fresh("draft_marketing_campaign", "marketing");
  decideAgentProposal(proposals, {
    id:created.id, organizationId:actor.organizationId, actorUserId:actor.actorUserId,
    expectedRevision:1, decision:"approve", now:new Date(+now+1000),
  });
  const brief = prepareReviewedHandoff(proposals[0], actor.organizationId, new Date(+now+2000));
  assert.equal(brief.kind, "campaign-planning-brief");
  assert.equal(brief.published, false);
  assert.equal(brief.externalDraftCreated, false);
  assert.match(brief.text, /verify campaign claims/i);
});

test("rejected, pending, mutated or unsupported proposals fail closed", () => {
  const { proposals, created } = fresh("draft_support_reply", "tiquet");
  decideAgentProposal(proposals, {
    id:created.id, organizationId:actor.organizationId, actorUserId:actor.actorUserId,
    expectedRevision:1, decision:"reject", now:new Date(+now+1000),
  });
  assert.equal(prepareReviewedHandoff(proposals[0], actor.organizationId, new Date(+now+2000)), null);
  assert.equal(prepareReviewedHandoff({...proposals[0],status:"approved",executionStatus:"enabled"},actor.organizationId,new Date(+now+2000)),null);
  assert.equal(prepareReviewedHandoff({...proposals[0],status:"approved",targetSystem:"pos"},actor.organizationId,new Date(+now+2000)),null);
  assert.equal(prepareReviewedHandoff({...proposals[0],status:"approved",rationale:"email: user@example.com"},actor.organizationId,new Date(+now+2000)),null);
});
