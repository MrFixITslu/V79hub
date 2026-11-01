import crypto from "node:crypto";

const hash = value => crypto.createHash("sha256").update(value).digest("hex");
const same = (a, b) => typeof a === "string" && typeof b === "string" &&
  a.length === b.length && crypto.timingSafeEqual(Buffer.from(a), Buffer.from(b));

/** Ephemeral, one-use authorisation grants bound to an existing MFA Hub session. */
export function createWebsiteSsoGrants({ now = Date.now, maxEntries = 500 } = {}) {
  const grants = new Map();
  const handles = new Map();
  function prune() {
    const time = now();
    for (const [key, row] of grants) if (row.expires <= time) grants.delete(key);
    for (const [key, row] of handles) if (row.expires <= time) handles.delete(key);
    while (grants.size >= maxEntries) grants.delete(grants.keys().next().value);
    while (handles.size >= maxEntries) handles.delete(handles.keys().next().value);
  }
  function issue({ challenge, sessionHash }) {
    prune();
    if (typeof challenge !== "string" || !/^[A-Za-z0-9_-]{43}$/.test(challenge) ||
        typeof sessionHash !== "string" || !/^[a-f0-9]{64}$/.test(sessionHash)) {
      throw Error("Invalid SSO handoff parameters");
    }
    const code = crypto.randomBytes(32).toString("base64url");
    grants.set(hash(code), { challenge, sessionHash, expires: now() + 60_000 });
    return code;
  }
  function consume({ code, verifier }) {
    prune();
    if (typeof code !== "string" || !/^[A-Za-z0-9_-]{43}$/.test(code) ||
        typeof verifier !== "string" || !/^[A-Za-z0-9_-]{43,128}$/.test(verifier)) return null;
    const key = hash(code);
    const item = grants.get(key);
    if (!item) return null;
    grants.delete(key); // Burn on first redemption, including an invalid proof.
    const challenge = crypto.createHash("sha256").update(verifier).digest("base64url");
    if (!same(item.challenge, challenge)) return null;
    const handle = crypto.randomBytes(32).toString("base64url");
    handles.set(hash(handle), { sessionHash: item.sessionHash, expires: now() + 30 * 60_000 });
    return handle;
  }
  function lookup(handle) {
    prune();
    if (typeof handle !== "string" || !/^[A-Za-z0-9_-]{43}$/.test(handle)) return null;
    return handles.get(hash(handle))?.sessionHash || null;
  }
  function revoke(handle) {
    if (typeof handle === "string") handles.delete(hash(handle));
  }
  return { issue, consume, lookup, revoke };
}
