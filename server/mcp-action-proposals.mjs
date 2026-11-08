// Dedicated MCP proposal ingress. Never accept MCP OAuth tokens, owner cookies,
// arbitrary downstream endpoints or execution requests at this boundary.
import express from "express";
import { createHash, createHmac, timingSafeEqual } from "node:crypto";
import { proposeWork, validateWorkRequest } from "./workforce-actions.mjs";

export const MCP_PROPOSAL_PATH = "/internal/mcp/v1/proposals";
const SECRET_MIN = 32;
const MAX_BYTES = 8192;
const MAX_CLOCK_SKEW_MS = 120_000;
const MAX_PER_MINUTE = 20;
const NONCE = /^[A-Za-z0-9_-]{22,96}$/;
const SIGNATURE = /^[a-f0-9]{64}$/;
const TIME = /^[0-9]{13}$/;

export function signMcpProposal({ key, timestamp, nonce, body }) {
  const raw = Buffer.isBuffer(body) ? body : Buffer.from(body);
  return createHmac("sha256", key)
    .update(["POST", MCP_PROPOSAL_PATH, String(timestamp), nonce,
      createHash("sha256").update(raw).digest("hex")].join("\n"))
    .digest("hex");
}

export function verifyMcpProposal({ method, path, contentType, origin, cookie,
  authorization, timestamp, nonce, signature, rawBody, key, now = Date.now() }) {
  if (method !== "POST" || path !== MCP_PROPOSAL_PATH ||
      String(contentType || "").toLowerCase().split(";")[0].trim() !== "application/json" ||
      origin || cookie || authorization ||
      typeof key !== "string" || key.length < SECRET_MIN ||
      !Buffer.isBuffer(rawBody) || rawBody.length < 2 || rawBody.length > MAX_BYTES ||
      !TIME.test(String(timestamp || "")) || !NONCE.test(String(nonce || "")) ||
      !SIGNATURE.test(String(signature || "")) || !Number.isFinite(now) ||
      Math.abs(now - Number(timestamp)) > MAX_CLOCK_SKEW_MS) return false;
  const expected = signMcpProposal({ key, timestamp, nonce, body: rawBody });
  return timingSafeEqual(Buffer.from(expected, "hex"), Buffer.from(signature, "hex"));
}

const exact = (value, names) => Boolean(value && typeof value === "object" &&
  !Array.isArray(value) &&
  Object.keys(value).sort().join(",") === [...names].sort().join(","));

/**
 * Only propose an owner-reviewed Hub work item.
 * An MCP client cannot approve, execute, send, publish, bill or deploy.
 * The existing Hub owner decision + fresh MFA / worker policies are unchanged.
 */
export function createMcpProposalRouter({ ledger, enabled, secret, ownerReady,
  ownerOrganizationId, now = Date.now }) {
  const router = express.Router();
  const requests = [];
  router.use((_req, res, next) => {
    res.setHeader("Cache-Control", "no-store");
    res.setHeader("X-V79-MCP-Mode", "proposal-only");
    next();
  });
  router.post("/", async (req, res) => {
    if (!enabled() || !ledger || !ownerReady()) {
      return res.status(503).json({ code: "MCP_PROPOSALS_DISABLED" });
    }
    const at = now();
    const key = secret();
    if (!verifyMcpProposal({
      method: req.method, path: MCP_PROPOSAL_PATH,
      contentType: req.get("content-type"), origin: req.get("origin"),
      cookie: req.get("cookie"), authorization: req.get("authorization"),
      timestamp: req.get("x-v79-mcp-timestamp"),
      nonce: req.get("x-v79-mcp-nonce"),
      signature: req.get("x-v79-mcp-signature"),
      rawBody: req.rawBody, key, now: at,
    })) return res.status(403).json({ code: "MCP_PROPOSAL_AUTH_DENIED" });

    while (requests.length && requests[0] < at - 60_000) requests.shift();
    if (requests.length >= MAX_PER_MINUTE) {
      return res.status(429).json({ code: "MCP_PROPOSAL_RATE_LIMIT" });
    }
    requests.push(at);

    if (!exact(req.body, ["operation", "system", "summary", "payload", "idempotencyKey"])) {
      return res.status(400).json({ code: "MCP_PROPOSAL_FORMAT_DENIED" });
    }
    let input;
    try {
      input = validateWorkRequest(req.body);
      if (input.operation !== "create_work_item" || input.system !== "hub") {
        return res.status(403).json({ code: "MCP_TOOL_NOT_ALLOWED" });
      }
    } catch {
      return res.status(400).json({ code: "MCP_PROPOSAL_INVALID" });
    }

    try {
      // Identity comes from trusted Hub configuration, never the MCP request.
      const organizationId = ownerOrganizationId();
      if (typeof organizationId !== "string" || organizationId.length < 5) {
        return res.status(503).json({ code: "MCP_OWNER_SCOPE_UNAVAILABLE" });
      }
      const job = await ledger.transact(state => proposeWork(state, input, {
        organizationId, actor: "mcp-action-broker", now: at,
      }));
      return res.status(201).json({
        proposal: {
          id: job.id, revision: job.revision, status: job.status,
          digest: job.digest, system: job.system,
          expiresAt: job.expiresAt,
        },
        approval: "Founder review required in Hub. MCP cannot approve or execute.",
      });
    } catch (error) {
      if (error?.message === "Idempotency conflict") {
        return res.status(409).json({ code: "MCP_IDEMPOTENCY_CONFLICT" });
      }
      return res.status(503).json({ code: "MCP_PROPOSAL_NOT_COMMITTED" });
    }
  });
  router.all("/", (_req, res) => res.status(405).json({ code: "MCP_METHOD_DENIED" }));
  return router;
}
