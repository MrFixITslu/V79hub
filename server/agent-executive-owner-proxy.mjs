// Owner-only, MFA-verified, read-only executive endpoints.
// Fixed upstream paths; no arbitrary client path, URL or evidence is forwarded.
const ROUTES = Object.freeze({
  structure: Object.freeze({ method: "GET", path: "/api/agent/executive-structure" }),
  handoff: Object.freeze({ method: "POST", path: "/api/agent/executive-handoff" }),
  preview: Object.freeze({ method: "POST", path: "/api/agent/executive-preview" }),
});

const MAX_RESPONSE_BYTES = 128 * 1024;

export function createOwnerExecutiveProxy(kind, {
  ownerMfaContext,
  readServiceToken,
  agentBaseUrl,
  fetchImpl = fetch,
  timeoutMs = 20_000,
}) {
  if (!Object.hasOwn(ROUTES, kind)) throw new Error("Unsupported executive endpoint");
  const route = ROUTES[kind];
  if (typeof ownerMfaContext !== "function" || typeof readServiceToken !== "function") {
    throw new Error("Missing executive auth dependencies");
  }
  const base = new URL(agentBaseUrl);
  if (!["http:", "https:"].includes(base.protocol) || base.username || base.password ||
      base.pathname !== "/" || base.search || base.hash) {
    throw new Error("Invalid internal agent service URL");
  }

  return async function ownerExecutiveHandler(req, res) {
    res.setHeader("Cache-Control", "no-store");
    const context = ownerMfaContext(req);
    if (!context) return res.status(403).json({ error: "MFA-verified owner access required." });
    const token = readServiceToken();
    if (!token) return res.status(503).json({ error: "Owner Assistant service is not configured." });

    try {
      const headers = {
        "x-v79-agent-token": token,
        "accept": "application/json",
      };
      if (route.method === "POST") headers["content-type"] = "application/json";
      const response = await fetchImpl(new URL(route.path, base), {
        method: route.method,
        headers,
        ...(route.method === "POST" ? { body: JSON.stringify({ context }) } : {}),
        redirect: "manual",
        signal: AbortSignal.timeout(timeoutMs),
      });
      if (response.status >= 300 && response.status < 400) {
        return res.status(502).json({ error: "Owner Assistant returned an unexpected redirect." });
      }
      const advertised = Number(response.headers.get("content-length"));
      if (Number.isFinite(advertised) && advertised > MAX_RESPONSE_BYTES) {
        return res.status(502).json({ error: "Owner Assistant response exceeded size limit." });
      }
      const raw = await response.text();
      if (Buffer.byteLength(raw, "utf8") > MAX_RESPONSE_BYTES) {
        return res.status(502).json({ error: "Owner Assistant response exceeded size limit." });
      }
      let body;
      try { body = JSON.parse(raw); } catch {
        return res.status(502).json({ error: "Owner Assistant returned invalid JSON." });
      }
      if (body === null || typeof body !== "object" || Array.isArray(body)) {
        return res.status(502).json({ error: "Owner Assistant returned invalid data." });
      }
      // Disallow upstream cookies/headers, and return only structured data.
      return res.status(response.status).json(body);
    } catch {
      return res.status(502).json({ error: "Owner Assistant service is unavailable." });
    }
  };
}
