import test from "node:test";
import assert from "node:assert/strict";
import {
  createOpaqueToken,
  decryptTotpSecret,
  encryptTotpSecret,
  generateTotpSecret,
  opaqueTokenHash,
  totpCode,
  totpProvisioningUri,
  verifyTotp,
} from "../server/account-security.mjs";

test("TOTP matches RFC 6238 SHA1 vector truncated to six digits", () => {
  const secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ";
  assert.equal(totpCode(secret, 59_000), "287082");
  assert.equal(verifyTotp(secret, "287082", 59_000, 0), true);
  assert.equal(verifyTotp(secret, "000000", 59_000, 0), false);
});

test("MFA secrets encrypt and decrypt with authenticated encryption", () => {
  const secret = generateTotpSecret();
  const master = "test-master-secret-material-at-least-32-characters";
  const encrypted = encryptTotpSecret(secret, master);
  assert.match(encrypted, /^v1\./);
  assert.notEqual(encrypted.includes(secret), true);
  assert.equal(decryptTotpSecret(encrypted, master), secret);
  assert.throws(() => decryptTotpSecret(encrypted, master + "-wrong"));
});

test("opaque tokens are random and stored as hashes", () => {
  const one = createOpaqueToken();
  const two = createOpaqueToken();
  assert.notEqual(one, two);
  assert.match(opaqueTokenHash(one), /^[a-f0-9]{64}$/);
  assert.notEqual(opaqueTokenHash(one), opaqueTokenHash(two));
});

test("provisioning URI does not lose account identity", () => {
  const uri = totpProvisioningUri({
    secret: "JBSWY3DPEHPK3PXP",
    account: "owner@example.com",
    issuer: "V79 Hub",
  });
  assert.match(uri, /^otpauth:\/\/totp\//);
  assert.match(uri, /issuer=V79\+Hub/);
  assert.match(uri, /secret=JBSWY3DPEHPK3PXP/);
});
