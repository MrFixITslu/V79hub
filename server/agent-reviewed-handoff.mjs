// Read-only, copy-only handoff for existing approved founder proposals.
// Never calls Tiquet/Marketing APIs, mutates the Hub store or creates a dispatch job.
import { validateAgentProposalInput } from "./agent-approval-ledger.mjs";

const OPERATIONS = Object.freeze({
  draft_support_reply: "tiquet",
  draft_marketing_campaign: "marketing",
});

export function prepareReviewedHandoff(proposal, organizationId, at = new Date()) {
  if (!proposal || typeof organizationId !== "string" ||
      proposal.organizationId !== organizationId ||
      proposal.status !== "approved" || proposal.executionStatus !== "disabled" ||
      !Object.hasOwn(OPERATIONS, proposal.operation) ||
      proposal.targetSystem !== OPERATIONS[proposal.operation] ||
      !Number.isFinite(+at) || !(Date.parse(proposal.expiresAt) > +at)) return null;

  const validated = validateAgentProposalInput({
    operation: proposal.operation, targetSystem: proposal.targetSystem,
    summary: proposal.summary, rationale: proposal.rationale,
    idempotencyKey: proposal.idempotencyKey,
    ...(proposal.evidenceRef ? { evidenceRef: proposal.evidenceRef } : {}),
  });
  if (!validated) return null;

  const kind = proposal.targetSystem === "tiquet" ? "support-review-brief" : "campaign-planning-brief";
  const instructions = proposal.targetSystem === "tiquet"
    ? "Review the actual Tiquet ticket, identify the customer and verify facts before composing a reply."
    : "Verify campaign claims, platforms, recipients, schedule and permissions before composing any publishable content.";
  const text = [
    "V79 AI WORKFORCE - INTERNAL REVIEW BRIEF (NOT READY TO SEND)",
    "Destination: " + proposal.targetSystem,
    "Subject: " + validated.summary,
    "Review notes: " + validated.rationale,
    "Evidence status: " + (proposal.evidenceVerification === "proxy_attested" ? "Hub session aggregate receipt" : "Not independently verified"),
    "Next step: " + instructions,
    "Status: approved planning brief only. No external action authorised.",
  ].join("\n");
  return Object.freeze({
    mode: "manual-handoff", kind, targetSystem: proposal.targetSystem,
    proposalId: proposal.id, text, executionEnabled: false,
    externalDraftCreated: false, sent: false, published: false,
  });
}
