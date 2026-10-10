import { WORKFORCE_SPECIALISTS, type WorkforceSpecialistId } from "./workforce.js";

/**
 * CEO + COO v1.0: deterministic, read-only governance metadata.
 *
 * This module DOES NOT create model agents, grant permissions, change the
 * existing specialist router, approve a task or execute an application write.
 * Existing specialist identities remain available for backwards compatibility.
 * Only the two executives are accountable roles in the target organization.
 */
export type ExecutiveId = "ceo" | "coo";

export type ExecutiveRole = Readonly<{
  id: ExecutiveId;
  name: string;
  accountability: string;
  mode: "read-only";
  approvalAuthority: "none";
  reportsTo: "owner" | "ceo";
}>;

export const EXECUTIVE_ROLES: readonly ExecutiveRole[] = Object.freeze([
  Object.freeze({
    id: "ceo",
    name: "V79 CEO",
    accountability: "Strategy, risk, business priorities, and presenting decisions to the owner",
    mode: "read-only",
    approvalAuthority: "none",
    reportsTo: "owner",
  }),
  Object.freeze({
    id: "coo",
    name: "V79 COO",
    accountability: "Daily operations, investigations, verified reporting, and proposing safe improvements",
    mode: "read-only",
    approvalAuthority: "none",
    reportsTo: "ceo",
  }),
]);

/** Existing owner coordinator is aligned to CEO; all six specialist skills to COO.
 * This does not turn those SDK specialist instances into independent executives.
 */
export const SPECIALIST_EXECUTIVE_ASSIGNMENT: Readonly<Record<WorkforceSpecialistId, ExecutiveId>> =
  Object.freeze({
    owner: "ceo",
    operations: "coo",
    technology: "coo",
    finance: "coo",
    growth: "coo",
    customer: "coo",
    combatzone: "coo",
  });

export function executiveForSpecialist(id: WorkforceSpecialistId): ExecutiveRole {
  if (!Object.prototype.hasOwnProperty.call(SPECIALIST_EXECUTIVE_ASSIGNMENT, id)) {
    throw new Error("Unknown specialist: no executive assignment");
  }
  const executiveId = SPECIALIST_EXECUTIVE_ASSIGNMENT[id];
  const executive = EXECUTIVE_ROLES.find(role => role.id === executiveId);
  if (!executive) throw new Error("Executive assignment is not configured");
  return executive;
}

/**
 * Safe static metadata for an already-internal, token-protected Hub agent API.
 * "planned" means NOT operational. No model-supplied permission claims.
 */
export function executiveWorkforceStructure() {
  return {
    version: "1.0",
    mode: "read-only" as const,
    scope: "v79-digital-owner-only" as const,
    approvalRoute: "coo-to-ceo-to-founder" as const,
    ownerApprovalRequiredForRestrictedActions: true,
    actionsEnabled: false,
    applicationWriteAdaptersEnabled: false,
    autonomousLearningPromotionEnabled: false,
    roles: EXECUTIVE_ROLES.map(role => ({ ...role })),
    assignments: WORKFORCE_SPECIALISTS.map(specialist => ({
      specialistId: specialist.id,
      specialistName: specialist.name,
      executiveId: executiveForSpecialist(specialist.id).id,
      mode: "read-only" as const,
    })),
    specialistCapabilities: {
      marketIntelligence: {
        parentSpecialist: "growth" as const,
        executiveOwner: "ceo" as const,
        executiveResearcher: "coo" as const,
        region: "Saint Lucia / OECS / Caribbean" as const,
        status: "planned" as const,
        autonomousAgent: false,
      },
      sentinel: {
        parentSpecialist: "technology" as const,
        executiveOwner: "ceo" as const,
        executiveOperator: "coo" as const,
        integrationStatus: "unverified" as const,
        actionsEnabled: false,
      },
    },
  };
}
