# V79 Sentinel — Owner-only service grant integration on current Hub baseline

Date: 2026-10-10 AST. Scope: V79 Digital internal pilot ONLY. **Staging release candidate: NOT DEPLOYED.**

## Provenance and contents
- Base: actual owner-approved Hub release `c45d305b98d6080c07a5d2e35f7941a8ef15f4ce` (PR #118).
- Selected changes only: `e96f891` (signed Hub entitlement decision), `5eadecc` (revocable persistent machine grants), `4228216` (fresh owner-MFA-scoped grant issuance and revocation).
- Cherry-picking directly onto the current base exposed a `server.ts` conflict because the source branch also contained later, UNAPPROVED manual bank-transfer billing work. The conflict was resolved by taking ONLY the scoped Sentinel grant-admin handlers; no pending manual payment API or UI feature was copied from that branch. Keep manual payments tracked separately under PR #116, with WiPay unchanged.
- Preserved all current Hub features, owner/agent modules, manual release approval gates, real organizations and customers.

## Security assessment and bug corrected
- **Found:** grant-admin POST/revoke in original source invoked `commitSentinelStore`, which requires the exclusive QA mutation window. As regular owner-administrator routes, they would fail to persist even with a valid owner-MFA grant.
- **Fixed:** both paths now use the normal protected `commitStore`, which is blocked by the Sentinel write fence during exclusive QA and allowed during ordinary Hub operation.
- Added focused regression verifying both grant routes use the ordinary fenced persistence path and the QA-specific store save fails outside maintenance.
- Grant routes and signed entitlement decision are disabled unless their exact, independent feature flags are enabled. Operator grant issuance requires recent, verified owner MFA, exact owner/customer/account/client mapping, active Tiquet entitlement, a single permitted `ticket.create` action, bounded expiry and audit. Revocation must fail closed.
- No machine secrets, signing keys, guest MFA information or customer subscriptions have been provisioned/changed for this staging task.

## Evidence available for review
- Focused Hub grant tests: **11 passed, 0 failed, 0 skipped**.
- `npm run lint` passed. `npm run build` passed (bundle-size performance advisory only).
- `npm audit --omit=dev`: 0 known advisories.
- Full current-baseline Hub suite: **306 passed, 0 failed, 1 skipped** (dedicated independent-process PostgreSQL CI race test). That exact missing test **passed separately 1/1** using a fresh loopback-only PostgreSQL 17 instance with required fixed test identity, and the instance was stopped. Therefore **307 distinct checks passed across the two runs**; do not describe this as a single zero-skip run. Logs: `/tmp/v79-sentinel-hub-grants-full-20261010.log` and `/tmp/v79-sentinel-grants-exact-pg-test.log`.
- Isolated Tiquet staging `0b00ce6` suite **47 passed**, lint passed; Acer NOC isolated full suite **107 passed**; no live Tiquet dispatch. Read-only public Tiquet unsigned ingest HTTP 404.
- Live private Acer reviewer HTTPS certificate verified (curl TLS verification 0), root 404, unauthorized approver request 400. These responses do NOT mean machine-credential provisioning or signed-approver verification is complete.
- Hub live remains at `c45d305`, healthy, Sentinel QA flags off, reminder leader on; existing data intact from prior QA lifecycle.

## Remaining release gates
1. Rerun final CI on the exact pushed tree and document any reviewer findings; current local isolated full regressions and PostgreSQL race test passed.
2. Owner-controlled machine HMAC credential ceremony for Acer and Tiquet, with distinct key custody, 0600 file permissions, rotation/revocation; never paste secrets into chat, Git or logs.
3. End-to-end signed source event verification, current approver-role check, active Hub service entitlement grant, and exact Tiquet client mapping through private HTTPS.
4. Independent exact-commit security approval before CUSTOMER onboarding and any commercial exposure, per owner policy. Internal pilot reviewer waiver is not independent certification.
5. Controlled Tiquet migration/rollback and separate explicitly authorized ONE supervised internal test ticket; ticket dispatch remains OFF. No autonomous closure.
6. Confirm backup retention, drive resilience, recovery test, MFA secret protection, least-privilege Edge enroll/revoke and app-specific integrations before external release.

**Do not merge into production/deploy or activate a machine grant merely because tests pass.**
