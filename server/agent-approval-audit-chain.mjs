import { createHmac, randomUUID, timingSafeEqual } from "node:crypto";

// Detects unauthorised edits to approval metadata within the persisted Hub store.
// It does NOT replace off-store write-once retention / independent hash anchoring.
const GENESIS = "0".repeat(64);
const MAX_EVENTS = 10000;
const EVENT_FIELDS = [
  "id", "organizationId", "actorUserId", "proposalId", "operation",
  "targetSystem", "status", "revision", "executionStatus", "createdAt", "previousMac",
];
const VALID_STATUS = new Set(["pending", "approved", "rejected"]);

function eventPayload(event) {
  return EVENT_FIELDS.map(field => event[field]);
}

function isValidEvent(event) {
  if (!event || typeof event !== "object" || Array.isArray(event) ||
      Object.keys(event).sort().join(",") !== [...EVENT_FIELDS, "mac"].sort().join(",")) return false;
  if (!["id", "organizationId", "actorUserId", "proposalId", "operation", "targetSystem", "createdAt"]
    .every(key => typeof event[key] === "string" && event[key].length > 0 && event[key].length <= 150)) return false;
  if (!VALID_STATUS.has(event.status) || event.executionStatus !== "disabled" ||
      !Number.isInteger(event.revision) || event.revision < 1 ||
      !/^[a-f0-9]{64}$/.test(event.previousMac) ||
      !/^[a-f0-9]{64}$/.test(event.mac)) return false;
  return Number.isFinite(Date.parse(event.createdAt));
}

// Cross-check the signed sequence against the current proposal snapshots.
// This detects a removed tail event while its proposal still exists. It cannot
// detect coordinated alteration of both records by a holder of the HMAC key.
export function verifyAgentApprovalAuditLinkage(events, proposals) {
  if (!Array.isArray(events) || !Array.isArray(proposals)) return false;
  const latest = new Map();
  for (const item of events) {
    if (!item || typeof item.proposalId !== "string") return false;
    const prior = latest.get(item.proposalId);
    if (!prior) {
      if (item.status !== "pending" || item.revision !== 1) return false;
    } else {
      if (prior.status !== "pending" || item.revision !== prior.revision + 1 ||
          !["approved", "rejected"].includes(item.status) ||
          item.organizationId !== prior.organizationId || item.operation !== prior.operation ||
          item.targetSystem !== prior.targetSystem) return false;
    }
    latest.set(item.proposalId, item);
  }
  if (latest.size !== proposals.length) return false;
  for (const proposal of proposals) {
    const entry = latest.get(proposal?.id);
    if (!entry || entry.status !== proposal.status ||
        entry.revision !== proposal.revision || entry.organizationId !== proposal.organizationId ||
        entry.operation !== proposal.operation || entry.targetSystem !== proposal.targetSystem ||
        proposal.executionStatus !== "disabled") return false;
  }
  return true;
}

export function createAgentApprovalAuditChain(secret, {
  now = () => new Date(), uuid = randomUUID,
} = {}) {
  const enabled = typeof secret === "string" && secret.length >= 32;

  function sign(payload) {
    if (!enabled) throw new Error("Agent approval audit signing key unavailable.");
    return createHmac("sha256", secret).update(JSON.stringify(payload)).digest("hex");
  }

  function verify(events) {
    if (!enabled || !Array.isArray(events) || events.length > MAX_EVENTS) return false;
    let previousMac = GENESIS;
    const seen = new Set();
    for (const event of events) {
      if (!isValidEvent(event) || event.previousMac !== previousMac ||
          seen.has(event.id)) return false;
      const expected = Buffer.from(sign(eventPayload(event)), "hex");
      const actual = Buffer.from(event.mac, "hex");
      if (!timingSafeEqual(actual, expected)) return false;
      seen.add(event.id);
      previousMac = event.mac;
    }
    return true;
  }

  function append(events, proposal, actorUserId) {
    if (!verify(events)) throw new Error("Agent approval audit integrity unavailable.");
    if (events.length >= MAX_EVENTS) throw new Error("Agent approval audit retention capacity reached.");
    if (!proposal || typeof proposal !== "object" ||
        !VALID_STATUS.has(proposal.status) || proposal.executionStatus !== "disabled" ||
        !Number.isInteger(proposal.revision) || proposal.revision < 1 ||
        !actorUserId) throw new Error("Invalid agent approval audit event.");
    const event = {
      id: uuid(), organizationId: proposal.organizationId, actorUserId,
      proposalId: proposal.id, operation: proposal.operation, targetSystem: proposal.targetSystem,
      status: proposal.status, revision: proposal.revision, executionStatus: "disabled",
      createdAt: now().toISOString(), previousMac: events.at(-1)?.mac || GENESIS,
    };
    if (!isValidEvent({ ...event, mac: GENESIS })) throw new Error("Invalid agent approval audit event.");
    const secured = { ...event, mac: sign(eventPayload(event)) };
    events.push(secured);
    return secured;
  }

  function health(events) {
    return {
      integrity: verify(events) ? "verified" : "unavailable",
      count: Array.isArray(events) ? events.length : null,
      capacity: MAX_EVENTS,
      // No raw HMAC, secret or personal identifiers in the health response.
    };
  }

  return { enabled, verify, append, health };
}
