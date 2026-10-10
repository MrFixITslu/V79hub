# Sentinel supervised browser controls — 2026-10-10 UTC

Status: STAGED AND TESTED. No deployment or live synthetic-resource mutation was performed.

## Scope

Base: reviewed/deployed Hub candidate 1ebe3357983c6f75bfd95ffa76beeee20f12984d.
Checkout: /home/firelion/V79-Sentinel/hub-runtime-integration on the Acer.

Added a Sentinel supervised testing panel under Platform Admin → Audit & Security.
It uses the existing authenticated administrator session, displays release/maintenance
status, creates exactly one Hub-local test organization, obtains an exact cleanup
preview, requires the full deletion phrase, and verifies the retained deletion audit
and absence of test organization/users/memberships afterward.

The panel cannot change flags, pause workers, provision external applications,
change billing, invite real users, reset credentials, or delete customer organizations.
It never renders, stores, logs or downloads generated test passwords.
Creation/cleanup have no automatic retry; uncertain outcomes require a read-only
status reconciliation. A reload can discover the exact trusted test organization.

Added GET /api/admin/sentinel-qa/status behind the existing actual platform-operator
authorization. It returns redacted test-resource metadata, counts, flags, maintenance
readiness and the latest same-operator deletion receipt. Status does not write data.
Untrusted/contaminated test-labelled organizations appear blocked; naming a customer
like a test target never grants cleanup eligibility. Existing mutation routes,
feature flags, write fence, reminder-worker refusal and reference checks are unchanged.

## Verification

- Complete existing Hub suite plus status/auth regressions: 256 passed,
  zero failures, zero skips. Actual JSON and disposable PostgreSQL 17.11 Hub runs.
- Additional browser orchestration tests: 7 passed, zero failures/skips.
  Exact-target reconciliation, password non-return, missing resources, wrong audit,
  contaminated preview, orphan users/memberships and lost-response/no-retry behavior.
- Total automated checks: 263 passed; no skipped release checks.
- TypeScript lint, production build and git diff --check pass.
- Existing bundle-size advisory remains.
- No dependency, schema or migration change.

PostgreSQL 17.11 packages were fetched from the official PostgreSQL APT repository.
InRelease signature, compressed package-index SHA256, package sizes/index and
individual package SHA256 checks were verified. Packages were unpacked beneath
a private temporary directory without system installation or service changes.
The independent-process approval test used a fresh loopback-only CI database
named v79_ci_approval; complete Hub tests used private socket-only generated databases.
All generated datastore/process fixtures were removed by teardown.
The unpacked runtime is retained temporarily for the release reviewer to reproduce
tests; it holds no customer data.

Logs:
- /tmp/v79-sentinel-browser-suite-20261010.log
- /tmp/v79-sentinel-browser-lint-final-20261010.log
- /tmp/v79-sentinel-browser-build-final-20261010.log

## Live preservation

Read-only checks: 2 existing users and 2 existing organizations.
No Sentinel QA organizations or synthetic identities present.
Comparison to the verified cutover backup at revision 52 found only the expected
administrator lastLogin update; current revision 54. All other persisted state
matches exactly, including memberships, organizations, billing, app mappings,
agent proposals and their audit chain.
Both Sentinel flags remain disabled; reminder leader remains enabled.
The genuine MFA-protected browser administrator session remains authenticated.
No existing account/session was reset or deleted.

## Remaining gate

The maintenance plan requires: "Obtain a separate independent security review
of the exact candidate commit." Existing independent approval covers 1ebe335,
not these new browser/status controls. A fresh review is required before deploying
this candidate, enabling the brief supervised maintenance configuration, or
creating live test resources. Current delegation instructions require explicit
user authorization before using a reviewer agent.

After review passes, preserve the live environment/overrides and data; pin and
validate a Hub-only image; refresh/verify the quiet-window snapshot; pause the
reminder leader; enable only the reviewed Hub-local flags; use the authenticated
operator browser for one create → preview → exact delete; verify state/session
cleanup and preservation; disable flags and restore the reminder configuration.
Any unexpected reference or uncertain cleanup stops for operator review.

## Session-scoped MFA hardening — 2026-10-10 UTC

A further disposable full-Hub adversarial check demonstrated that a previously
persisted `mfaVerified: false` platform-owner session could call Sentinel status,
creation and cleanup routes after the user account itself had MFA enrolled.
No live account, datastore or session was used in that reproducer.

`requirePlatformOperator` now refuses a platform-owner session unless this
specific session has `mfaVerified: true` and the underlying owner account has
MFA enabled whenever `V79_REQUIRE_ADMIN_MFA=1`. It does not revoke, rotate or
alter ordinary Hub user sessions. The isolated regression seeds a historical
non-MFA owner session after genuine MFA setup, checks all Sentinel routes deny
it, logs it out, and confirms the properly MFA-verified session still works.

After hardening, the complete Hub suite passed 263/263 checks (0 failures,
0 skips), including disposable JSON and PostgreSQL 17.11 backends; lint,
production build and whitespace check also passed. Test output:
`/tmp/v79-sentinel-mfa-hardening-suite-20261010.log`,
`/tmp/v79-sentinel-mfa-hardening-lint-20261010.log`,
`/tmp/v79-sentinel-mfa-hardening-build-20261010.log`.

Final read-only live check: deployed image remains `v79-hub:sentinel-1ebe335`,
revision 54; 2 existing users, 2 existing organizations, zero Sentinel QA
organizations and zero synthetic users. Both QA mutation flags are OFF;
normal trial reminder leadership remains enabled. This follow-up code is
staging-only; live supervised create/delete remains HOLD until an independent
security review signs off on the exact new candidate and the maintenance
release checks pass. Do not infer release approval from a successful test run.
