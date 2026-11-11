import test from "node:test";
import assert from "node:assert/strict";
import { createOwnerMfaStepUp } from "../server/owner-mfa-step-up.mjs";

function fixture(overrides = {}) {
  let time = 1_800_000_000_000, saves = 0;
  const session = { userId: "owner", mfaVerified: true, mfaVerifiedAt: time - 600_000 };
  const handler = createOwnerMfaStepUp({
    ownerContext: () => ({ userId: "owner" }), sameOrigin: () => true,
    getSecret: () => "synthetic-totp-secret", verifyCode: (_s, code) => code === "123456",
    persistSession: () => { saves++; }, now: () => time, ...overrides,
  });
  function invoke(code = "123456") {
    const req = { user: session, body: { code } };
    const result = { statusCode: 200, headers: {}, json: null };
    const res = { setHeader: (k,v) => { result.headers[k] = v; },
      status: v => { result.statusCode = v; return res; },
      json: v => { result.json = v; return res; } };
    handler(req,res);
    return result;
  }
  return { invoke, session, saves: () => saves, advance: v => { time += v; }, time: () => time };
}
test("step-up renews only a previously authenticated owner session and persists timestamp", () => {
  const f = fixture();
  const r = f.invoke();
  assert.equal(r.statusCode, 200);
  assert.equal(r.json.verified, true);
  assert.equal(f.session.mfaVerifiedAt, f.time());
  assert.equal(f.saves(), 1);
  assert.deepEqual(Object.keys(r.json).sort(), ["validUntil", "verified"]);
});
test("step-up denies unauthorised owners and cross-origin requests", () => {
  assert.equal(fixture({ownerContext:()=>null}).invoke().statusCode,403);
  assert.equal(fixture({sameOrigin:()=>false}).invoke().statusCode,403);
});
test("step-up requires a six digit code", () => {
  const f = fixture();
  assert.equal(f.invoke("12345").statusCode,400);
  assert.equal(f.invoke("1234567").statusCode,400);
  assert.equal(f.saves(),0);
});
test("step-up rate limits wrong codes without changing authentication state", () => {
  const f = fixture();
  const original = f.session.mfaVerifiedAt;
  for (let i = 0; i < 5; i++) assert.equal(f.invoke("000000").statusCode,401);
  assert.equal(f.invoke().statusCode,429);
  assert.equal(f.session.mfaVerifiedAt,original);
  assert.equal(f.saves(),0);
  f.advance(15 * 60_000 + 1);
  assert.equal(f.invoke().statusCode,200);
});
test("step-up rolls back freshness if durable session persistence fails", () => {
  const f = fixture({persistSession:()=>{throw new Error("fake disk failure")}});
  const old = f.session.mfaVerifiedAt;
  assert.equal(f.invoke().statusCode,503);
  assert.equal(f.session.mfaVerifiedAt,old);
});
