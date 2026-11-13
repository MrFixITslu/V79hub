import { createHash } from "node:crypto";

const PATH = "/api/platform/organization/rename";

const validId = value =>
  typeof value === "string" &&
  value.length >= 1 &&
  value.length <= 180 &&
  !/[\x00-\x1f\x7f]/.test(value);

const validName = value =>
  typeof value === "string" &&
  value.length >= 1 &&
  value.length <= 120 &&
  value === value.trim() &&
  !/[\x00-\x1f\x7f]/.test(value);

export function createMarketingRenameHandler({ verify, secret, rename }) {
  return async (req, res) => {
    res.setHeader("Cache-Control", "no-store");

    const key = secret();
    const rawBody = req.rawBody?.toString("utf8") || "";

    if (
      req.get("x-v79-service-id") !== "v79-marketing" ||
      !key ||
      !verify({
        method: "POST",
        pathname: PATH,
        body: rawBody,
        timestamp: req.get("x-v79-timestamp") || "",
        signature: req.get("x-v79-signature") || "",
        secret: key,
      })
    ) {
      return res.status(401).json({ error: "Invalid service signature" });
    }

    const b = req.body;
    if (!b || typeof b !== "object" || Array.isArray(b)) {
      return res.status(400).json({ error: "Invalid rename request" });
    }

    const {
      organizationId, hubOwnerUserId, marketingBusinessId,
      marketingUserId, expectedName, name, eventId, occurredAt,
    } = b;

    if (
      ![organizationId, hubOwnerUserId, marketingBusinessId,
        marketingUserId, eventId].every(validId) ||
      !validName(name) ||
      !validName(expectedName) ||
      name === expectedName ||
      typeof occurredAt !== "string" ||
      !/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,3})?Z$/.test(occurredAt) ||
      !Number.isFinite(Date.parse(occurredAt))
    ) {
      return res.status(400).json({ error: "Invalid rename fields" });
    }

    // Stable across retries, independent of the HMAC request timestamp.
    const auditId = createHash("sha256")
      .update(`marketing-rename:${eventId}`)
      .digest("hex");

    const input = {
      organizationId,
      name,
      eventId,
      destinations: ["tiquet", "pos"],
      marketingAuthorization: {
        hubOwnerUserId,
        marketingBusinessId,
        marketingUserId,
        expectedName,
      },
      auditEvent: {
        id: `marketing-rename-${auditId}`,
        organizationId,
        actorUserId: hubOwnerUserId,
        type: "organization.name.changed",
        createdAt: new Date(occurredAt).toISOString(),
        details: {
          source: "v79-marketing",
          eventId,
          previousName: expectedName,
          newName: name,
          marketingBusinessId,
          marketingUserId,
        },
      },
    };

    try {
      const result = await rename(input);
      return res.status(result.duplicate ? 200 : 202).json({
        accepted: true,
        applied: result.applied,
        duplicate: result.duplicate,
        organizationId,
        name,
        revision: result.revision,
        destinations: ["tiquet", "pos"],
        deliveryConfirmed: false,
      });
    } catch (error) {
      if (error?.name === "MarketingRenameAccessError") {
        return res.status(error.code === "conflict" ? 409 : 403)
          .json({ error: "Rename authorisation failed" });
      }
      if (/event ID was reused with different data/i.test(error?.message || "")) {
        return res.status(409).json({ error: "Rename event conflict" });
      }
      console.error("Marketing organisation rename failed:", error);
      return res.status(503).json({ error: "Organisation rename unavailable" });
    }
  };
}
