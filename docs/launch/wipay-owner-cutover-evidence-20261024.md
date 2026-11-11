# Vision79 WiPay / Academy — operator evidence and release gates
**Prepared:** 2026-10-24 · **Disposition:** REVIEW ONLY — NO GO for live payment or production deployment

## Immutable source pairing
| Component | Reviewed source | Status |
|---|---|---|
| Hub | `MrFixITslu/V79hub` [draft PR #196](https://github.com/MrFixITslu/V79hub/pull/196), commit `8a9b452e50cf6212e23c5751c3ca2457dbff392d` | Synthetic CI only, not merged/deployed |
| Academy | `MrFixITslu/V79acaedmy` [draft PR #32](https://github.com/MrFixITslu/V79acaedmy/pull/32), commit `c748e3ecc3dfe94d8a15fe0a6015870aac498132` | Combined pricing + billing security + payer email, not merged/deployed |
| Historic Hub baseline | `9528f27422525ed6340c6a42e0152aa62f433fd8`, accepted `server.ts` blob `6784def9a38d018f87aa85e0d73ec10d65972daf` | Preserve. Do not rewrite original R18 release test |

This source pairing is **not a container image digest** and does not prove the installed Dell release or rollback. Recheck source SHAs before any future approval if either branch changes.

## Verified isolated evidence (does not prove production safety)
- [Disposable five-app Docker acceptance](https://github.com/MrFixITslu/V79hub/actions/runs/40116142515): all builds, five health endpoints, all four tenant-provisioning paths, four signed entitlement negative/positive contracts PASS.
- [WiPay/PostgreSQL race and rollback tests](https://github.com/MrFixITslu/V79hub/actions/runs/40116142434): PASS, including cross-process duplicate/replay/crash handling.
- [Hub–Academy real localhost HTTP with synthetic provider callback](https://github.com/MrFixITslu/V79hub/actions/runs/40116142505): PASS; **not actual WiPay sandbox**.
- [Candidate source attestation and broad synthetic regression](https://github.com/MrFixITslu/V79hub/actions/runs/40116142586): PASS; historical R18 immutability remains separately checked.
- Full production-coupled Hub pipeline is **not green** because `server.ts` differs from the immutable historical R18 candidate; release approval, publish and deployment jobs were skipped. Do not turn that check off or edit the historical pinned hash.

## Read-only Dell evidence, when explicitly authorized by the owner
From a trusted checkout of the reviewed Hub candidate, run **locally on the authorized host** (or on an authorized machine with a *locally configured* Docker context):
```bash
node scripts/wipay-runtime-parity-readonly.mjs --help
node scripts/wipay-runtime-parity-readonly.mjs --hub v79-hub --academy academy
```
The container names above are examples; use the **actual** local container names once observed. The script calls only `docker inspect --type container NAME`; it does not invoke SSH, `docker exec`, a database query, backups, payments, network requests or any state-changing Docker command. It reports only immutable image identity if present, OCI Git label if present, running/health state and booleans for secret/configuration presence. It never prints environment values, mounted directory names, merchant IDs, callback URLs or database credentials. The script's output is *not* permission to activate WiPay.

Expected operator signoff requires, separately:
1. Exact **running Hub + Academy OCI image digests** and source/provenance. An absent image digest or revision label means **unverified**, not automatically a match.
2. Confirm Hub backend is **PostgreSQL** with correct completed data migration and no unexplained revision conflict. A `DATABASE_URL`-present flag is **not** a schema/integrity test. Use independent approved backup/restore evidence from the relevant release.
3. Document a fixed, tested **rollback contract**, covering application image, configuration, database schema compatibility, provider callback in-flight handling, scheduled worker quiescence and customer entitlement reversals. **Do not roll back to a stale database snapshot after live charges**; financial ledgers need reconciliation.
4. Recheck Hub login/MFA/SSO, Academy learner isolation and no-double-login flow using *synthetic* identities on an isolated host. Do not export real customer data.
5. WiPay Saint Lucia **verified business merchant** agreement: exact live AND sandbox Payments API checkout URL, supported pay-in and payout XCD (EC$), fees/tax/refunds/chargebacks, hosted return/callback, and risk controls. The WiPay Saint Lucia marketing page alone does not prove which endpoint your specific merchant can use.
6. A real provider sandbox checkout with a test merchant account and correct return signature: invalid amount, mismatch, replay, cancellation, foreign learner, restart, and no course entitlement for sandbox. Synthetic signatures in GitHub CI do not replace provider sandbox.
7. A **separate owner-approved** low-value live payment, provider ledger reconciliation and bank payout/settlement validation, only after an approved production candidate is installed.
8. An independently reviewed new approved **main-branch SHA**, exact container image digest and rollback plan. Never substitute the draft PR SHA for a deployed image, alter the R18 accepted proof or bypass the protected production release workflow.

## Immediate disposition
- **Source/test readiness:** supported by the linked isolated CI evidence.
- **Installed server readiness:** UNKNOWN — no fresh authorized read-only container evidence gathered in this work.
- **Merchant activation and live settlement:** UNKNOWN — no account-specific confirmation or real provider transaction here.
- **Merge:** NOT AUTHORIZED. **Deployment:** NOT AUTHORIZED. **Real payments:** NOT AUTHORIZED.
- **Next bounded approval:** only a read-only runtime observation, if the operator's authorized access is available. Anything that changes services, data or payment configuration requires a separate explicit approval.
