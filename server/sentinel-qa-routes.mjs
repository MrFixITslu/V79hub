import crypto from "node:crypto";
import { previewSentinelCleanup, removeSentinelCleanup, SentinelCleanupError } from "./sentinel-qa-cleanup.mjs";
import { stageSentinelQaCreation } from "./sentinel-qa-create.mjs";

/**
 * Registers the exact same Sentinel QA routes on the Hub and the disposable
 * loopback-only integration test. The main Hub supplies its actual auth,
 * same-origin verifier, durable commit method, and session invalidator.
 *
 * Feature gates are OFF unless environment variables equal "1".
 */
export function registerSentinelQaRoutes(app, {
  requirePlatformOperator, sameOriginMutation, getStore, commitStore,
  hashPassword, deleteSessionsWhere,
}) {
  if (!app || typeof requirePlatformOperator !== "function" ||
    typeof sameOriginMutation !== "function" || typeof getStore !== "function" ||
    typeof commitStore !== "function" || typeof hashPassword !== "function" ||
    typeof deleteSessionsWhere !== "function") {
    throw Error("Sentinel QA routes missing required Hub safety dependencies");
  }

  const allowed = (key) => process.env[key] === "1";
  const fail = (res, error, generic) => {
    if (error instanceof SentinelCleanupError) {
      return res.status(409).json({ error: error.message });
    }
    // Internal store errors are not disclosed to the HTTP caller.
    console.error("[Sentinel QA] " + generic);
    return res.status(503).json({ error: generic });
  };
  let mutationInProgress = false;
  const busy = (res) => res.status(409).json({ error: "Sentinel QA mutation already in progress" });

  app.post("/api/admin/sentinel-qa/organizations", requirePlatformOperator, async (req, res) => {
    if (!allowed("V79_SENTINEL_QA_CREATE_ENABLED") ||
        !allowed("V79_SENTINEL_QA_CLEANUP_ENABLED")) {
      return res.status(404).json({ error: "Sentinel test tenant creation is disabled" });
    }
    if (!sameOriginMutation(req)) return res.status(403).json({ error: "Invalid request origin" });
    if (req.body?.confirm !== "CREATE ISOLATED SENTINEL QA" ||
        req.body?.appIds !== undefined || req.body?.email !== undefined ||
        req.body?.userIds !== undefined) {
      return res.status(400).json({ error: "Exact isolated test-tenant confirmation is required; apps and external users are not allowed" });
    }
    if (mutationInProgress) return busy(res);
    mutationInProgress = true;
    const operatorUserId = req.user.userId;
    try {
      const roles = ["owner", "staff", "viewer"];
      const temporaryAccounts = roles.map(role => ({
        id: crypto.randomUUID(), role, password: crypto.randomBytes(24).toString("base64url"),
      }));
      const { nextStore, organization, syntheticUsers, cleanupPreviewHash } =
        stageSentinelQaCreation(getStore(), {
          operatorUserId,
          syntheticAccounts: temporaryAccounts.map(a => ({
            id: a.id, role: a.role, passwordHash: hashPassword(a.password),
          })),
        });
      await commitStore(nextStore);
      res.setHeader("Cache-Control", "no-store");
      return res.status(201).json({
        organization, cleanupPreviewHash,
        testAccounts: syntheticUsers.map(a => ({
          ...a, oneTimePassword: temporaryAccounts.find(p => p.id === a.userId).password,
        })),
        warning: "Store these one-time test credentials securely; do not email or share them. Only Hub-local accounts are created.",
      });
    } catch (error) {
      return fail(res, error, "Test tenant creation unavailable");
    } finally {
      mutationInProgress = false;
    }
  });

  app.get("/api/admin/sentinel-qa/organizations/:organizationId/cleanup-preview",
    requirePlatformOperator, (req, res) => {
      if (!allowed("V79_SENTINEL_QA_CLEANUP_ENABLED")) {
        return res.status(404).json({ error: "Sentinel cleanup is disabled" });
      }
      try {
        const preview = previewSentinelCleanup(getStore(), {
          organizationId: String(req.params.organizationId || ""),
          operatorUserId: req.user.userId,
        });
        res.setHeader("Cache-Control", "no-store");
        return res.json(preview);
      } catch (error) {
        return fail(res, error, "Sentinel cleanup preview unavailable");
      }
    });

  app.post("/api/admin/sentinel-qa/organizations/:organizationId/cleanup",
    requirePlatformOperator, async (req, res) => {
      if (!allowed("V79_SENTINEL_QA_CLEANUP_ENABLED")) {
        return res.status(404).json({ error: "Sentinel cleanup is disabled" });
      }
      if (!sameOriginMutation(req)) return res.status(403).json({ error: "Invalid request origin" });
      if (mutationInProgress) return busy(res);
      mutationInProgress = true;
      try {
        const { nextStore, removed } = removeSentinelCleanup(getStore(), {
          organizationId: String(req.params.organizationId || ""),
          operatorUserId: req.user.userId,
          confirmName: req.body?.confirmName, previewHash: req.body?.previewHash,
          auditId: crypto.randomUUID(), deletedAt: new Date().toISOString(),
        });
        await commitStore(nextStore);
        const removedUserIds = new Set(removed.userIds);
        deleteSessionsWhere(session =>
          session.organizationId === removed.organizationId ||
          removedUserIds.has(session.userId));
        res.setHeader("Cache-Control", "no-store");
        return res.json({
          success: true, organizationId: removed.organizationId,
          syntheticUsersDeleted: removed.memberCount, auditId: removed.auditId,
        });
      } catch (error) {
        return fail(res, error, "Sentinel cleanup unavailable; inspect operator logs");
      } finally {
        mutationInProgress = false;
      }
    });
}
