import assert from "node:assert/strict";
import test from "node:test";
import {
  base32Decode,
  base32Encode,
  decryptSecret,
  encryptSecret,
  totpCode,
  verifyTotp,
  createOpaqueToken,
  opaqueTokenHash,
  totpProvisioningUri,
} from "../server/security-contract.mjs";

test("base32 round-trips bytes", () => {
  const input = Buffer.from("V79 Hub security");
  assert.deepEqual(base32Decode(base32Encode(input)), input);
});

test("TOTP matches the RFC 6238 SHA-1 vector truncated to six digits", () => {
  const secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ";
  assert.equal(totpCode(secret, 59_000), "287082");
  assert.equal(verifyTotp(secret, "287082", 59_000), true);
  assert.equal(verifyTotp(secret, "000000", 59_000), false);
});

test("TOTP verification permits one adjacent 30 second window", () => {
  const secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ";
  const code = totpCode(secret, 60_000);
  assert.equal(verifyTotp(secret, code, 90_000, 1), true);
  assert.equal(verifyTotp(secret, code, 120_000, 1), false);
});

test("MFA secrets are encrypted and authenticated at rest", () => {
  const key = "v79-test-mfa-encryption-key-32-characters-minimum";
  const encrypted = encryptSecret("JBSWY3DPEHPK3PXP", key);
  assert.notEqual(encrypted, "JBSWY3DPEHPK3PXP");
  assert.equal(decryptSecret(encrypted, key), "JBSWY3DPEHPK3PXP");
  const [version, iv, tag, ciphertext] = encrypted.split(".");
  const tamperedBytes = Buffer.from(ciphertext, "base64url");
  tamperedBytes[0] ^= 0x01;
  const tampered = [version, iv, tag, tamperedBytes.toString("base64url")].join(".");
  assert.notEqual(tampered, encrypted);
  assert.throws(() => decryptSecret(tampered, key));
});


test("recovery tokens are opaque and hashed before persistence", () => {
  const one = createOpaqueToken();
  const two = createOpaqueToken();
  assert.notEqual(one, two);
  assert.match(opaqueTokenHash(one), /^[a-f0-9]{64}$/);
  assert.notEqual(opaqueTokenHash(one), opaqueTokenHash(two));
});

test("TOTP provisioning URI identifies V79 Hub and the account", () => {
  const uri = totpProvisioningUri({ secret: "JBSWY3DPEHPK3PXP", account: "vision79slu@gmail.com", issuer: "V79 Hub" });
  assert.match(uri, /^otpauth:\/\/totp\//);
  assert.match(uri, /secret=JBSWY3DPEHPK3PXP/);
  assert.match(uri, /issuer=V79\+Hub/);
});
