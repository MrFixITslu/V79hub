# V79-01 Hub release candidate — integration gate

**State: DRAFT, not deployed. No commercial customer launch.**

## Why this is a single release candidate

The three Hub PR branches have overlapping changes and `main` triggers Docker image publishing and a production Hub deployment. Combining them in one isolated release candidate ensures one controlled deployment after review instead of three.

Source components merged into this candidate, in order:

1. Academy canonical URL and Docker secret exclusions (Hub PR #94).
2. Scoped 7-day HSTS and conservative CSP (Hub PR #95).
3. V79-01 integration staging / full acceptance and release documentation (Hub PR #93).

The Marketing provisioning contract fix lives separately in Marketing draft PR #24; its narrow Compose change is already live and tested, but its repository merge and deployment remain gated.

## Validation performed before creating this candidate

- Clean merge of all three Hub branches in an isolated worktree. No conflicts.
- TypeScript lint passed; **145 of 145 Node tests passed**; frontend production build passed.
- `scripts/release-config-audit.mjs` reported `ready: true` and zero issues.
- Five-app disposable staging passed on the source V79-01 branch (GitHub run **37866361771**).
- Hub CI passed on the same source branch (GitHub run **37866361790**).
- Live production: all six HTTPS sites HTTP 200, all six HTTP origins 301 to HTTPS; applications checked healthy. Founder confirmed the six Hub application launches work.
- Comparing this candidate to `/opt/v79/hub`, the current `docker-compose.yml`, `.dockerignore`, Academy app launcher components are identical; `server.ts` differs only by the four new security-header lines.

## Pre-merge / pre-deploy gates

1. Inspect GitHub CI for **this exact candidate SHA** and verify publishing/deployment jobs stay skipped until a `main` push is specifically approved.
2. Review the header policy in authenticated Hub with MFA, Academy launch and all managed app launchers in an isolated candidate environment, or validate safely in a staged roll-forward/roll-back window. Current PR work has not changed live Hub headers.
3. Confirm a production snapshot, current safe local rollback image (`v79-hub:academy-safe-rollback-20261008`), working database and rollback steps. The previous unused rollback image that contained `.env` was deleted after checking it was not in use.
4. Revalidate installed app secrets, live `.env` protected file, production/source parity and unchanged Nginx Proxy Manager Force SSL rules. Never copy or print credential values.
5. Review changes in the Marketing source repository separately and avoid replacing its large unrelated local working-tree modifications.
6. **Explicitly authorise** the one candidate PR merge and its auto-deployment after the final gated checks. Do not enable billing, customer invitation campaigns or extra beta trials as part of this merge.
7. After deployment: verify 200 and 301 responses, Hub HSTS/CSP, MFA login, all six app launches, session restrictions, beta org entitlement/expiry, email configuration, runtime and error logs. Roll back the Hub image if acceptance fails.

## Security and operational follow-ups

- Old local Hub secret-bearing Docker image deleted; replacement image lacks embedded `/app/.env`. Historical release backups and live secret rotation require a separate controlled inventory and approvals.
- Daily local backup remains enabled; a previous retention warning referred to a snapshot that is no longer on disk. Confirm following scheduled backup has no new retention warning. Offsite encrypted backup remains intentionally deferred.
- Resend DKIM / sending DNS records verified and earlier test mail delivered, but optional custom email-link tracking DNS is still not fully verified. Avoid hijacking `hub.v79sl.com` for tracking.

**Release verdict:** code integrated and local tests pass; production candidate merge/deploy is **NOT YET APPROVED**.
