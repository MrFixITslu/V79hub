# V79-01 — 14-day trial lifecycle (development branch)

**Status:** Development implementation and isolated automated tests. **NOT APPROVED FOR PRODUCTION.**

## Implemented

- Invite acceptance creates a 14 × 24-hour UTC trial with immutable start/end dates.
- Server-side app visibility, launch-ticket issuance, and launch-ticket consumption use subscription-aware access checks.
- Trial expires at its exact timestamp even when an expiry scheduler has not executed.
- Paused/cancelled and unverified paid plans fail closed even with stale enabled entitlements.
- Existing platform-owner organisation retains its separately identified internal access.
- Hub billing summary includes trial/paid-through timestamps and an effective access reason.
- Plan administration cannot restart a used trial or arbitrarily activate an unverified paid plan.
- Verified live WiPay subscription renewal sets a paid-through timestamp. Its next period is based only on an existing verified paid-through value, not an editable renewal label.
- Synthetic access-control tests and onboarding integration tests cover trial expiry, two tenant identities, invitation acceptance, and owner isolation.

## Mandatory blocks before production deployment

1. **Legacy plan migration:** The new access helper rejects existing non-owner plans without a recognised access policy. Review all historical organisation plans using a copied/sanitised database snapshot. Classify each explicitly: internal owner, eligible new trial, verified paid term, or restricted legacy-review. Do not auto-convert an old `active` state into proof of payment.
2. **Downstream session revocation:** POS, Tiquet, FFPRO and Marketing create separate application sessions after Hub launch. Provide bounded revalidation or signed entitlement invalidation so an expired subscription cannot continue using an already-open session beyond the approved revocation window.
3. **Trial reminders:** Notifications at agreed offsets require an idempotent delivery mechanism, opt-out policy and message testing. Do not send reminders from this branch.
4. **Manual banking:** Manual invoices and bank-statement verification are V79-02; not implemented here. No staff or AI assertion of bank payment should activate a paid plan.
5. **Staging database rehearsal:** Capture migration dry-run results, restore evidence, product-by-product isolation, and rollback compatibility before publishing a release candidate.
6. **Operational approval:** Do not merge or deploy this branch to main until the founder approves the production change and outstanding P0 conditions are met.

## Safe verification performed

```sh
npm ci --ignore-scripts --no-audit --no-fund
./node_modules/.bin/tsc --noEmit
npm test
npm run build
```

All validation ran in an isolated Git worktree at `/home/firelion/v79hub-trial-dev`; no running Hub container or production PostgreSQL row was modified.

## Expected API behaviour

`GET /api/billing/summary` returns current plan status, `accessStatus`, `trialStartedAt`, `trialEndsAt`, and `paidThroughAt`. All trusted dates are evaluated on the server in UTC; customer browsers cannot extend trial expiry.

## Release rollback

Preserve the versioned PostgreSQL state, all data/encryption secrets, current container image digest and running deployment revision. Reverting source alone may be insufficient if new subscription fields were persisted or customer payments occurred. Never blindly restore a database over newer legitimate transactions.

## Phase 2: session revalidation and migration review

Hub provides a signed, read-only POST /api/platform/entitlement/check endpoint.
Each product must derive user/org identities server-side and send an HMAC signed
request. Success is cached for at most 30 seconds and never beyond subscription
expiry. Failure and unavailable Hub mean deny, not access continuation.

Run a review-only migration preview against a staging JSON copy:

    node scripts/preview-trial-migration.mjs --snapshot <COPY> --owner-organization-id <OWNER>

This command does not connect to PostgreSQL, apply migration or expose customer
data. It prints aggregate counts only. Existing active legacy status is NOT
verified payment and must be reviewed before any production release.

POS has a separate opt-in development hook; FFPRO, Tiquet and Marketing still
need request-level adapters and automated negative tests before a full rollout.
Production integration flag remains disabled.
