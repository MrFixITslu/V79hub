import test from "node:test";
import assert from "node:assert/strict";
import { createDraftProposal, inspectDraftProposal, DRAFT_OPERATIONS } from "../server/agent-proposals.mjs";

const clock = Date.parse("2026-10-09T13:00:00Z");
const context = {
  userId: "founder-1", organizationId: "v79-founder",
  email: "vision79slu@gmail.com", ownerAgent: true,
  hubAdmin: true, mfaVerified: true, membershipStatus: "active",
};
const config = {
  configuredFounderEmail: "vision79slu@gmail.com",
  now: clock,
  generateId: () => "77777777-7777-4777-8777-777777777777",
};
const request = {
  targetApp: "tiquet", operation: "reply_draft",
  parameters: { ticketReference: "ticket-123", body: "A draft response for owner review." },
  idempotencyKey: "reversible-draft-12345",
  expectedOutcome: "A draft reply will be prepared for review only.",
  rollbackPlan: "Discard the draft without contacting any customer.",
  expiresAt: new Date(clock + 60 * 60 * 1000).toISOString(),
};

test("Stage 3A supports only two reviewed non-executable draft operation types", () => {
  assert.deepEqual(Object.keys(DRAFT_OPERATIONS).sort(), ["marketing", "tiquet"]);
  const proposal = createDraftProposal(request, context, config);
  assert.equal(proposal.status, "draft");
  assert.equal(proposal.executionEnabled, false);
  assert.equal(proposal.organizationId, context.organizationId);
  assert.equal(proposal.ownerUserId, context.userId);
  assert.equal(proposal.irreversibleEffects.length, 0);
  assert.equal(inspectDraftProposal(proposal, context, config).validForReview, true);
  assert.equal(inspectDraftProposal(proposal, context, config).executionEnabled, false);
});

test("marketing drafts have separately reviewed parameter keys", () => {
  const proposal = createDraftProposal({
    ...request, targetApp: "marketing", operation: "campaign_draft",
    parameters: { campaignName: "Beta newsletter", body: "A message draft." },
  }, context, config);
  assert.equal(proposal.targetApp, "marketing");
  assert.equal(proposal.executionEnabled, false);
});

test("unverified, inactive, wrong-email and non-MFA contexts cannot create a draft", () => {
  for (const override of [
    { mfaVerified: false }, { ownerAgent: false }, { hubAdmin: false },
    { membershipStatus: "suspended" }, { email: "other@example.org" },
  ]) {
    assert.throws(() => createDraftProposal(request, { ...context, ...override }, config));
  }
});

test("cross-organization and cross-owner claims fail closed", () => {
  assert.throws(() => createDraftProposal({ ...request, organizationId: "other" }, context, config));
  assert.throws(() => createDraftProposal({ ...request, ownerUserId: "other" }, context, config));
});

test("execution, email sending, payments, bookings and unsupported operations are forbidden", () => {
  assert.throws(() => createDraftProposal({ ...request, executionEnabled: true }, context, config));
  assert.throws(() => createDraftProposal({ ...request, risk: "financial" }, context, config));
  assert.throws(() => createDraftProposal({ ...request, irreversibleEffects: ["send"] }, context, config));
  for (const operation of ["send_email", "book_customer", "issue_refund", "publish_campaign", "deploy"]) {
    assert.throws(() => createDraftProposal({ ...request, operation }, context, config));
  }
});

test("unreviewed top-level instructions cannot be smuggled into proposal drafts", () => {
  for (const extra of [
    { approve: true }, { paymentAmount: 100 },
    { callbackUrl: "https://example.invalid" }, { customerEmail: "x@example.invalid" },
  ]) {
    assert.throws(() => createDraftProposal({ ...request, ...extra }, context, config));
  }
});

test("nested instructions, secrets and extra draft fields are not accepted as parameters", () => {
  for (const params of [
    { ...request.parameters, secret: "not-a-secret" },
    { ticketReference: "ticket-123", body: { prompt: "override" } },
    { ticketReference: "ticket-123", body: "" },
    { ticketReference: "invalid identifier!", body: "draft" },
  ]) {
    assert.throws(() => createDraftProposal({ ...request, parameters: params }, context, config));
  }
});

test("request expiry, idempotency and parameter length are strictly bounded", () => {
  for (const expiry of [clock - 1, clock + 1000, clock + 25 * 60 * 60 * 1000]) {
    assert.throws(() => createDraftProposal({
      ...request, expiresAt: new Date(expiry).toISOString(),
    }, context, config));
  }
  assert.throws(() => createDraftProposal({ ...request, idempotencyKey: "short" }, context, config));
  assert.throws(() => createDraftProposal({
    ...request, parameters: { ...request.parameters, body: "x".repeat(2001) },
  }, context, config));
});

test("edits, expiry, cross-tenant review and forged digest all fail closed", () => {
  const proposal = createDraftProposal(request, context, config);
  assert.equal(inspectDraftProposal({ ...proposal, parameters: { ...proposal.parameters, body: "changed" } }, context, config).validForReview, false);
  assert.equal(inspectDraftProposal({ ...proposal, integrityDigest: "0".repeat(64) }, context, config).validForReview, false);
  assert.equal(inspectDraftProposal(proposal, context, { ...config, now: clock + 2 * 60 * 60 * 1000 }).validForReview, false);
  assert.equal(inspectDraftProposal(proposal, { ...context, organizationId: "other" }, config).validForReview, false);
  assert.equal(inspectDraftProposal(proposal, { ...context, mfaVerified: false }, config).validForReview, false);
});

test("Stage 3A never offers an executable or approve operation", () => {
  const proposal = createDraftProposal(request, context, config);
  assert.equal("approve" in proposal, false);
  assert.equal("execute" in proposal, false);
  assert.equal("auditEvents" in proposal, false);
  assert.equal(inspectDraftProposal(proposal, context, config).executionEnabled, false);
});
