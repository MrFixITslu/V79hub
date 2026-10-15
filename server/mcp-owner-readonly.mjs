// INTERNAL V79 MCP downstream-read contract, disabled by default at routing layer.
// Not an OAuth Authorization Server. These are separately issued short-lived,
// audience-bound downstream assertions; NEVER forward an inbound MCP bearer token.
// This module has no networking, storage writes or dependencies beyond node:crypto.
import crypto from "node:crypto";
import { activeMembership, enabledAppIds } from "./organization-access.mjs";
import { hasOwnerAssistantAccess } from "./agent-access.mjs";

export class McpReadDenied extends Error {
  constructor(code) { super(code); this.name = "McpReadDenied"; this.code = code; }
}
const deny = code => { throw new McpReadDenied(code); };
const allowedKeys = (obj, keys) => obj && typeof obj === "object" &&
  !Array.isArray(obj) && Object.keys(obj).sort().join("|") === [...keys].sort().join("|");
const CLAIM_KEYS = ["iss","aud","sub","tenant","client_id","agent_id","scope","iat","nbf","exp","jti","acr","auth_time"];
const HEADER_KEYS = ["alg","typ","kid"];
const TEXT = /^[A-Za-z0-9._:@-]{3,128}$/;

function decodeCanonicalPart(part) {
  if (typeof part !== "string" || !/^[A-Za-z0-9_-]+$/.test(part)) deny("MALFORMED_ASSERTION");
  const bytes = Buffer.from(part, "base64url");
  if (bytes.toString("base64url") !== part || bytes.length > 2048) deny("MALFORMED_ASSERTION");
  const text = bytes.toString("utf8");
  let value;
  try { value = JSON.parse(text); } catch { deny("MALFORMED_ASSERTION"); }
  // Intentional strict profile: reject duplicate members, whitespace and
  // ambiguous JSON representations instead of accepting arbitrary JWT claims.
  // The approved downstream issuer must use this exact JSON serialization.
  if (JSON.stringify(value) !== text) deny("NONCANONICAL_ASSERTION");
  return value;
}

export function verifyMcpDownstreamAssertion({
  token, publicKeyPem, kid, issuer, now = Date.now(),
}) {
  if (typeof token !== "string" || token.length > 4096 || token.split(".").length !== 3)
    deny("MISSING_ASSERTION");
  if (!publicKeyPem || !issuer || !kid || !Number.isSafeInteger(now))
    deny("TRUST_NOT_CONFIGURED");
  const [head, body, sig] = token.split(".");
  const header = decodeCanonicalPart(head);
  const claim = decodeCanonicalPart(body);
  if (!allowedKeys(header, HEADER_KEYS) || header.alg !== "RS256" ||
      header.typ !== "at+jwt" || header.kid !== kid) deny("UNTRUSTED_HEADER");
  if (!allowedKeys(claim, CLAIM_KEYS)) deny("INVALID_CLAIMS");
  if (claim.iss !== issuer || claim.aud !== "v79-hub-mcp-readonly" ||
      claim.client_id !== "v79-mcp-internal" ||
      !["v79-ceo","v79-coo"].includes(claim.agent_id) ||
      claim.scope !== "hub.apps.read" || claim.acr !== "urn:v79:mfa") deny("WRONG_AUDIENCE_SCOPE_OR_AGENT");
  for (const field of ["sub","tenant","jti"])
    if (typeof claim[field] !== "string" || !TEXT.test(claim[field])) deny("INVALID_IDENTITY");
  for (const field of ["iat","nbf","exp","auth_time"])
    if (!Number.isSafeInteger(claim[field])) deny("INVALID_LIFETIME");
  const clock = Math.floor(now / 1000);
  if (claim.auth_time > clock || clock - claim.auth_time > 900 ||
      claim.iat > clock + 10 || claim.nbf > clock || claim.exp <= clock ||
      claim.exp - claim.iat > 120 || claim.exp <= claim.iat)
    deny("EXPIRED_OR_INVALID_LIFETIME");
  if (!/^[A-Za-z0-9_-]+$/.test(sig)) deny("MALFORMED_SIGNATURE");
  let key;
  try {
    key = crypto.createPublicKey(publicKeyPem);
    if (key.asymmetricKeyType !== "rsa" || key.asymmetricKeyDetails?.modulusLength < 2048)
      deny("UNTRUSTED_KEY");
  } catch { deny("TRUST_NOT_CONFIGURED"); }
  let signature;
  try {
    signature = Buffer.from(sig, "base64url");
    if (signature.toString("base64url") !== sig || !crypto.verify(
      "RSA-SHA256", Buffer.from(head + "." + body, "ascii"), key, signature
    )) deny("BAD_SIGNATURE");
  } catch (error) {
    if (error instanceof McpReadDenied) throw error;
    deny("BAD_SIGNATURE");
  }
  return Object.freeze({
    userId: claim.sub, organizationId: claim.tenant,
    agentId: claim.agent_id, clientId: claim.client_id, jti: claim.jti,
  });
}

export function ownerMcpAppProjection({
  identity, store, ownerOrganizationId, ownerUserId, ownerEmail = "vision79slu@gmail.com",
  now = Date.now(),
}) {
  if (!identity || !store || identity.organizationId !== ownerOrganizationId ||
      identity.userId !== ownerUserId) deny("OWNER_BOUNDARY_DENIED");
  const user = (store.users || []).find(item => item.id === ownerUserId);
  const membership = activeMembership(store, ownerUserId, ownerOrganizationId);
  if (user?.mfaEnabled !== true) deny("MFA_REQUIRED");
  if (!hasOwnerAssistantAccess({
    user, membership, organizationId: identity.organizationId,
    ownerOrganizationId, ownerUserId, ownerEmail,
  })) deny("OWNER_MEMBERSHIP_DENIED");
  const enabled = new Set(enabledAppIds(store, ownerOrganizationId, ownerOrganizationId, now));
  const apps = (store.ecosystemApps || []).filter(a => enabled.has(a.id))
    .filter(a => !a.id.startsWith("app-custom-") || a.ownerOrganizationId === ownerOrganizationId)
    .slice(0, 50).map(a => ({
      id: String(a.id).slice(0, 80),
      name: String(a.name || "").slice(0, 100),
    }));
  return { apps, readOnly: true, tenantScoped: true };
}

export function mcpReadAccessDecision({ enabled, method, authorization, cookie, tokenOptions,
                                     store, ownerOrganizationId, ownerUserId, ownerEmail, now }) {
  if (enabled !== true) return { status: 404, error: "MCP_DISABLED" };
  if (method !== "GET") return { status: 405, error: "METHOD_NOT_ALLOWED" };
  if (cookie || typeof authorization !== "string" ||
      !/^Bearer [A-Za-z0-9_.-]+$/.test(authorization))
    return { status: 401, error: "MCP_ACCESS_DENIED" };
  try {
    const identity = verifyMcpDownstreamAssertion({
      ...tokenOptions, token: authorization.slice(7), now
    });
    return { status: 200, body: ownerMcpAppProjection({
      identity, store, ownerOrganizationId, ownerUserId, ownerEmail, now
    }) };
  } catch (error) {
    const isMembershipDenial = error instanceof McpReadDenied &&
      ["OWNER_BOUNDARY_DENIED", "OWNER_MEMBERSHIP_DENIED", "MFA_REQUIRED"].includes(error.code);
    return { status: isMembershipDenial ? 403 : 401, error: "MCP_ACCESS_DENIED" };
  }
}
