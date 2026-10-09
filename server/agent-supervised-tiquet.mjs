import { prepareReviewedHandoff } from "./agent-reviewed-handoff.mjs";

const OWNER_ID = /^[A-Za-z0-9._:@-]{8,180}$/;
const JOB_ID = /^[A-Za-z0-9._:@-]{1,180}$/;

// Pure only: authenticated owner, verified audit, explicit ticket selection,
// and signed HTTP calls are enforced by the surrounding server routes.
export function prepareSupervisedTiquetDraft(proposal, organizationId, actorHubUserId, jobId, at = new Date()) {
  if (typeof organizationId !== "string" || !OWNER_ID.test(organizationId) ||
      typeof actorHubUserId !== "string" || !OWNER_ID.test(actorHubUserId) ||
      typeof jobId !== "string" || !JOB_ID.test(jobId)) return null;
  const reviewed = prepareReviewedHandoff(proposal, organizationId, at);
  if (!reviewed || reviewed.kind !== "support-review-brief" ||
      reviewed.targetSystem !== "tiquet" || reviewed.executionEnabled !== false ||
      reviewed.externalDraftCreated !== false || reviewed.sent !== false) return null;
  const content = reviewed.text;
  if (content.trim() !== content || content.length < 12 || content.length > 2000 ||
      /[\u0000-\u0009\u000b-\u001f\u007f]/.test(content)) return null;
  return Object.freeze({
    organizationId, actorHubUserId, proposalId: proposal.id,
    jobId, content,
  });
}
