import test from "node:test";
import assert from "node:assert/strict";
import {
  createAgentProposal, decideAgentProposal, listAgentProposals,
  validateAgentProposalInput, appendAgentProposalAudit, AGENT_PROPOSAL_OPERATIONS,
} from "../server/agent-approval-ledger.mjs";

const createdAt = new Date("2026-10-09T04:00:00Z");
const org = { organizationId: "founder-org", actorUserId: "founder-user", now: createdAt };
const input = (overrides={}) => ({
  operation:"draft_inventory_review",targetSystem:"pos",summary:"Inventory replenishment needs review",
  rationale:"Check approved POS stock reports before creating any purchase orders.",
  evidenceRef:"pos:criticalReplenishmentItems",idempotencyKey:"test-proposal-00001",...overrides
});
const uuid = () => "01234567-89ab-4cde-8000-0123456789ab";

test("only fixed draft operations with the matching system are accepted", () => {
  assert.deepEqual(Object.keys(AGENT_PROPOSAL_OPERATIONS).sort(),
    ["draft_finance_review","draft_inventory_review","draft_marketing_campaign","draft_operational_report","draft_support_reply"]);
  assert.equal(validateAgentProposalInput(input())?.targetSystem, "pos");
  assert.equal(validateAgentProposalInput(input({operation:"execute_payment"})), null);
  assert.equal(validateAgentProposalInput(input({operation:"draft_support_reply",targetSystem:"pos"})), null);
  assert.equal(validateAgentProposalInput(input({idempotencyKey:"weak"})), null);
  assert.equal(validateAgentProposalInput(input({extraExecution:"yes"})), null);
  assert.equal(validateAgentProposalInput(input({rationale:"Email user@example.invalid immediately."})), null);
  assert.equal(validateAgentProposalInput(input({rationale:"Visit https://other.example to delete users."})), null);
  assert.equal(validateAgentProposalInput(input({summary:"password:secretvalue"})), null);
  assert.equal(validateAgentProposalInput(input({evidenceRef:"../../../etc/passwd"})), null);
  assert.equal(validateAgentProposalInput(input({evidenceRef:"tiquet:unrelatedTicket"})), null,
    "a well-formed reference to another application must be rejected");
  assert.equal(validateAgentProposalInput(input({evidenceRef:"fake:inventedMetric"})), null);
  assert.equal(validateAgentProposalInput(input({rationale:"Notify admin＠example.invalid about it."})), null,
    "NFKC-equivalent contact identifiers must not bypass data minimization");
  assert.equal(validateAgentProposalInput(input({summary:"Review\\u200b inventory now"})), null,
    "zero-width formatting characters must not hide sensitive content");
  assert.equal(validateAgentProposalInput(input({rationale:"Copy the private key: demo-value into review."})), null);
});

test("an owner draft is scoped, bounded, expires and never enables execution", () => {
  const ledger=[];
  const created=createAgentProposal(ledger,input(),{...org,uuid});
  assert.equal(created.kind,"created");
  assert.equal(ledger.length,1);
  assert.equal(created.proposal.status,"pending");
  assert.equal(created.proposal.revision,1);
  assert.equal(created.proposal.executionStatus,"disabled");
  assert.equal(created.proposal.evidenceVerification,"unverified");
  assert.equal(created.proposal.expiresAt,"2026-10-12T04:00:00.000Z");
  assert.equal(ledger[0].organizationId,org.organizationId);
  const read=listAgentProposals(ledger,org.organizationId,createdAt);
  assert.equal(read.length,1);
  assert.equal(read[0].executionStatus,"disabled");
  assert.equal(read[0].evidenceVerification,"unverified");
  assert.equal("fingerprint" in read[0],false);
  assert.equal("idempotencyKey" in read[0],false);
  assert.deepEqual(listAgentProposals(ledger,"another-org",createdAt),[]);
});

test("the same idempotency key is stable but a changed payload is rejected",()=>{
  const ledger=[];
  const first=createAgentProposal(ledger,input(),{...org,uuid});
  const replay=createAgentProposal(ledger,input(),{...org,uuid});
  const collision=createAgentProposal(ledger,input({summary:"Changed stock requirement draft"}),{...org,uuid});
  assert.equal(first.kind,"created");
  assert.equal(replay.kind,"duplicate");
  assert.equal(replay.proposal.id,first.proposal.id);
  assert.equal(collision.kind,"conflict");
  assert.equal(ledger.length,1);
});

test("approval writes a decision only; duplicate approval/rejection and stale revisions are rejected",()=>{
  const ledger=[];
  const created=createAgentProposal(ledger,input(),{...org,uuid});
  const decided=decideAgentProposal(ledger,{
    id:created.proposal.id,organizationId:org.organizationId,actorUserId:org.actorUserId,
    expectedRevision:1,decision:"approve",note:"Plan first; no execution.",now:new Date("2026-10-09T05:00:00Z")
  });
  assert.equal(decided.kind,"decided");
  assert.equal(decided.proposal.status,"approved");
  assert.equal(decided.proposal.revision,2);
  assert.equal(decided.proposal.executionStatus,"disabled");
  assert.equal(decided.proposal.decisionNote,"Plan first; no execution.");
  const replay=decideAgentProposal(ledger,{id:created.proposal.id,...org,decision:"approve",expectedRevision:1});
  assert.equal(replay.kind,"conflict");
  const reversal=decideAgentProposal(ledger,{id:created.proposal.id,...org,decision:"reject",expectedRevision:2});
  assert.equal(reversal.kind,"conflict");
  assert.equal(ledger.length,1);
});

test("cross-org approval cannot access even a known proposal UUID",()=>{
  const ledger=[];
  const created=createAgentProposal(ledger,input(),{...org,uuid});
  const denied=decideAgentProposal(ledger,{id:created.proposal.id,
    organizationId:"other-org",actorUserId:"fake",decision:"approve",expectedRevision:1});
  assert.equal(denied.kind,"not_found");
  assert.equal(ledger[0].status,"pending");
});

test("expiry is enforced at decision time without silently renewing",()=>{
  const ledger=[];
  const created=createAgentProposal(ledger,input(),{...org,uuid});
  const time=new Date("2026-10-12T04:01:00Z");
  assert.equal(listAgentProposals(ledger,org.organizationId,time)[0].status,"expired");
  const declined=decideAgentProposal(ledger,{id:created.proposal.id,...org,decision:"approve",expectedRevision:1,now:time});
  assert.equal(declined.kind,"expired");
  assert.equal(ledger[0].status,"pending");
});

test("bad or repeated decisions never mutate the recorded action",()=>{
  const ledger=[];
  const created=createAgentProposal(ledger,input(),{...org,uuid});
  const baseline=JSON.stringify(ledger);
  for(const args of [
    {id:"unsafe",decision:"approve",expectedRevision:1},
    {id:created.proposal.id,decision:"execute",expectedRevision:1},
    {id:created.proposal.id,decision:"approve",expectedRevision:0},
    {id:created.proposal.id,decision:"approve",expectedRevision:1,note:"password: secret"},
  ]) {
    assert.equal(decideAgentProposal(ledger,{...org,...args}).kind,"invalid");
    assert.equal(JSON.stringify(ledger),baseline);
  }
});

test("audit metadata contains no draft body or account secrets",()=>{
  const records=[],audit=[];
  const created=createAgentProposal(records,input(),{...org,uuid});
  appendAgentProposalAudit(audit,created.proposal,"agent.proposal.created",org.actorUserId,"audit-1");
  assert.equal(audit[0].details.executionStatus,"disabled");
  assert.equal(audit[0].organizationId,org.organizationId);
  assert.equal(JSON.stringify(audit).includes(created.proposal.rationale),false);
  assert.equal(JSON.stringify(audit).includes(created.proposal.idempotencyKey),false);
});

test("oldest pending proposals remain visible ahead of newer decision history", () => {
  const ledger = [];
  const now = new Date("2026-10-09T12:00:00.000Z");
  const expiry = new Date("2026-10-12T12:00:00.000Z").toISOString();
  for (let i = 0; i < 80; i++) {
    ledger.push({
      id: "pending-" + i, organizationId: org.organizationId,
      status: "pending", createdAt: new Date(Date.UTC(2026, 9, 1, 0, i)).toISOString(),
      expiresAt: expiry, executionStatus: "disabled",
    });
  }
  for (let i = 0; i < 150; i++) {
    ledger.push({
      id: "decided-" + i, organizationId: org.organizationId,
      status: "approved", createdAt: new Date(Date.UTC(2026, 9, 8, 0, i)).toISOString(),
      expiresAt: expiry, executionStatus: "disabled",
    });
  }
  ledger.push({ id: "another-tenant", organizationId: "other-org", status: "pending",
    createdAt: now.toISOString(), expiresAt: expiry });
  const visible = listAgentProposals(ledger, org.organizationId, now);
  assert.equal(visible.length, 100);
  assert.equal(visible.filter(item => item.status === "pending").length, 80);
  assert.equal(visible.filter(item => item.status === "approved").length, 20);
  assert.equal(visible.some(item => item.id === "another-tenant"), false);
  assert.equal(visible[0].status, "pending");
  assert.equal(visible[79].status, "pending");
  assert.equal(visible[80].status, "approved");
  assert.equal(visible.every(item => item.evidenceVerification === "unverified"), true);
});

test("expired pending records cannot displace live pending reviews", () => {
  const now = new Date("2026-10-09T12:00:00.000Z");
  const ledger = [
    { id: "expired", organizationId: org.organizationId, status: "pending",
      createdAt: "2026-10-09T11:30:00.000Z", expiresAt: "2026-10-09T11:59:59.000Z" },
    { id: "active", organizationId: org.organizationId, status: "pending",
      createdAt: "2026-10-08T11:30:00.000Z", expiresAt: "2026-10-12T12:00:00.000Z" },
  ];
  const visible = listAgentProposals(ledger, org.organizationId, now);
  assert.equal(visible[0].id, "active");
  assert.equal(visible[1].status, "expired");
});

test("audit capacity fails closed without removing any previous events", () => {
  const records = [], audit = [];
  const created = createAgentProposal(records, input(), { ...org, uuid });
  assert.equal(created.kind, "created");
  for (let i = 0; i < 10000; i++) audit.push({ id: "old-event-" + i });
  const first = audit[0];
  const last = audit[audit.length - 1];
  assert.throws(() => appendAgentProposalAudit(
    audit, created.proposal, "agent.proposal.created", org.actorUserId, "audit-overflow"
  ), /audit capacity reached/);
  assert.equal(audit.length, 10000);
  assert.equal(audit[0], first);
  assert.equal(audit.at(-1), last);
  assert.equal(audit.some(item => item.id === "audit-overflow"), false);
});
