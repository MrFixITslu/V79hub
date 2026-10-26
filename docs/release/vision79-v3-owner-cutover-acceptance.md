# Vision79 v3 — owner acceptance and rollback release gate

Prepared 26 October 2026. **Status: pending, NOT approved for production cutover.**
Approved visual source: `114841271d4f8b9c4b63df6aedfd55bde2e82f40`.
Approved candidate image: `sha256:960849ef917ac542674b07ccff5fa64a2c68cd0b452346f5c9fb72d1765d97d6`.
Prior live Hub image: `sha256:d2e6f4aee332b076f1340c339e4277b39f1337d2cd02b4b3a4c849e3a6d615e4`.

## Hard release prerequisites — all must be PASS

- Current five-service image and health fingerprint has been rechecked *immediately* before release, matching approved baseline. No uncontrolled concurrent Docker/Compose mutations.
- Exact existing Hub `Config`, `HostConfig.Binds`, `HostConfig.Mounts`, writable mount paths, network attachments, restart/security policies, labels, environment, healthcheck and rollback identity are privately captured. Only the Hub image may change in the sealed release transaction; not the database/Tiquet/worker images, mounts, secrets or user data.
- Operator has verified an **up-to-date** encrypted off-host checkpoint, a tested rollback transaction for the actual current image/runtime settings, and a deterministic automatic health-failure rollback **before** switching. Earlier cold-boot rehearsal establishes image viability only, not an actual production rollback transaction.
- Workforce timers and live action side effects are explicitly accounted for. No worker, database schema migration, cache flush or restoration may run as part of a visual release.
- Owner can complete the interactive acceptance checks below immediately after switching. The release command/transaction must preserve an emergency rollback trigger if the owner cannot sign in. Do not require owner credentials or MFA secrets in scripts, chat, logs or evidence.
- Rollback is never silently skipped if cutover or acceptance fails. The old Hub image must remain cached and available until full acceptance.

## Owner acceptance, only inside a monitored reversible release

1. **Live runtime health:** exact Hub `/api/health` response is healthy; Tiquet and both Postgres services remain healthy. No emergency migration or reinitialization is observed.
2. **MFA:** open a *fresh private browser session* to `https://hub.v79sl.com`, use the established owner account and complete the real MFA challenge. Verify unauthorized/absent MFA does **not** grant access. Never copy OTP, recovery codes or passwords into terminal or chat.
3. **Session:** reload Owner Assistant and Platform Admin to confirm continued authenticated access; sign out in a *separate test session* and confirm protected pages reject that session. Test expiry according to the existing policy, without shortening a production timeout.
4. **Tiquet SSO:** from signed-in Hub, click Tiquet. Confirm Tiquet opens its authorized dashboard directly without a second login; account/tenant must be correct. Direct anonymous entry must still deny access.
5. **Visual acceptance:** Owner Assistant opens **Today** first with clear Tasks & approvals and Delivery board; Platform Admin shows Overview, Customers, Applications, Plans & entitlements, Audit & security. Review desktop and mobile or narrow window, dark and light states. Confirm approved Vision79 design, readable text and no old black empty workspace.
6. **Data/permission safety:** missing numbers show an unknown marker, not fabricated zero or a misleading green health badge; failed refresh marks stale data. Confirm admin and owner information is visible only to permitted accounts. No automated messages, approvals, purchases or provisioning should be triggered by page navigation.
7. **Baseline preservation:** existing organizations/users/plans, actual subscriptions, Tiquet tickets and dashboards remain present and unchanged. Confirm no repeat MFA enrollment or new first-run onboarding.
8. **Rollback window:** retain the old image and exact rollback receipt; release must not close until observed private MFA, SSO, design and health all pass.

## Mandatory ROLLBACK triggers

- Hub unhealthy, restart loop, unexpected published port, lost or changed mounted customer data or Compose config, wrong network, inaccessible old-image rollback, or any database/worker impact.
- Owner cannot pass MFA, authorized routes become accessible without MFA, unexpected MFA enrollment or owner-session loss.
- Hub-to-Tiquet launch requires a second login or resolves to wrong account/tenant.
- Approved v3 Owner Assistant/Admin visual design is absent, old UI still shown after verified cache refresh, or sensitive statistics are misrepresented.
- Any uncontrolled writes/migrations or release plan drift.

On a rollback trigger: stop release acceptance, execute **the exact rollback from the sealed live transaction** and verify five service identities/health and genuine owner login. Do **not** guess a manual `docker run` or `docker compose up` command from old receipts. Escalate if sealed rollback fails; preserve logs and private evidence without exposing secrets.

## Current decision

All live/isolated recovery, static metadata and image-only cache stages have passed. **Production still serves the prior Hub image.** New candidate runtime parity, interactive owner MFA/SSO, authenticated design and the reversible production cutover are **not** yet verified. `GO=NO` until the guarded release transaction exists, prerequisites pass and acceptance is performed.
