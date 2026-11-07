/**
 * Bounded in-session TOTP re-verification for an already MFA-authenticated owner.
 * Never creates a login session, changes permissions or authorises an action.
 */
export function createOwnerMfaStepUp({
  ownerContext, sameOrigin, getSecret, verifyCode, persistSession,
  now = Date.now, maxAttempts = 5, windowMs = 15 * 60_000, freshMs = 5 * 60_000,
}) {
  const attempts = new Map();
  return (req, res) => {
    res.setHeader("Cache-Control", "no-store");
    const context = ownerContext(req);
    if (!context || req.user?.mfaVerified !== true) {
      return res.status(403).json({ code: "MFA_SESSION_REQUIRED", error: "Sign in to your owner account with MFA." });
    }
    if (!sameOrigin(req)) {
      return res.status(403).json({ code: "INVALID_ORIGIN", error: "Open this page directly in V79 Hub and retry." });
    }
    const code = req.body?.code;
    if (typeof code !== "string" || !/^\d{6}$/.test(code) ||
        Object.keys(req.body).length !== 1) {
      return res.status(400).json({ code: "INVALID_MFA_CODE", error: "Enter the six-digit authenticator code." });
    }
    const userId = String(req.user.userId);
    const at = now();
    if (attempts.size > 100) {
      for (const [key, entry] of attempts) if (entry.until <= at) attempts.delete(key);
    }
    const prior = attempts.get(userId);
    const recent = prior && prior.until > at ? prior : { count: 0, until: at + windowMs };
    if (recent.count >= maxAttempts) {
      return res.status(429).json({ code: "MFA_RATE_LIMITED", error: "Too many attempts. Try again in 15 minutes." });
    }
    let secret;
    try {
      secret = getSecret(userId);
    } catch {
      return res.status(503).json({ code: "MFA_UNAVAILABLE", error: "Secure verification is temporarily unavailable." });
    }
    if (!secret) {
      return res.status(403).json({ code: "MFA_SESSION_REQUIRED", error: "Owner MFA enrolment is required." });
    }
    if (!verifyCode(secret, code, at)) {
      recent.count++;
      attempts.set(userId, recent);
      return res.status(401).json({ code: "INVALID_MFA_CODE", error: "Invalid code. Check your authenticator clock." });
    }
    const before = req.user.mfaVerifiedAt;
    req.user.mfaVerifiedAt = at;
    try {
      persistSession();
    } catch {
      req.user.mfaVerifiedAt = before;
      return res.status(503).json({ code: "MFA_UNAVAILABLE", error: "Verification could not be saved. Retry safely." });
    }
    attempts.delete(userId);
    return res.json({ verified: true, validUntil: new Date(at + freshMs).toISOString() });
  };
}
