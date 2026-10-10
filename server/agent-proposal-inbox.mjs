import crypto from "node:crypto";
import { inspectDraftProposal, verifyDraftDigest } from "./agent-proposals.mjs";

// Stage 3A.1: pure inbox state, no HTTP, DB or executable action.
const GENESIS = "0".repeat(64);
const MAX_PROPOSALS = 1000;
const MAX_EVENTS = 4000;

function checkedKey(value) {
  if (typeof value !== "string" && !Buffer.isBuffer(value)) throw new TypeError("Dedicated audit key required");
  const key = Buffer.from(value);
  if (key.length < 32) throw new TypeError("Audit key must be at least 32 bytes");
  return key;
}

function signedEvent(key, payload) {
  const mac = crypto.createHmac("sha256", key).update(JSON.stringify(payload)).digest("hex");
  return Object.freeze({ ...payload, mac });
}

function auditEvent(state, kind, draft, key, now) {
  const last = state.audit.at(-1);
  const payload = {
    sequence: state.audit.length + 1, kind,
    proposalId: draft.proposalId,
    ownerUserId: draft.ownerUserId,
    organizationId: draft.organizationId,
    proposalDigest: draft.integrityDigest,
    occurredAt: new Date(now).toISOString(),
    previousMac: last ? last.mac : GENESIS,
  };
  return signedEvent(key, payload);
}

export function emptyDraftInbox() {
  return Object.freeze({ schemaVersion: 1, proposals: Object.freeze([]), audit: Object.freeze([]) });
}

export function verifyDraftInbox(state, auditKey) {
  try {
    const key = checkedKey(auditKey);
    if (state?.schemaVersion !== 1 || !Array.isArray(state.proposals) ||
        !Array.isArray(state.audit) || state.proposals.length > MAX_PROPOSALS ||
        state.audit.length > MAX_EVENTS) return false;
    const history = new Map();
    let previousMac = GENESIS;
    for (let i = 0; i < state.audit.length; i += 1) {
      const event = state.audit[i];
      if (!event || event.sequence !== i + 1 ||
          event.previousMac !== previousMac ||
          !/^[a-f0-9]{64}$/.test(String(event.mac))) return false;
      const { mac, ...payload } = event;
      const expected = signedEvent(key, payload).mac;
      if (!crypto.timingSafeEqual(Buffer.from(mac, "hex"), Buffer.from(expected, "hex"))) return false;
      previousMac = mac;
      if (event.kind === "draft.created") {
        if (history.has(event.proposalId)) return false;
        history.set(event.proposalId, {
          reviewStatus: "pending", organizationId: event.organizationId,
          ownerUserId: event.ownerUserId, digest: event.proposalDigest,
        });
      } else if (event.kind === "draft.rejected") {
        const entry = history.get(event.proposalId);
        if (!entry || entry.reviewStatus !== "pending" ||
            entry.digest !== event.proposalDigest ||
            entry.ownerUserId !== event.ownerUserId ||
            entry.organizationId !== event.organizationId) return false;
        entry.reviewStatus = "rejected";
      } else return false;
    }
    if (history.size !== state.proposals.length) return false;
    const idempotency = new Set();
    for (const record of state.proposals) {
      const draft = record?.draft;
      const check = history.get(draft?.proposalId);
      if (!draft || !verifyDraftDigest(draft) || !check ||
          check.reviewStatus !== record.reviewStatus ||
          draft.status !== "draft" || draft.executionEnabled !== false ||
          draft.ownerUserId !== check.ownerUserId ||
          draft.organizationId !== check.organizationId ||
          draft.integrityDigest !== check.digest) return false;
      const idKey = JSON.stringify([draft.organizationId, draft.ownerUserId, draft.idempotencyKey]);
      if (idempotency.has(idKey)) return false;
      idempotency.add(idKey);
    }
    return true;
  } catch {
    return false;
  }
}

function equivalentDraft(a, b) {
  return a.organizationId === b.organizationId &&
    a.ownerUserId === b.ownerUserId &&
    a.targetApp === b.targetApp && a.operation === b.operation &&
    JSON.stringify(a.parameters) === JSON.stringify(b.parameters) &&
    a.expectedOutcome === b.expectedOutcome && a.rollbackPlan === b.rollbackPlan &&
    a.expiresAt === b.expiresAt && a.risk === b.risk;
}

export function registerDraft(state, draft, context, {
  auditKey, configuredFounderEmail, now = Date.now(),
} = {}) {
  const key = checkedKey(auditKey);
  if (!verifyDraftInbox(state, key)) throw new Error("Inbox integrity verification failed");
  if (!inspectDraftProposal(draft, context, { configuredFounderEmail, now }).validForReview) {
    throw new Error("Invalid, expired or cross-tenant draft");
  }
  const existing = state.proposals.find(item =>
    item.draft.organizationId === draft.organizationId &&
    item.draft.ownerUserId === draft.ownerUserId &&
    item.draft.idempotencyKey === draft.idempotencyKey);
  if (existing) {
    if (!equivalentDraft(existing.draft, draft)) throw new Error("Idempotency key reused with changed request");
    return { inbox: state, record: existing, duplicate: true };
  }
  if (state.proposals.length >= MAX_PROPOSALS || state.audit.length >= MAX_EVENTS ||
      state.proposals.some(item => item.draft.proposalId === draft.proposalId)) {
    throw new Error("Inbox limit or proposal ID collision");
  }
  const record = Object.freeze({ draft, reviewStatus: "pending" });
  return {
    inbox: Object.freeze({
      schemaVersion: 1,
      proposals: Object.freeze([...state.proposals, record]),
      audit: Object.freeze([...state.audit, auditEvent(state, "draft.created", draft, key, now)]),
    }),
    record,
    duplicate: false,
  };
}

// Only owner rejection is implemented; approval and execution are absent.
export function rejectDraft(state, proposalId, context, {
  auditKey, configuredFounderEmail, now = Date.now(),
} = {}) {
  const key = checkedKey(auditKey);
  if (!verifyDraftInbox(state, key)) throw new Error("Inbox integrity verification failed");
  const item = state.proposals.find(record => record.draft.proposalId === proposalId);
  if (!item || !inspectDraftProposal(item.draft, context, {
    configuredFounderEmail, now,
  }).validForReview) throw new Error("Owner cannot reject this draft");
  if (item.reviewStatus === "rejected") return { inbox: state, duplicate: true };
  if (state.audit.length >= MAX_EVENTS) throw new Error("Audit event limit reached");
  return {
    inbox: Object.freeze({
      schemaVersion: 1,
      proposals: Object.freeze(state.proposals.map(record =>
        record === item ? Object.freeze({ draft: item.draft, reviewStatus: "rejected" }) : record)),
      audit: Object.freeze([...state.audit, auditEvent(state, "draft.rejected", item.draft, key, now)]),
    }),
    duplicate: false,
  };
}

export function reviewableDrafts(state, context, {
  auditKey, configuredFounderEmail, now = Date.now(),
} = {}) {
  if (!verifyDraftInbox(state, auditKey)) throw new Error("Inbox integrity verification failed");
  return state.proposals.filter(item =>
    item.reviewStatus === "pending" &&
    inspectDraftProposal(item.draft, context, { configuredFounderEmail, now }).validForReview
  ).map(item => structuredClone(item));
}
