import { prepareReviewedHandoff } from "./agent-reviewed-handoff.mjs";

const HUB_ID = /^[A-Za-z0-9._:@-]{8,180}$/;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

// This function has no side effects. The caller MUST verify an MFA owner
// session, intact approval audit trail, and explicit human confirmation.
export function prepareSupervisedMarketingDraft(proposal, organizationId, actorHubUserId, at = new Date()) {
  if (typeof organizationId !== "string" || !HUB_ID.test(organizationId) ||
      typeof actorHubUserId !== "string" || !HUB_ID.test(actorHubUserId) ||
      !UUID.test(String(proposal?.id || ""))) return null;
  const reviewed = prepareReviewedHandoff(proposal, organizationId, at);
  if (!reviewed || reviewed.targetSystem !== "marketing" ||
      reviewed.kind !== "campaign-planning-brief" ||
      reviewed.executionEnabled !== false || reviewed.externalDraftCreated !== false) return null;

  const title = String(proposal.summary || "");
  const brief = reviewed.text;
  if (title.length < 4 || title.length > 160 || title.trim() !== title ||
      brief.length < 12 || brief.length > 2000 ||
      /[\u0000-\u0009\u000b-\u001f\u007f]/.test(title + brief)) return null;
  return Object.freeze({
    organizationId,
    actorHubUserId,
    proposalId: proposal.id,
    title,
    brief,
  });
}
