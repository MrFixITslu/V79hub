# V79 Ecosystem Architecture v2 — Red-team Phase 1 implementation

**Status:** isolated draft only. **Date:** 11 November 2026 (Saint Lucia).  
**Deployment:** explicitly prohibited at this stage. **This is a proposed safety boundary, not a connected integration.**

## Decision: three approaches considered

1. **Rebuild the platform as a single shared database:** rejected; high blast radius, tenant and recovery risk.
2. **Wire every app together immediately:** rejected; weak live evidence for payment, permissions and reconciliation.
3. **Preserve existing products and introduce verified, fail-closed contracts:** selected; low-risk additive work with staged testing.

## What already exists in inspected GitHub main branches

- Hub: `server/organization-access.mjs` checks memberships/entitlements. `server/organization-store.mjs` preserves legacy mapping rules. `server/workforce-actions.mjs` has an approval lifecycle and idempotency checks. `server/agent-approval-ledger.mjs` stores approval decision provenance with execution disabled in proposal inbox.
- Tiquet: `server/hubProvisioning.js` binds Tiquet account to Hub organisation, `server/hubManagedLink.js` rejects mismatched Hub organisation tokens, and `server/platformEvents.js` has an HMAC-signed outbox with retry. **Review finding:** outbound `organizationRef` falls back to the local `account_id` when `hub_organization_id` is null. Before wiring additional consumers, enforce a verified canonical mapping or explicitly quarantine unmapped events; the existing fallback is not proof of a cross-tenant exposure.
- POS: the Prisma schema contains inventory movement/reservation and payment entities; this does **not** establish integrated job-level stock costing or payment settlement.
- CI: `.github/workflows/deploy-ecosystem.yml` requires a manual dispatch; `v79-ci-cd.yml` handles pull request validation and has separately gated production release logic. Review all CI jobs before promotion.

These are **source observations** from GitHub main, not claims about the binary running on the live server.

## Additive, non-runtime implementation in this draft

- `server/ecosystem-v2-boundary.mjs`: pure functions that reject mismatched organisation/customer records, unmapped tenant events, raw PII in event summaries, wrong financial data owners, expired/unverified action approvals and premature ticket closure.
- `tests/ecosystem-v2-boundary.test.mjs`: local Node built-in tests with synthetic data and no database, network, provider account or secrets.

### Trust boundary (essential)

These functions do **not** verify a real transport signature, query the authoritative approval ledger, reconcile customer identity or perform payment settlement. The eventual callers must derive `trusted` values exclusively from verified server-side authentication, signed transport and durable organisation mappings. Never pass attacker-controlled request data into the trusted argument. Passing `transportVerified: true` as raw client input is a security defect.

The draft validator rejects nested event summaries to limit PII exposure until each named event has a reviewed schema. Do not wire it against existing event producers before inspecting actual emitted event types and payloads.

### Customer identity rule

- Hub issues organisation identifier; product account references stay in their respective product.
- Customer names or email alone are **not** canonical identity. No automatic merge on name or email.
- Explicit, auditable mapping per `(organisation, product, local account, customer reference)`, with conflict review and non-destructive migration.
- Duplicate and cross-tenant mapping require fail-closed/manual remediation, not silent overwrite.

### Financial ownership rule

- Tiquet owns service invoice and draft status; POS owns inventory cost snapshots and POS sales; WiPay is external payment provider evidence; FFPRO owns **budgets and forecasts only**.
- Use safe integer **minor units** and ISO 4217 currencies (`XCD`, `USD`, etc.). Never merge amounts in different currencies without a declared conversion basis.
- Payment provider event signature alone is not settlement: bind invoice, amount, currency, merchant, provider event ID, status and reconciliation before any paid-status transition.
- Project margin should show missing or stale data as **unknown**, never as zero profit/cost.

### Automation approval rule

- Approved scopes are fixed, time-bound, tenant-bound and digest-bound.
- Financial/legal/release actions require separate approver from executing actor; maintain an immutable audit and a kill switch.
- Unknown operations fail closed. Email recipients, legal terms, published campaign destinations and payment amounts remain gated to verified input.
- A paid invoice **cannot close a service ticket** without delivery and customer acceptance checks.

## Release gates before runtime wiring

| Gate | Evidence required | Current state |
| --- | --- | --- |
| G0: source baselines | Pin live source/image IDs, verify backups, immutable snapshot and rollback | **BLOCKED: gateway returns UNKNOWN for backup and release evidence** |
| G1: contract test | Synthetic 2-tenant fail-closed cases, signed-event tampering, approval expiry/replay | **Local isolated validator tests passed; no integrated signature test** |
| G2: identity mapping | Read-only reconcile Hub/Tiquet/POS customer IDs, document duplicates and ownership | **Not performed** |
| G3: finance | WiPay sandbox webhook tampering/duplicate/out-of-order, invoice matching, XCD/USD | **Not performed** |
| G4: browser acceptance | Owner and second tenant, customer entry → ticket → updates → invoice drafts | **Not performed** |
| G5: guarded release | Explicit owner approval, canary, health, data checks, rollback rehearsal | **Not approved** |

## Implementation order and ownership

**Now / independent work:** review this contract and synthetic tests; build read-only identity mapping and event inventory; avoid touching customer data.  
**Next / Tiquet & Hub:** reconcile website lead and Tiquet customer references with explicit approval; adopt named event schemas and durable idempotency/inbox where missing.  
**Next / POS & Finance:** validate stock issue to job and cost snapshots in staging; keep FFPRO forecast clearly separate.  
**Then / automation:** connect only narrowly approved actions to existing Hub ledger; human approval and audit by default.  
**Finally / rollout:** run staged browser acceptance and release only after separate owner deployment approval.

## Exact local smoke command

```bash
node --test tests/ecosystem-v2-boundary.test.mjs
```

The test passes demonstrate the *new pure validator's expected behaviour* only. They do not prove the live Hub, Tiquet, POS or payment provider is safe, connected or ready.

## Current evidence limitation

On 11 November 2026, the read-only V79 evidence gateway reported `UNKNOWN` for server backup, Hub/Tiquet release and Hub/Tiquet/security gate evidence. A previous operator report may establish a historical backup, but it does not replace a fresh attributable recovery checkpoint. **Do not deploy.**

## Explicit red-team stop conditions

Stop changes and do not deploy if **any** of: failed backups/restore point, missing canonical organisation mapping, mixed-tenant customer reference, unverifiable provider payment, approval bypass, stale/offline status incorrectly shown as live, uncontrolled invoice sends, incomplete audit evidence, or rollback not available.