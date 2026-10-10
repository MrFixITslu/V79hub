import crypto from "node:crypto";

// Stage 3A is a pure draft contract: no persistence, approval or executor is wired.
export const DRAFT_OPERATIONS = Object.freeze({
  tiquet: Object.freeze({ reply_draft: Object.freeze(["ticketReference", "body"]) }),
  marketing: Object.freeze({ campaign_draft: Object.freeze(["campaignName", "body"]) }),
});
const MAX_LIFETIME_MS = 24 * 60 * 60 * 1000;
const MIN_LIFETIME_MS = 5 * 60 * 1000;
const IDENTIFIER = /^[A-Za-z0-9][A-Za-z0-9._:-]{2,127}$/;
const IDEMPOTENCY_KEY = /^[A-Za-z0-9][A-Za-z0-9._:-]{15,127}$/;

function requireText(value, name, maxLength) {
  if (typeof value !== "string" || !value.trim() || value.length > maxLength ||
      /[\u0000-\u0008\u000B\u000C\u000E-\u001F]/.test(value)) {
    throw new TypeError(name + " is invalid");
  }
  return value.trim();
}

function verifiedFounder(context, configuredFounderEmail) {
  if (!context || typeof context !== "object" ||
      context.ownerAgent !== true || context.hubAdmin !== true ||
      context.mfaVerified !== true || context.membershipStatus !== "active" ||
      typeof context.userId !== "string" || !IDENTIFIER.test(context.userId) ||
      typeof context.organizationId !== "string" || !IDENTIFIER.test(context.organizationId) ||
      typeof configuredFounderEmail !== "string" || !configuredFounderEmail.trim() ||
      String(context.email || "").trim().toLowerCase() !== configuredFounderEmail.trim().toLowerCase()) {
    throw new Error("Verified founder and MFA context required");
  }
  return context;
}

function validateParameters(targetApp, operation, value) {
  const expected = DRAFT_OPERATIONS[targetApp]?.[operation];
  if (!expected) throw new TypeError("Unsupported draft-only operation");
  if (!value || typeof value !== "object" || Array.isArray(value) ||
      ![Object.prototype, null].includes(Object.getPrototypeOf(value))) {
    throw new TypeError("Parameters must be a plain record");
  }
  const keys = Object.keys(value);
  if (keys.length !== expected.length || !keys.every(key => expected.includes(key))) {
    throw new TypeError("Only reviewed draft parameters are allowed");
  }
  const normalized = {};
  for (const key of expected) {
    const limit = key === "body" ? 2000 : key === "campaignName" ? 100 : 128;
    const text = requireText(value[key], key, limit);
    if (key === "ticketReference" && !IDENTIFIER.test(text)) {
      throw new TypeError("Ticket reference must be an opaque identifier");
    }
    normalized[key] = text;
  }
  if (Buffer.byteLength(JSON.stringify(normalized), "utf8") > 4096) {
    throw new TypeError("Draft parameters exceed maximum size");
  }
  return Object.freeze(normalized);
}

function digestOf(proposal) {
  const fields = {
    schemaVersion: proposal.schemaVersion,
    proposalId: proposal.proposalId,
    status: proposal.status,
    risk: proposal.risk,
    targetApp: proposal.targetApp,
    operation: proposal.operation,
    ownerUserId: proposal.ownerUserId,
    organizationId: proposal.organizationId,
    idempotencyKey: proposal.idempotencyKey,
    parameters: proposal.parameters,
    expectedOutcome: proposal.expectedOutcome,
    rollbackPlan: proposal.rollbackPlan,
    irreversibleEffects: proposal.irreversibleEffects,
    createdAt: proposal.createdAt,
    updatedAt: proposal.updatedAt,
    expiresAt: proposal.expiresAt,
    executionEnabled: proposal.executionEnabled,
  };
  return crypto.createHash("sha256").update(JSON.stringify(fields)).digest("hex");
}

export function verifyDraftDigest(proposal) {
  try {
    return proposal?.schemaVersion === 1 &&
      proposal.status === "draft" &&
      proposal.risk === "draft" &&
      proposal.executionEnabled === false &&
      typeof proposal.integrityDigest === "string" &&
      /^[0-9a-f]{64}$/.test(proposal.integrityDigest) &&
      digestOf(proposal) === proposal.integrityDigest;
  } catch {
    return false;
  }
}

export function createDraftProposal(request, context, {
  configuredFounderEmail,
  now = Date.now(),
  generateId = crypto.randomUUID,
} = {}) {
  const actor = verifiedFounder(context, configuredFounderEmail);
  if (!request || typeof request !== "object" || Array.isArray(request)) {
    throw new TypeError("Draft proposal required");
  }
  const allowedRequestKeys = new Set([
    "targetApp", "operation", "parameters", "idempotencyKey",
    "expectedOutcome", "rollbackPlan", "expiresAt",
    "organizationId", "ownerUserId", "risk", "irreversibleEffects",
    "executionEnabled",
  ]);
  if (Object.keys(request).some(key => !allowedRequestKeys.has(key))) {
    throw new TypeError("Unreviewed proposal fields are forbidden");
  }
  if ((request.organizationId && request.organizationId !== actor.organizationId) ||
      (request.ownerUserId && request.ownerUserId !== actor.userId)) {
    throw new Error("Draft proposal crosses the verified owner scope");
  }
  if (request.executionEnabled === true || (request.risk && request.risk !== "draft") ||
      (request.irreversibleEffects && (!Array.isArray(request.irreversibleEffects) ||
        request.irreversibleEffects.length !== 0))) {
    throw new Error("Only reversible non-executable drafts are supported");
  }
  const targetApp = requireText(request.targetApp, "targetApp", 32);
  const operation = requireText(request.operation, "operation", 64);
  const parameters = validateParameters(targetApp, operation, request.parameters);
  const idempotencyKey = requireText(request.idempotencyKey, "idempotencyKey", 128);
  if (!IDEMPOTENCY_KEY.test(idempotencyKey)) throw new TypeError("Invalid idempotency key");
  const expectedOutcome = requireText(request.expectedOutcome, "expectedOutcome", 500);
  const rollbackPlan = requireText(request.rollbackPlan, "rollbackPlan", 500);
  if (!Number.isSafeInteger(now) || now <= 0) throw new TypeError("Invalid clock");
  const expires = Date.parse(request.expiresAt);
  if (!Number.isFinite(expires) || expires - now < MIN_LIFETIME_MS ||
      expires - now > MAX_LIFETIME_MS) {
    throw new TypeError("Draft expiration must be 5 minutes to 24 hours ahead");
  }
  const proposalId = String(generateId());
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(proposalId)) {
    throw new TypeError("Invalid generated proposal identifier");
  }
  const createdAt = new Date(now).toISOString();
  const draft = {
    schemaVersion: 1,
    proposalId,
    status: "draft",
    risk: "draft",
    targetApp,
    operation,
    ownerUserId: actor.userId,
    organizationId: actor.organizationId,
    idempotencyKey,
    parameters,
    expectedOutcome,
    rollbackPlan,
    irreversibleEffects: Object.freeze([]),
    createdAt,
    updatedAt: createdAt,
    expiresAt: new Date(expires).toISOString(),
    executionEnabled: false,
  };
  return Object.freeze({ ...draft, integrityDigest: digestOf(draft) });
}

export function inspectDraftProposal(proposal, context, {
  configuredFounderEmail,
  now = Date.now(),
} = {}) {
  // Reviewability is never an approval, and there is no execution path in Stage 3A.
  try {
    const actor = verifiedFounder(context, configuredFounderEmail);
    const expires = Date.parse(proposal?.expiresAt);
    const created = Date.parse(proposal?.createdAt);
    if (!proposal || typeof proposal !== "object" || proposal.schemaVersion !== 1 ||
        proposal.status !== "draft" || proposal.executionEnabled !== false ||
        proposal.ownerUserId !== actor.userId ||
        proposal.organizationId !== actor.organizationId ||
        !DRAFT_OPERATIONS[proposal.targetApp]?.[proposal.operation] ||
        !Number.isSafeInteger(now) || !Number.isFinite(expires) ||
        !Number.isFinite(created) || now < created || expires <= now ||
        expires - created < MIN_LIFETIME_MS || expires - created > MAX_LIFETIME_MS ||
        typeof proposal.integrityDigest !== "string" ||
        !/^[0-9a-f]{64}$/.test(proposal.integrityDigest) ||
        digestOf(proposal) !== proposal.integrityDigest) {
      return Object.freeze({ validForReview: false, executionEnabled: false });
    }
    return Object.freeze({ validForReview: true, executionEnabled: false });
  } catch {
    return Object.freeze({ validForReview: false, executionEnabled: false });
  }
}
