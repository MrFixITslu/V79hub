import test from "node:test";
import assert from "node:assert/strict";
import { createDraftProposal } from "../server/agent-proposals.mjs";
import {
  emptyDraftInbox, verifyDraftInbox, registerDraft, rejectDraft, reviewableDrafts,
} from "../server/agent-proposal-inbox.mjs";

const now = Date.parse("2026-10-09T14:00:00Z");
const owner = {
  userId: "founder-1", organizationId: "v79-owner", email: "vision79slu@gmail.com",
  ownerAgent: true, hubAdmin: true, mfaVerified: true, membershipStatus: "active",
};
const auditKey = "dedicated-test-only-inbox-key-is-long-enough-0123456789";
const options = { auditKey, configuredFounderEmail: "vision79slu@gmail.com", now };

function proposal({
  key = "unique-inbox-request-001",
  body = "A draft for owner review",
  id = "11111111-1111-4111-8111-111111111111",
} = {}) {
  return createDraftProposal({
    targetApp: "marketing", operation: "campaign_draft",
    parameters: { campaignName: "Beta announcement", body },
    idempotencyKey: key,
    expectedOutcome: "Only prepare a draft.",
    rollbackPlan: "Discard the draft.",
    expiresAt: new Date(now + 3600000).toISOString(),
  }, owner, { ...options, generateId: () => id });
}

test("new inbox has empty valid audit state", () => {
  const state = emptyDraftInbox();
  assert.equal(verifyDraftInbox(state, auditKey), true);
  assert.equal(state.audit.length, 0);
});

test("registration creates only a non-executable proposal and signed event", () => {
  const result = registerDraft(emptyDraftInbox(), proposal(), owner, options);
  assert.equal(result.duplicate, false);
  assert.equal(result.inbox.proposals.length, 1);
  assert.equal(result.inbox.audit.length, 1);
  assert.equal(result.inbox.audit[0].kind, "draft.created");
  assert.equal(result.record.draft.executionEnabled, false);
  assert.equal(verifyDraftInbox(result.inbox, auditKey), true);
});

test("identical retry does not create another draft or audit event", () => {
  const first = registerDraft(emptyDraftInbox(), proposal(), owner, options);
  const again = registerDraft(first.inbox,
    proposal({ id: "22222222-2222-4222-8222-222222222222" }), owner, options);
  assert.equal(again.duplicate, true);
  assert.equal(again.inbox, first.inbox);
  assert.equal(again.inbox.audit.length, 1);
});

test("conflicting retry with reused idempotency key fails", () => {
  const state = registerDraft(emptyDraftInbox(), proposal(), owner, options).inbox;
  assert.throws(() => registerDraft(state, proposal({ body: "Changed request" }), owner, options));
});

test("review listing never exposes other organizations or non-MFA contexts", () => {
  const state = registerDraft(emptyDraftInbox(), proposal(), owner, options).inbox;
  assert.equal(reviewableDrafts(state, owner, options).length, 1);
  assert.equal(reviewableDrafts(state, { ...owner, organizationId: "other" }, options).length, 0);
  assert.equal(reviewableDrafts(state, { ...owner, mfaVerified: false }, options).length, 0);
});

test("registration and rejection fail closed after expiration", () => {
  const state = registerDraft(emptyDraftInbox(), proposal(), owner, options).inbox;
  const later = { ...options, now: now + 7200000 };
  assert.throws(() => registerDraft(emptyDraftInbox(), proposal(), owner, later));
  assert.throws(() => rejectDraft(state, proposal().proposalId, owner, later));
  assert.equal(reviewableDrafts(state, owner, later).length, 0);
});

test("owner can reject once; double-click is idempotent and auditable", () => {
  const state = registerDraft(emptyDraftInbox(), proposal(), owner, options).inbox;
  const first = rejectDraft(state, proposal().proposalId, owner, options);
  assert.equal(first.duplicate, false);
  assert.equal(first.inbox.proposals[0].reviewStatus, "rejected");
  assert.equal(first.inbox.audit[1].kind, "draft.rejected");
  assert.equal(verifyDraftInbox(first.inbox, auditKey), true);
  const again = rejectDraft(first.inbox, proposal().proposalId, owner, options);
  assert.equal(again.duplicate, true);
  assert.equal(again.inbox.audit.length, 2);
});

test("wrong HMAC key, modified proposal and modified audit are detected", () => {
  const state = registerDraft(emptyDraftInbox(), proposal(), owner, options).inbox;
  assert.equal(verifyDraftInbox(state, "another-test-audit-key-with-more-than-thirty-two-bytes"), false);
  const editedEvent = structuredClone(state);
  editedEvent.audit[0].kind = "draft.rejected";
  assert.equal(verifyDraftInbox(editedEvent, auditKey), false);
  const editedDraft = structuredClone(state);
  editedDraft.proposals[0].draft.parameters.body = "Tampered";
  assert.equal(verifyDraftInbox(editedDraft, auditKey), false);
});

test("deleted or replayed events cannot fabricate inbox history", () => {
  const state = registerDraft(emptyDraftInbox(), proposal(), owner, options).inbox;
  assert.equal(verifyDraftInbox({ ...state, audit: [] }, auditKey), false);
  assert.equal(verifyDraftInbox({ ...state, audit: [state.audit[0], state.audit[0]] }, auditKey), false);
});

test("no approve, send, publish or execute operation is available", () => {
  const state = registerDraft(emptyDraftInbox(), proposal(), owner, options).inbox;
  assert.equal(state.proposals[0].reviewStatus, "pending");
  assert.equal(state.proposals[0].draft.executionEnabled, false);
  assert.equal("approved" in state, false);
});
