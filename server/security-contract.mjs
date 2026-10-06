import crypto from "node:crypto";

const BASE32_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";

export function base32Encode(input) {
  const bytes = Buffer.isBuffer(input) ? input : Buffer.from(input);
  let bits = "";
  for (const byte of bytes) bits += byte.toString(2).padStart(8, "0");
  let output = "";
  for (let i = 0; i < bits.length; i += 5) {
    const chunk = bits.slice(i, i + 5).padEnd(5, "0");
    output += BASE32_ALPHABET[Number.parseInt(chunk, 2)];
  }
  return output;
}

export function base32Decode(value) {
  const normalized = String(value || "").toUpperCase().replace(/=+$/g, "").replace(/\s+/g, "");
  if (!normalized || /[^A-Z2-7]/.test(normalized)) throw new Error("Invalid base32 secret.");
  let bits = "";
  for (const char of normalized) bits += BASE32_ALPHABET.indexOf(char).toString(2).padStart(5, "0");
  const bytes = [];
  for (let i = 0; i + 8 <= bits.length; i += 8) bytes.push(Number.parseInt(bits.slice(i, i + 8), 2));
  return Buffer.from(bytes);
}

export function generateTotpSecret(bytes = 20) {
  return base32Encode(crypto.randomBytes(bytes));
}

function hotp(secret, counter, digits = 6) {
  const counterBuffer = Buffer.alloc(8);
  counterBuffer.writeBigUInt64BE(BigInt(counter));
  const digest = crypto.createHmac("sha1", base32Decode(secret)).update(counterBuffer).digest();
  const offset = digest[digest.length - 1] & 0x0f;
  const binary =
    ((digest[offset] & 0x7f) << 24) |
    ((digest[offset + 1] & 0xff) << 16) |
    ((digest[offset + 2] & 0xff) << 8) |
    (digest[offset + 3] & 0xff);
  return String(binary % (10 ** digits)).padStart(digits, "0");
}

export function totpCode(secret, now = Date.now(), periodSeconds = 30, digits = 6) {
  const counter = Math.floor(now / 1000 / periodSeconds);
  return hotp(secret, counter, digits);
}

export function verifyTotp(secret, code, now = Date.now(), window = 1) {
  const candidate = String(code || "").replace(/\s+/g, "");
  if (!/^\d{6}$/.test(candidate)) return false;
  const counter = Math.floor(now / 1000 / 30);
  for (let offset = -window; offset <= window; offset++) {
    const expected = hotp(secret, counter + offset, 6);
    const left = Buffer.from(expected);
    const right = Buffer.from(candidate);
    if (left.length === right.length && crypto.timingSafeEqual(left, right)) return true;
  }
  return false;
}

function deriveKey(keyMaterial) {
  const material = String(keyMaterial || "");
  if (material.length < 32) throw new Error("MFA encryption key must contain at least 32 characters.");
  return crypto.createHash("sha256").update(material).digest();
}

export function encryptSecret(secret, keyMaterial) {
  const iv = crypto.randomBytes(12);
  const cipher = crypto.createCipheriv("aes-256-gcm", deriveKey(keyMaterial), iv);
  const ciphertext = Buffer.concat([cipher.update(String(secret), "utf8"), cipher.final()]);
  const tag = cipher.getAuthTag();
  return ["v1", iv.toString("base64url"), tag.toString("base64url"), ciphertext.toString("base64url")].join(".");
}

export function decryptSecret(payload, keyMaterial) {
  const [version, ivText, tagText, ciphertextText] = String(payload || "").split(".");
  if (version !== "v1" || !ivText || !tagText || !ciphertextText) throw new Error("Invalid encrypted MFA secret.");
  const decipher = crypto.createDecipheriv("aes-256-gcm", deriveKey(keyMaterial), Buffer.from(ivText, "base64url"));
  decipher.setAuthTag(Buffer.from(tagText, "base64url"));
  return Buffer.concat([
    decipher.update(Buffer.from(ciphertextText, "base64url")),
    decipher.final(),
  ]).toString("utf8");
}


export function totpProvisioningUri({ secret, account, issuer = "V79 Hub" }) {
  const label = encodeURIComponent(`${issuer}:${account}`);
  const query = new URLSearchParams({
    secret: String(secret),
    issuer: String(issuer),
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
