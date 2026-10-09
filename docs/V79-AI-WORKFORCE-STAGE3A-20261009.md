# V79 AI Workforce — Stage 3A draft-proposal contract (development only)

This branch implements the **pure, fail-closed proposal data contract and tests only**.
It introduces **no HTTP endpoint, workflow activation, DB migration, persistent proposal
inbox, approval button, application write adapter, email sender or autonomous action**.

The owner/MFA context is a *trusted server-side prerequisite*, not a client payload.
Only owner-scoped non-executable **Tiquet reply drafts** and **Marketing campaign
drafts** are allowed. Strict parameter keys, bounded expiry (5 minutes to 24 hours),
size limits, idempotency-key shape, owner scope, and basic change-detection digest
are required. Returned reviewability **never implies execution permission**.

## Security boundary and known gaps

- The SHA-256 digest detects uncoordinated modifications; it is **not a signature**
  and does **not provide tamper-resistant audit logs**. An adversary with full store
  write access could recompute it.
- There is **no persisted deduplication or replay prevention** yet. The key format
  is validated here; atomic idempotency must be implemented and verified later.
- There is no executable approval state, signed owner decision, resource-state
  revalidation, or rollback adapter. MFA proof must come from the authenticated
  Hub session when server routes are eventually developed.
- Text previews have not been wired into per-product permission-checked APIs.
  Do not ingest customer PII in a production approval inbox until data review.
- This code is not loaded by production routes. It does not alter the Hub store.

## Remaining Stage 3 release gates

1. Introduce a durable, revision-safe Postgres proposal store with isolated
   organization/owner scope, unique idempotency constraints and retention limits.
2. Implement immutable, keyed audit event chain with provenance and rotateable
   keys (not just an unhashed local text log).
3. Add owner-only, MFA-verified Hub inbox with explicit before/after preview,
   approve/reject routes, CSRF protection, expiry and race/replay resistance.
4. Implement per-product **draft-only** adapters, server-side entitlement checks,
   source-object version check, transactional exactly-once processing, and
   reversal paths. No automatic send, publish or billing operations.
5. Exercise end-to-end malicious-input, replay, double-click, expiry, cross-tenant,
   conflict, failure, recovery and audit verification tests on disposable instances.
6. Run independent security review, scoped beta acceptance, image+DB rollback
   checks and explicit release approval **before merging to main/deploying**.

Tracked by V79 Hub issue #100. Do not enable or merge this branch automatically.
