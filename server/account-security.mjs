import crypto from "node:crypto";

const ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";

function base32Encode(buffer) {
  let bits = 0;
  let value = 0;
  let output = "";
  for (const byte of buffer) {
    value = (value << 8) | byte;
    bits += 8;
    while (bits >= 5) {
      output += ALPHABET[(value >>> (bits - 5)) & 31];
      bits -= 5;
    }
  }
  if (bits > 0) output += ALPHABET[(value << (5 - bits)) & 31];
  return output;
}

function base32Decode(input) {
  const clean = String(input || "").toUpperCase().replace(/[^A-Z2-7]/g, "");
  let bits = 0;
  let value = 0;
  const bytes = [];
  for (const char of clean) {
    const index = ALPHABET.indexOf(char);
    if (index < 0) throw new Error("Invalid base32 secret.");
    value = (value << 5) | index;
    bits += 5;
    if (bits >= 8) {
      bytes.push((value >>> (bits - 8)) & 255);
      bits -= 8;
    }
  }
  return Buffer.from(bytes);
}

function hotp(secret, counter, digits = 6) {
  const key = base32Decode(secret);
  const counterBuffer = Buffer.alloc(8);
  counterBuffer.writeBigUInt64BE(BigInt(counter));
  const digest = crypto.createHmac("sha1", key).update(counterBuffer).digest();
  const offset = digest[digest.length - 1] & 0x0f;
  const binary =
    ((digest[offset] & 0x7f) << 24) |
    ((digest[offset + 1] & 0xff) << 16) |
    ((digest[offset + 2] & 0xff) << 8) |
    (digest[offset + 3] & 0xff);
  return String(binary % (10 ** digits)).padStart(digits, "0");
}

export function generateTotpSecret(bytes = 20) {
  return base32Encode(crypto.randomBytes(bytes));
}

export function totpCode(secret, timestamp = Date.now(), digits = 6, periodSeconds = 30) {
  const counter = Math.floor(timestamp / 1000 / periodSeconds);
  return hotp(secret, counter, digits);
}

export function verifyTotp(secret, code, timestamp = Date.now(), window = 1) {
  const supplied = String(code || "").trim();
  if (!/^\d{6}$/.test(supplied)) return false;
  const counter = Math.floor(timestamp / 1000 / 30);
  for (let drift = -window; drift <= window; drift += 1) {
    const expected = hotp(secret, counter + drift, 6);
    const left = Buffer.from(expected);
    const right = Buffer.from(supplied);
    if (left.length === right.length && crypto.timingSafeEqual(left, right)) return true;
  }
  return false;
}

function securityKey(masterSecret) {
  const source = Buffer.from(String(masterSecret || ""));
  if (source.length < 32) throw new Error("Hub security key material must be at least 32 characters.");
  return Buffer.from(crypto.hkdfSync(
    "sha256",
    source,
    Buffer.from("v79-hub-security-v1"),
    Buffer.from("totp-secret-encryption"),
    32,
  ));
}

export function encryptTotpSecret(secret, masterSecret) {
  const key = securityKey(masterSecret);
  const iv = crypto.randomBytes(12);
  const cipher = crypto.createCipheriv("aes-256-gcm", key, iv);
  const encrypted = Buffer.concat([cipher.update(String(secret), "utf8"), cipher.final()]);
  const tag = cipher.getAuthTag();
  return ["v1", iv.toString("base64url"), tag.toString("base64url"), encrypted.toString("base64url")].join(".");
}

export function decryptTotpSecret(value, masterSecret) {
  const [version, ivText, tagText, encryptedText] = String(value || "").split(".");
  if (version !== "v1" || !ivText || !tagText || !encryptedText) throw new Error("Invalid encrypted MFA secret.");
  const key = securityKey(masterSecret);
  const decipher = crypto.createDecipheriv("aes-256-gcm", key, Buffer.from(ivText, "base64url"));
  decipher.setAuthTag(Buffer.from(tagText, "base64url"));
  return Buffer.concat([
    decipher.update(Buffer.from(encryptedText, "base64url")),
    decipher.final(),
  ]).toString("utf8");
}

export function totpProvisioningUri({ secret, account, issuer = "V79 Hub" }) {
  const label = encodeURIComponent(`${issuer}:${account}`);
  const query = new URLSearchParams({
    secret,
    issuer,
    algorithm: "SHA1",
    digits: "6",
    period: "30",
  });
  return `otpauth://totp/${label}?${query.toString()}`;
}

export function createOpaqueToken(bytes = 32) {
  return crypto.randomBytes(bytes).toString("base64url");
}

export function opaqueTokenHash(token) {
  return crypto.createHash("sha256").update(String(token || "")).digest("hex");
}
