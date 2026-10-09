import { createHash, randomBytes } from "node:crypto";
import { validateAgentProposalInput } from "./agent-approval-ledger.mjs";

// Session-bound, transient receipts for *the authenticated agent proxy's* read-only
// investigation output. Not a signature from the underlying application source.
// Tokens are intentionally invalid after a process restart or on another replica.
const SYSTEM_OPERATIONS = Object.freeze({
  tiquet: "draft_support_reply",
  marketing: "draft_marketing_campaign",
  pos: "draft_inventory_review",
  ffpro: "draft_finance_review",
  hub: "draft_operational_report",
});

function digest(value) {
  return createHash("sha256").update(JSON.stringify(value)).digest("hex");
}

function validSourceFinding(finding, ledger, nowMs) {
  if (!finding || typeof finding !== "object" || Array.isArray(finding) ||
      typeof finding.system !== "string" || !Object.hasOwn(SYSTEM_OPERATIONS, finding.system) ||
      typeof finding.id !== "string" ||
      !/^[a-z]+:[A-Za-z0-9]+$/.test(finding.id) ||
      !finding.id.startsWith(finding.system + ":") ||
      !finding.evidence || typeof finding.evidence !== "object" ||
      !Array.isArray(ledger?.records)) return false;

  const { source, metric, value, reportedAt } = finding.evidence;
  const timestamp = Date.parse(reportedAt);
  if (!Number.isFinite(timestamp) || timestamp > nowMs + 5 * 60_000 ||
      nowMs - timestamp > 24 * 60 * 60_000 ||
      typeof source !== "string" || typeof metric !== "string" ||
      typeof value !== "number" || !Number.isFinite(value)) return false;

  const proposed = validateAgentProposalInput({
    operation: SYSTEM_OPERATIONS[finding.system], targetSystem: finding.system,
    summary: finding.title, rationale: finding.nextStep,
    evidenceRef: finding.id, idempotencyKey: "synthetic-attestation-validation-0001",
  });
  if (!proposed) return false;

  // Require a matching *available*, fresh aggregate from the proxied ledger.
  // The model's freeform output alone cannot mint an attestation.
  return ledger.records.some(record =>
    record?.system === finding.system &&
    record?.state === "available" &&
    record?.source === source &&
    record?.reportedAt === reportedAt &&
    Array.isArray(record.metrics) &&
    record.metrics.some(item => item?.key === metric && item?.value === value)
  );
}

export function createAgentEvidenceAttestations({
  now = () => Date.now(), ttlMs = 10 * 60_000, maxEntries = 1000,
  nonce = () => randomBytes(24).toString("base64url"),
} = {}) {
  const records = new Map();

  function prune() {
    const clock = now();
    for (const [token, item] of records) {
      if (item.expiresAt <= clock) records.delete(token);
    }
    while (records.size > maxEntries) records.delete(records.keys().next().value);
  }

  function decorate(payload, { organizationId, userId } = {}) {
    if (!payload || typeof payload !== "object" || Array.isArray(payload) ||
        !Array.isArray(payload.investigation?.findings)) return payload;

    const mayAttest = Boolean(organizationId && userId &&
      payload.investigation?.mode === "read-only" &&
      ["available", "partial"].includes(payload.investigation?.dataStatus) &&
      payload.evidence?.mode === "read-only");
    prune();
    // Strip model/upstream-authored attestation fields, even if the response
    // cannot be attested. Only this trusted proxy may mint a new receipt.
    const findings = payload.investigation.findings.map(finding => {
      if (!finding || typeof finding !== "object" || Array.isArray(finding)) return finding;
      const { evidenceAttestation: ignored, ...cleanFinding } = finding;
      if (!mayAttest || !validSourceFinding(cleanFinding, payload.evidence, now()) ||
          records.size >= maxEntries) {
        return cleanFinding;
      }
      const token = nonce();
      const input = {
        operation: SYSTEM_OPERATIONS[cleanFinding.system], targetSystem: cleanFinding.system,
        summary: cleanFinding.title, rationale: cleanFinding.nextStep,
        evidenceRef: cleanFinding.id,
      };
      records.set(token, {
        organizationId, userId, expiresAt: now() + ttlMs,
        fingerprint: digest(input), idempotencyKey: null,
      });
      return { ...cleanFinding, evidenceAttestation: token };
    });
    return { ...payload, investigation: { ...payload.investigation, findings } };
  }

  function verify(raw, { organizationId, userId } = {}) {
    // Manual unreferenced proposals remain possible, but may NOT claim evidence.
    if (raw?.evidenceRef === undefined || raw?.evidenceRef === null) {
      return raw?.evidenceAttestation === undefined && { valid: true, stripped: raw };
    }
    if (typeof raw?.evidenceAttestation !== "string" ||
        !/^[A-Za-z0-9_-]{24,96}$/.test(raw.evidenceAttestation)) return { valid: false };
    prune();
    const record = records.get(raw.evidenceAttestation);
    if (!record || record.organizationId !== organizationId || record.userId !== userId ||
        record.expiresAt <= now()) return { valid: false };
    const { evidenceAttestation, ...stripped } = raw;
    const validated = validateAgentProposalInput(stripped);
    if (!validated || record.fingerprint !== digest({
      operation: validated.operation, targetSystem: validated.targetSystem,
      summary: validated.summary, rationale: validated.rationale, evidenceRef: validated.evidenceRef,
    }) || (record.idempotencyKey && record.idempotencyKey !== validated.idempotencyKey)) {
      return { valid: false };
    }
    return { valid: true, stripped, token: evidenceAttestation };
  }

  function bindIdempotencyKey(token, key) {
    const record = records.get(token);
    if (!record || record.expiresAt <= now() ||
        (record.idempotencyKey && record.idempotencyKey !== key)) return false;
    record.idempotencyKey = key;
    return true;
  }

  return { decorate, verify, bindIdempotencyKey };
}
