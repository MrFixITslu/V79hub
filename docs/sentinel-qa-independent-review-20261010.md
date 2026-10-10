# Sentinel independent review remediation — 2026-10-10 UTC

This supersedes the earlier candidate's development verification. Production
remains HOLD pending the operational maintenance gates; no cutover was executed.

## Findings and fixes

Independent review of 0c7f3477deceecb6a278d6ddd209f723be86dd97 found:
- P1: response close retired a write while its asynchronous handler could still
  be provisioning upstream or modifying a captured membership.
- P2: aggregate manifest-user count accepted a duplicated identity substituting
  for a missing different identity.

The revised fence retires a request only after its transport ends and all
invoked handler promises settle. Handler tracking is installed before all Hub
middleware/routes after the original fence middleware. Deferred dispatch after
transport completion is suppressed. Normal route skips, nested handler arrays,
settings, error handlers and next-then-rejection behavior are covered.
Current writable Hub routes register directly on app. A future mounted writable
Router must install tracking before registering its internal handlers.

Cleanup now requires exactly one persisted user row for each manifest ID.
Malformed snapshots fail both preview and deletion without mutation.

## Validation

- Full regression: 215 passed, zero failures or skips, disposable PostgreSQL
  17.11 and JSON, actual server.ts mandatory MFA/auth/session/lifecycle tests.
- Real Hub operator provisioning against a loopback-only synthetic POS stub:
  disconnect while awaiting upstream; QA creation stays blocked; provisioning
  saves the exact correct mapping; subsequent QA lifecycle preserves it.
- Real Express deferred provisioning and captured membership regressions prove
  no clone/replacement overlaps their execution, including disconnected clients.
- Early response with an async tail stays busy; aborted body parsing retires
  safely; callbacks cannot later restart dispatch; errors and route skips work.
- Actual Hub persisted duplicate+missing-user snapshots reject preview/deletion
  on both stores while preserving malformed input exactly.
- Independent working-tree re-review: 29 pure/HTTP tests passed, zero skips or
  failures; both material findings resolved, no new material blocker identified.
  Exact immutable commit sign-off must be recorded separately after commit.
- TypeScript lint, production build and git diff --check passed.
  Existing bundle-size build advisory remains.
- Final suite log: /tmp/v79-sentinel-review-final-20261010.log.

Temporary PostgreSQL package was SHA256-verified, unpacked without installation,
and used only for isolated socket-only databases. No customer backup or service
credentials entered the Acer fixtures.

## Production preservation and remaining gates

Read-only verification still shows revision 52, two users, two organizations,
and full state equality fingerprint 4c1ae50c49b7baa2f89695e41b54a6ed.
Live session-file SHA256 still matches the verified backup. Backup SHA256
manifest revalidated; Hub, database and business-agent remain healthy.
Source remains 1fae5211e187623b5a1e68eca1ac5aebb88f59e0.
Mandatory MFA remains configured; Sentinel create/cleanup remain disabled.

The live reminder leader remains enabled, so maintenance is not quiescent.
The previously prepared backup/restore/rollback plan remains available, but a
quiet cutover must revalidate drift, refresh capture if necessary, pin and verify
the candidate image, and replace only the Hub after all gates pass.
The standard whole-stack deployment helper must not be used.
No live QA organization, account mutation, external provisioning, flag change,
service restart, push, merge or deployment was performed by this work.
