import { createHash, createHmac } from "node:crypto";

// Signed product-to-Hub entitlement validation. Never accept user identity from a client payload.
export function createHubEntitlementChecker({ product, hubUrl, secret, now = Date.now, transport = fetch }) {
  if (!["tiquet", "ffpro", "marketing", "pos"].includes(product)) throw new Error("Invalid product");
  if (!/^https?:\/\//.test(hubUrl || "") || String(secret || "").length < 32) {
    throw new Error("Hub entitlement validation is not securely configured");
  }
  const url = new URL("/api/platform/entitlement/check", hubUrl);
  const pathname = url.pathname;
  const cached = new Map();
  return async ({ organizationId, scopedUserId }) => {
    if (!organizationId || !scopedUserId) return false;
    const key = JSON.stringify([organizationId, scopedUserId]);
    const current = now();
    if ((cached.get(key) || 0) > current) return true;
    cached.delete(key);
    const body = JSON.stringify({ product, organizationId, scopedUserId });
    const timestamp = String(current);
    const contentHash = createHash("sha256").update(body).digest("hex");
    const canonical = ["POST", pathname, timestamp, contentHash].join("\n");
    const signature = createHmac("sha256", secret).update(canonical).digest("hex");
    try {
      const response = await transport(url.toString(), {
        method: "POST", body,
        headers: {
          "content-type":"application/json",
          "x-v79-service-id": "v79-" + product,
          "x-v79-timestamp": timestamp,
          "x-v79-signature": signature,
        },
        signal: AbortSignal.timeout(3500),
      });
      if (!response.ok) return false;
      const result = await response.json();
      const seconds = Number(result?.validForSeconds);
      if (result?.allowed !== true || !Number.isFinite(seconds) || seconds < 1) return false;
      cached.set(key, now() + Math.min(30, Math.floor(seconds)) * 1000);
      return true;
    } catch {
      return false;
    }
  };
}
