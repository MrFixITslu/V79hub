# Sentinel Hub-only maintenance plan — 2026-10-09

Status: prepared for review; not executed. The integrated candidate is on
feat/sentinel-runtime-fab2f1a-20261009 in hub-runtime-integration on the Acer.
See sentinel-runtime-integration-20261010.md for the intentional newer baseline,
current verification and protected deployed operational files. Earlier image and
rollback identities below are historical; do not apply them to the newer runtime.
Preserve all existing accounts, organizations, memberships, application data,
secrets and sessions.

## Gates before any cutover

1. Obtain a separate independent security review of the exact candidate commit.
   Review operator identity/MFA enforcement, creation marker and manifest trust,
   preserved-schema reference scan, exact-target deletion, session invalidation,
   audit retention, write fencing and background-worker refusal.
2. Require zero unresolved material findings; confirm the entire integrated-base
   suite passed with no skips and lint/build/patch checks passed. The historical
   05942fa suite contained 215 tests; use the current integration receipt.
3. Confirm the existing source/image match the recorded baseline or reassess any
   drift. Do not overwrite new work or use an unrelated deployment checkout.
4. Confirm a quiet maintenance window. Temporarily stop the trial-reminder
   leader and drain state-changing requests, including GET/HEAD provisioning
   launches, payment returns and catalogue initialization.
5. Capture and verify a new pre-cutover backup after quiescing writes. The
   prepared snapshot and restore drill prove rollback preparation but must be
   refreshed if persisted state, sessions or configuration change.
6. Validate a version-pinned candidate Hub image independently before replacing
   the live Hub. Maintain original secrets, DATA_DIR mount, PostgreSQL volume,
   APP_URL, mandatory MFA and reverse-proxy network configuration.
7. Keep both Sentinel flags disabled for the initial candidate replacement.

## Narrow replacement

Do not use scripts/deploy-server.sh for this change: it builds/recreates the
whole Hub/agent/PostgreSQL stack and includes collision-removal behavior.

Use a reviewed override with the exact candidate Hub image, and recreate only
the v79-hub service with no dependencies and no builds/pulls at cutover.
Do not recreate the database or business-agent containers. Do not run
migration, account-recovery, password-reset, volume-delete or prune commands.

Compare preserved state fingerprints, account/org counts and persisted session
membership before and after replacement. Check Hub readiness and public
availability. Existing owner login, MFA, session/refresh and app access must
remain intact.

## Controlled Hub-local lifecycle

Only after all preceding gates pass, enable the two Sentinel flags briefly in
the maintenance configuration and keep the reminder leader disabled.

Use the genuine platform operator's authenticated MFA-protected session.
Create exactly one organization and the three generated synthetic accounts
using the reviewed endpoint. Avoid printing, emailing or retaining plaintext
credentials in logs, history or reports.

Perform only Hub authentication/read checks. Do not activate billing, plans,
invitations, account recovery, custom apps or external product provisioning.
Preview the exact organization; verify its trusted marker, manifest and absence
of references. Delete using its exact name and the current preview hash.

Verify organization/users/memberships absent, synthetic cookies and credentials
rejected, and existing accounts/data preserved. Any unexpected reference or
failed cleanup stops the maintenance process for review; no generic deletion,
manual datastore surgery or bypass is permitted.

Disable both flags, return the Hub to its ordinary reviewed configuration,
resume the reminder leader only after cleanup and verification, and validate
health/availability and data again.

## Rollback

Prepared rollback image:
v79-hub:sentinel-pre-auth-20261009
sha256:61ecdd6dd7d00201feba89daf3242398e14253f240c12cbea9819b89f259fd37

Prepared verified snapshot:
 /home/firelion/v79-backups/pre-sentinel-auth-20261009-pbM3Do

Roll back only the Hub image/configuration while preserving the running
PostgreSQL container, volume and latest data. This candidate makes no schema
migration. Never automatically restore an older database over new user activity.
If a database restore is ever needed, stop for explicit recovery authorization.

Do not roll back while leaving a synthetic organization unresolved. Complete
supported exact-target cleanup or retain the guarded candidate with flags
restricted and escalate the observed issue.
