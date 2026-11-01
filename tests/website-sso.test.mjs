import test from "node:test";
import assert from "node:assert/strict";
import crypto from "node:crypto";
import { createWebsiteSsoGrants } from "../server/website-sso.mjs";

const challenge = verifier => crypto.createHash("sha256").update(verifier).digest("base64url");
const verifier = crypto.randomBytes(32).toString("base64url");
const sessionHash = crypto.randomBytes(32).toString("hex");

test("single-use PKCE code: correct verifier, replay rejected, independent session handle", () => {
  let clock = 1_000_000;
  const grants = createWebsiteSsoGrants({ now: () => clock });
  const code = grants.issue({ challenge: challenge(verifier), sessionHash });
  assert.equal(typeof code, "string");
  assert.equal(grants.consume({ code, verifier: "different" }), null, "wrong verifier burns code");
  assert.equal(grants.consume({ code, verifier }), null);
  const code2 = grants.issue({ challenge: challenge(verifier), sessionHash });
  const handle = grants.consume({ code: code2, verifier });
  assert.match(handle, /^[A-Za-z0-9_-]{43}$/);
  assert.equal(grants.lookup(handle), sessionHash);
  assert.equal(grants.consume({ code: code2, verifier }), null, "code cannot be replayed");
  grants.revoke(handle);
  assert.equal(grants.lookup(handle), null, "handle revocation is enforced");
});

test("60-second authorisation grant TTL and 30-minute handle expiry", () => {
  let clock = 1_000_000;
  const grants = createWebsiteSsoGrants({ now: () => clock });
  const code = grants.issue({ challenge: challenge(verifier), sessionHash });
  clock += 60_001;
  assert.equal(grants.consume({ code, verifier }), null);
  const code2 = grants.issue({ challenge: challenge(verifier), sessionHash });
  const handle = grants.consume({ code: code2, verifier });
  clock += 30 * 60_000 + 1;
  assert.equal(grants.lookup(handle), null);
});

test("reject malformed PKCE challenges and missing session identity", () => {
  const grants = createWebsiteSsoGrants();
  assert.throws(() => grants.issue({ challenge: "bad", sessionHash }));
  assert.throws(() => grants.issue({ challenge: challenge(verifier), sessionHash: "bad" }));
});
