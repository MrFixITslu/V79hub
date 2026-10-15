// V79 founder-only COO GitHub workboard. Disabled by default; GET-only, no writes.
// GitHub issues/PRs are engineering status, NEVER runtime health, Sentinel protection,
// security certification, customer readiness, or permission to execute an action.
const OWNER = "MrFixITslu";
const REPOS = Object.freeze(["V79hub", "V79Tiquet", "V79-Sentinel", "V79Marketing", "V79acaedmy", "V79POS"]);
const LANES = Object.freeze(["Hub + Tiquet", "CEO / COO", "Sentinel protection", "P2 apps"]);
const TRACKED = Object.freeze([
  ["Hub + Tiquet","V79hub",113,"issue","Commercial launch gates","Resolve outstanding customer security and recovery gates"],
  ["Hub + Tiquet","V79Tiquet",35,"issue","Session revocation","Complete independent customer-session review"],
  ["Hub + Tiquet","V79Tiquet",37,"pr","Session security candidate","Review exact cumulative draft; do not deploy automatically"],
  ["Hub + Tiquet","V79Tiquet",38,"pr","Staff WebSocket Hub parity","Independently review Hub-only entitlement policy and heartbeat"],
  ["Hub + Tiquet","V79Tiquet",39,"pr","Customer portal WebSocket revocation","Check rotated/revoked portal link with real disposable WebSocket and PostgreSQL"],
  ["CEO / COO","V79hub",152,"issue","AI workforce coordination","Prioritize verified work and founder decisions"],
  ["CEO / COO","V79hub",138,"issue","Executive pilot acceptance","Verify installed owner-only CEO/COO runtime"],
  ["CEO / COO","V79hub",145,"pr","Approved-action queue","Preserve signed MFA approval boundary"],
  ["CEO / COO","V79hub",153,"pr","COO workboard source","Review draft code and safe evidence semantics"],
  ["Sentinel protection","V79-Sentinel",15,"issue","V79-owned service protection","Validate actual owned targets and collector freshness"],
  ["Sentinel protection","V79-Sentinel",14,"pr","NOC isolated deployment","Resolve GitGuardian hold before staging"],
  ["Sentinel protection","V79-Sentinel",16,"pr","Owned HTTPS advisory","Validate owned targets, freshness, and source boundary"],
  ["Sentinel protection","V79-Sentinel",17,"pr","Signed observation verifier","Review pinned key custody and live measurement evidence"],
  ["Sentinel protection","V79-Sentinel",18,"pr","Durable signed replay checkpoint","Review atomic disk state, restart and rotation controls"],
  ["Sentinel protection","V79hub",124,"issue","Signed Sentinel COO evidence","Do not promote simulated data to trusted telemetry"],
  ["P2 apps","V79acaedmy",25,"issue","Academy publishing","Reproduce password / catalog boundary in isolation"],
  ["P2 apps","V79acaedmy",26,"pr","Academy publishing test","Decide Academy-only or website catalog after isolated reproduction"],
  ["P2 apps","V79POS",12,"issue","POS direct dashboard SSO","Test Hub-launched and signed-out routing"],
  ["P2 apps","V79Marketing",28,"pr","Marketing publication tracking","Verify actual provider receipt, not a simulated success"]
]);
const MAX_BYTES = 1024 * 1024;
const MAX_PAGES = 2;

async function boundedJson(response) {
  const length = response.headers.get("content-length");
  if (length && (!/^\d+$/.test(length) || Number(length) > MAX_BYTES)) throw new Error("INVALID_SIZE");
  if (!response.body?.getReader) throw new Error("NO_STREAM");
  const reader = response.body.getReader();
  const parts = [];
  let total = 0, done = false;
  try {
    while (true) {
      const next = await reader.read();
      if (next.done) { done = true; break; }
      total += next.value.byteLength;
      if (total > MAX_BYTES) throw new Error("TOO_LARGE");
      parts.push(Buffer.from(next.value));
    }
  } finally {
    if (!done) await reader.cancel().catch(() => {});
  }
  return JSON.parse(Buffer.concat(parts).toString("utf8"));
}

export async function readCooGithubRepo(repo, token, { fetchImpl = fetch, timeoutMs = 5000 } = {}) {
  if (!REPOS.includes(repo) || typeof token !== "string" || token.length < 16) {
    return { state: "UNAVAILABLE", entries: {} };
  }
  const entries = {};
  try {
    for (let page = 1; page <= MAX_PAGES; page++) {
      // Fixed URL, fixed API host, no URL from caller or provider response.
      const url = `https://api.github.com/repos/${OWNER}/${repo}/issues?state=open&per_page=100&page=${page}`;
      const response = await fetchImpl(url, {
        method: "GET",
        redirect: "manual",
        headers: { accept: "application/vnd.github+json",
          "x-github-api-version": "2022-11-28",
          authorization: `Bearer ${token}`,
          "user-agent": "v79-coo-readonly-workboard" },
        signal: AbortSignal.timeout(timeoutMs),
      });
      if (!response.ok || response.status >= 300) throw new Error("GITHUB_UNAVAILABLE");
      const body = await boundedJson(response);
      if (!Array.isArray(body) || body.length > 100) throw new Error("INVALID_PAGE");
      for (const row of body) {
        if (!row || typeof row !== "object" || !Number.isSafeInteger(row.number) || row.number <= 0 ||
            Object.hasOwn(entries, row.number)) throw new Error("INVALID_ENTRY");
        // Do NOT include GitHub-controlled title, body, paths, URLs or attachments.
        entries[row.number] = { kind: Object.hasOwn(row, "pull_request") ? "pr" : "issue",
          updatedAt: typeof row.updated_at === "string" && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(row.updated_at) &&
            Number.isFinite(Date.parse(row.updated_at)) ? row.updated_at : null };
      }
      if (body.length < 100) return { state: "COMPLETE", entries };
    }
    return { state: "INCOMPLETE", entries };
  } catch {
    // Do not echo API responses, network errors, token or remote issue text.
    return { state: "UNAVAILABLE", entries: {} };
  }
}

export function formatCooWorkboard(sources, collectedAt) {
  const repositories = REPOS.map(repo => ({ repo,
    fetchState: sources[repo]?.state || "UNAVAILABLE" }));
  const tracked = TRACKED.map(([lane, repo, number, kind, label, nextStep]) => {
    const source = sources[repo] || { state: "UNAVAILABLE", entries: {} };
    const record = source.entries?.[number];
    let githubState = "UNKNOWN_SOURCE";
    if (source.state === "COMPLETE" || source.state === "INCOMPLETE") {
      githubState = record?.kind === kind ? "OPEN_IN_GITHUB"
        : source.state === "COMPLETE" ? "NOT_LISTED_AS_OPEN" : "UNKNOWN_INCOMPLETE";
    }
    return {
      lane, repo, number, kind, label, nextStep, githubState,
      url: `https://github.com/${OWNER}/${repo}/${kind === "pr" ? "pull" : "issues"}/${number}`,
      updatedAt: githubState === "OPEN_IN_GITHUB" ? record?.updatedAt ?? null : null,
    };
  });
  return {
    mode: "read-only", source: "github-issue-pr-register", collectedAt,
    lanes: LANES, repositories, tracked,
    runtimeHealth: "UNKNOWN", deployedRevision: "UNKNOWN",
    customerLaunchGo: "NOT_ESTABLISHED", sentinelCoverage: "NOT_ESTABLISHED",
    approvalGranted: false, executionEnabled: false,
    caveat: "GitHub work status does not prove live uptime, customer readiness, or monitored devices.",
  };
}

export function createOwnerCooWorkboard({ ownerMfaContext, enabled, readToken,
  fetchImpl = fetch, now = () => new Date().toISOString() }) {
  if (typeof ownerMfaContext !== "function" || typeof enabled !== "function" ||
      typeof readToken !== "function") throw new Error("Missing workboard security dependencies");
  return async (req, res) => {
    res.setHeader("Cache-Control", "no-store");
    if (!ownerMfaContext(req)) return res.status(403).json({ error: "MFA-verified founder required" });
    const blank = Object.fromEntries(REPOS.map(repo => [repo, { state: "UNAVAILABLE", entries: {} }]));
    if (!enabled()) return res.json({ ...formatCooWorkboard(blank, now()), connection: "DISABLED" });
    let token = "";
    try { token = readToken(); } catch { /* fail closed */ }
    if (typeof token !== "string" || token.trim().length < 16 || token.trim().length > 256 || /\s/.test(token.trim())) {
      return res.json({ ...formatCooWorkboard(blank, now()), connection: "NOT_CONFIGURED" });
    }
    const result = await Promise.all(REPOS.map(async repo => [repo, await readCooGithubRepo(repo, token.trim(), { fetchImpl })]));
    const sources = Object.fromEntries(result);
    const connected = Object.values(sources).some(item => item.state === "COMPLETE");
    return res.json({ ...formatCooWorkboard(sources, now()),
      connection: connected ? "PARTIAL_OR_COMPLETE" : "UNAVAILABLE" });
  };
}
