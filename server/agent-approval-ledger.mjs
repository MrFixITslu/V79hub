import { createHash, randomUUID } from "node:crypto";

export const AGENT_PROPOSAL_OPERATIONS = Object.freeze({
  draft_support_reply: "tiquet",
  draft_marketing_campaign: "marketing",
  draft_inventory_review: "pos",
  draft_finance_review: "ffpro",
  draft_operational_report: "hub",
});

const MAX_PENDING_PER_ORG = 80;
const MAX_STORED_PER_ORG = 500;
const TTL_MS = 72 * 60 * 60 * 1000;

function clean(value, min, max) {
  if (typeof value !== "string") return null;
  if (value !== value.trim() || value.length < min || value.length > max ||
      /[\u0000-\u001f\u007f]/.test(value) ||
      /\b(?:password|api[_ -]?key|secret|bearer|token)\s*[:=]/i.test(value) ||
      /[\u200b-\u200f\u2060\ufeff]/.test(value)) return null;
  return value;
}

export function validateAgentProposalInput(raw) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  const allowed = ["operation", "targetSystem", "summary", "rationale", "idempotencyKey", "evidenceRef"];
  if (Object.keys(raw).some(k => !allowed.includes(k))) return null;
  const { operation, targetSystem } = raw;
  if (typeof operation !== "string" || !Object.hasOwn(AGENT_PROPOSAL_OPERATIONS, operation) ||
    targetSystem !== AGENT_PROPOSAL_OPERATIONS[operation]) return null;
  const summary = clean(raw.summary, 8, 180);
  const rationale = clean(raw.rationale, 12, 900);
  const key = clean(raw.idempotencyKey, 16, 96);
  if (!summary || !rationale || !key || !/^[a-zA-Z0-9_-]{16,96}$/.test(key)) return null;
  const evidenceRef = raw.evidenceRef === undefined ? null : clean(raw.evidenceRef, 5, 150);
  if (raw.evidenceRef !== undefined && (!evidenceRef || !/^[a-z]+:[A-Za-z0-9]+$/.test(evidenceRef))) return null;
  // A syntactically valid reference is NOT authenticated evidence. Require its
  // source to match the fixed application, and expose unverified provenance.
  if (evidenceRef && evidenceRef.split(":")[0] !== targetSystem) return null;
  // This inbox is for generic draft plans, never customer PII, account identifiers or credentials.
  const disclosureText = (summary + " " + rationale).normalize("NFKC");
  if (/@|https?:\/\/|(?:\+?\d[\d\s()-]{8,}\d)|\b(?:private\s*key|client\s*secret|authorization)\s*[:=]/i.test(disclosureText)) return null;
  return { operation, targetSystem, summary, rationale, idempotencyKey:key, evidenceRef };
}

function fingerprint(input) {
  return createHash("sha256").update(JSON.stringify([
    input.operation, input.targetSystem, input.summary, input.rationale, input.evidenceRef,
  ])).digest("hex");
}

export function createAgentProposal(records, raw, { organizationId = "", actorUserId = "", now = new Date(), uuid = randomUUID } = {}) {
  if (!Array.isArray(records) || !organizationId || !actorUserId) return { kind: "invalid" };
  const input = validateAgentProposalInput(raw);
  if (!input || !Number.isFinite(+now)) return { kind: "invalid" };
  const matching = records.find(p => p.organizationId === organizationId && p.idempotencyKey === input.idempotencyKey);
  const digest = fingerprint(input);
  if (matching) return matching.fingerprint === digest
    ? { kind: "duplicate", proposal: matching }
    : { kind: "conflict" };
  const orgRecords = records.filter(p => p.organizationId === organizationId);
  if (orgRecords.length >= MAX_STORED_PER_ORG ||
      orgRecords.filter(p => p.status === "pending" && Date.parse(p.expiresAt) > +now).length >= MAX_PENDING_PER_ORG) {
    return { kind: "limit" };
  }
  const proposal = {
    id: uuid(), organizationId, createdByUserId: actorUserId,
    operation: input.operation, targetSystem: input.targetSystem,
    summary: input.summary, rationale: input.rationale,
    evidenceRef: input.evidenceRef,
    evidenceVerification: "unverified",
    idempotencyKey: input.idempotencyKey, fingerprint: digest,
    status: "pending", revision: 1,
    createdAt: now.toISOString(), expiresAt: new Date(+now + TTL_MS).toISOString(),
    decidedAt: null, decidedByUserId: null, decisionNote: null,
    executionStatus: "disabled",
  };
  records.push(proposal);
  return { kind: "created", proposal };
}

export function decideAgentProposal(records, { id = "", organizationId = "", actorUserId = "", expectedRevision = 0, decision = "", note = "", now = new Date() } = {}) {
  if (!Array.isArray(records) || typeof id !== "string" ||
    !/^[0-9a-f-]{36}$/i.test(id) || !organizationId || !actorUserId ||
    !Number.isInteger(expectedRevision) || expectedRevision < 1 ||
    !["approve", "reject"].includes(decision) || !Number.isFinite(+now)) return { kind: "invalid" };
  const decisionNote = note === undefined || note === "" ? null : clean(note, 3, 400);
  if (note !== undefined && note !== "" && !decisionNote) return { kind: "invalid" };
  const proposal = records.find(p => p.id === id && p.organizationId === organizationId);
  if (!proposal) return { kind: "not_found" };
  if (proposal.status !== "pending" || proposal.revision !== expectedRevision) return { kind: "conflict" };
  if (Date.parse(proposal.expiresAt) <= +now) return { kind: "expired" };
  const next = {
    ...proposal, status: decision === "approve" ? "approved" : "rejected", revision: proposal.revision + 1,
    decidedAt: now.toISOString(), decidedByUserId: actorUserId, decisionNote, executionStatus: "disabled",
  };
  records[records.indexOf(proposal)] = next;
  return { kind: "decided", proposal: next };
}

export function listAgentProposals(records, organizationId, now = new Date()) {
  if (!Array.isArray(records) || !organizationId) return [];
  return records.filter(p => p.organizationId === organizationId)
    .map(p => {
      if (p.status !== "pending" || Date.parse(p.expiresAt) > +now) return p;
      return { ...p, status: "expired", executionStatus: "disabled" };
    })
    // Always show every outstanding pending proposal (max 80 per org) before
    // recently decided records. Older decisions may still require pagination.
    .sort((a,b) => Number(b.status === "pending") - Number(a.status === "pending") ||
      b.createdAt.localeCompare(a.createdAt) || b.id.localeCompare(a.id)).slice(0,100)
    .map(p => ({
      id:p.id, targetSystem:p.targetSystem, operation:p.operation, summary:p.summary,
      rationale:p.rationale, evidenceRef:p.evidenceRef,
      evidenceVerification:"unverified", status:p.status, revision:p.revision,
      createdAt:p.createdAt, expiresAt:p.expiresAt, decidedAt:p.decidedAt,
      decisionNote:p.decisionNote, executionStatus:"disabled",
    }));
}

export function appendAgentProposalAudit(events, proposal, type, actorUserId, id = randomUUID()) {
  events.push({
    id, organizationId: proposal.organizationId, actorUserId,
    type, createdAt: new Date().toISOString(),
    details: { proposalId: proposal.id, operation: proposal.operation, targetSystem:proposal.targetSystem,
      status:proposal.status, revision:proposal.revision, executionStatus:"disabled" },
  });
  if (events.length > 5000) events.splice(0, events.length-5000);
}
