# Hub reconciliation candidate — source protection and integration contract
Date: 11 November 2026
Status: **DRAFT / RELEASE HOLD / NOT PRODUCTION-READY**

## Scope and provenance

This branch is **preparation only**. It begins at `d0e46c0d85175eb21fdd85cd4a58dce00252fea0` (Hub PR #237 Sales Review), NOT at a proven byte-identical production commit. Do not merge, deploy, enable flags, re-label images, or close historical PRs based on this branch.

The user-observed production Hub Docker image is `sha256:5d11cfdb424e793441615038e2fa1de7c1143deb69a915d0c5d94f99edb0ab1d`. Its `org.opencontainers.image.revision` label points to `a7cfeb3141e103ee4ee7d88d14d32f50eac48b8c` (#230), but **the live `server.ts` SHA-256 differs** from GitHub #230, #237, #247 and `main`. Production `Login.tsx` also differs. The image label is provenance evidence, not proof of exact source content.

The observed SHA-256 inventory and the read-only validation tool are:
- `docs/reconciliation/hub-live-source-baseline-20261111.json`
- `node scripts/reconciliation/verify-live-file-digests.mjs`

The verifier is intentionally expected to fail against this seed branch. **Never update observed hashes merely to turn the test green.** Recover the actual source bytes from the approved running image, check them against the recorded digests, then prove every protected file matches.

## Preserve existing working production capabilities

Preserve byte/behaviour compatibility for:
1. Google login, existing user/tenant identity, MFA and the custom production login screen;
2. Website Admin Hub SSO including session introspection and revocation. Production Hub and Website SSO enforcement are enabled, and the owner reports the browser journey works;
3. App Help `/api/help`, owner MFA step-up, Skill Manager `/api/agent/skills`, Sales Review and approved navigation/dashboard;
4. customer data, payments, WiPay state, entitlement boundaries, current Hub/Tiquet/POS connections, app logos and favicon, and verified recovery procedures.

The matching production modules already include `server/website-sso.mjs`, `server/owner-mfa-step-up.mjs`, `server/customer-help-routes.mjs` and the newer `server/workforce-skill-*.mjs`. Do NOT replay older whole-branch snapshots that drop them.

## Integration A — canonical business-name change

**Preferred external request:** Marketing #38/#39 => Hub #247, signed `POST /api/platform/organizations/rename` with `organizationId`, `businessId`, `hubUserId`, `name`. Marketing currently signs with `V79_PLATFORM_SHARED_SECRET` and expects `result.organization.id` and `result.organization.name`; Hub #247 accepts this shape and verifies exact active mapping and workspace owner.

**Preserve unique earlier safeguards from #243:** Hub remains canonical, per-tenant concurrency control, retries to Tiquet and POS independently, durable retry/ack evidence and no misleading full-success result if one app is pending. Do not copy #243's conflicting inbound path or `V79_MARKETING_LAUNCH_SECRET` inbound contract without adapting the Marketing caller. Avoid reusing a broader platform key if a separately approved dedicated key can be introduced in a coordinated, backwards-compatible release.

**Downstream adapters:** Tiquet #60 signed `POST /api/platform/organization/name` plus #61/#62 UI-visible settings refresh; POS #18 signed tenant-name-only update. The Hub should adapt calls to those exact downstream contracts with explicit mapping, retry, idempotent acknowledgement and durable unsynchronised state. Confirm Tiquet service port and POS identity/entitlements from live configuration before staging. Do not change slugs, contacts, pricing, tickets, invoices, stock, roles or tenant ownership.

**Hard red-team tests:** wrong tenant mapping, non-owner, stale expected name, two concurrent renames, forced Hub DB failure, Hub succeeds/Marketing local DB fails, Tiquet timeout with POS success, POS timeout with Tiquet success, restarts before ack, Unicode normalisation, later application login resync. Do not mark cross-app propagation complete until both independent signed acknowledgements are proven.

## Integration B — Ecosystem V2

- Hub #251: signed, minimal event ingress and durable tenant-bound PostgreSQL receipts. Keep it **OFF** by default until source reconstruction and staging tests.
- Website #86: public lead belongs to Website CRM; **do not create a Tiquet ticket until staff explicitly convert the lead to a client**. Retry with the same event UUID; require real `clientId` and `jobId`.
- Tiquet #64: owns service customers/jobs, durable outbox, signed events; never treat a Hub event receipt as payment settlement or an invoice sent.
- POS #19: read-only *provisional* FIFO cost evidence, which depends on technician work in POS #17. Fix Hub #251's **wrong POS entitlement key `app-pos`; the catalogue uses `app-v79pos`**, and replace the current self-consistent-but-wrong source-string test with a behavioural entitlement test.
- Do not claim verified job margin until material/labour/currency mapping, signed Tiquet job association and POS reconciliation have passed.
- FFPRO automatic ticket-to-project planning/review and client-selective attachments/20% deposit are **separate follow-up workflow scope**, not completed by this V2 branch.
- Enforce tenant isolation, least privilege, PII-minimised payloads, idempotent retry and rollback across all connected apps.

The isolated three-app Hub/Website/Tiquet synthetic integration previously passed, but external mail, owner SSO, actual tenant mappings, POS/FFPRO, WiPay and restore were not accepted by that result. The R18 browser job for #251 failed at the Ubuntu package mirror installation, so browser acceptance remains incomplete.

## Release gates — all mandatory

1. Recover exact production source from the running image or validated immutable archive; prove protected SHA-256 inventory and build provenance. Maintain verified backup/restore point; do not expose secrets.
2. Produce an **additive**, isolated candidate patch. Document every file change and compare with all relevant existing PRs; preserve existing auth, help, skill and branding behaviour.
3. Execute nondeploying tests: typecheck/build/unit, auth/MFA/Google/login and Website SSO session/revocation, role/tenant enforcement, inbound signed name change and downstream retries, CRM approval/once-only Tiquet conversion, and cross-tenant event replay.
4. Test with real isolated staging databases and both successful and failure paths; demonstrate backup and rollback.
5. Owner reviews the precise diff, staging receipts, and behavioural checks. A passing test or GitHub mergeable status is NOT approval.
6. Only after **separate explicit user approval** may any merge or production cutover be considered.

## /REDTEAM disposition

- Mass-merging the 58 open Hub PRs risks replacing deployed, unmerged fixes. **Rejected.**
- Rebuilding from `main` or this #237 seed risks losing custom `server.ts` and `Login.tsx`. **Rejected.**
- Observe deployed source, prepare small compatibility-tested changes in an isolated branch, verify in staging, request explicit merge approval. **Chosen.**

All prior PRs, including 17 candidates for eventual retirement, remain open until unique safeguards and runtime provenance have been preserved.

**Current GitHub branch contains only this protective documentation, the observed manifest and a non-mutating digest checker. No integrations have been implemented or tested on this branch.**
