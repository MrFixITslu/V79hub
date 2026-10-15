# V79 Digital — independent release reviewer handoff
Date: 15 October 2026 | **DRAFT PROCUREMENT BRIEF / DO NOT PEN-TEST LIVE SERVICE WITHOUT SIGNED AUTHORIZATION**

## Objective

Obtain an **independent, narrow, evidence-based security and recovery review** of the already-running V79 Hub + Tiquet service for an invite-only **3–5 business, 14-day external beta**. The owner wants to **reuse passed engineering results**, not purchase another generic retest of the same SSO flow. Separate a later paying-customer decision and a future Sentinel/Edge customer-monitoring release.

Owner/project: V79 Digital, Saint Lucia | https://v79sl.com | Master gate [Issue #113](https://github.com/MrFixITslu/V79hub/issues/113).

## Exact system scope

**Primary beta scope:** Hub account registration by invitation, admin and organization roles, MFA/session handling, trial entitlement, Hub→Tiquet one-time signed launch, Tiquet cookie/bearer sessions, tenant-scoped APIs/uploads/WebSockets, Tiquet PostgreSQL records, error/incident logging, application backups and restricted administrative paths.

Last owner-observed running identifiers (reconfirm privately before assessment):
- Hub image `sha256:33a357c6c73f45ef05edcef57c6c0abf9234022cbec1c30041c463b2f3ff8d06`.
- Tiquet image `sha256:ee3deff332977160d66e0dbb448aef1e1e6d4418eac333e1feaf8a07c044715b`.
- Hub source revision `045d68a61257c758f2f6ca229d050e4e7a7df618`; Tiquet image locally tagged from retained source `81f46592...` but exact deterministic image-to-build lockfile provenance still needs review.
- The two applications have distinct Compose deployments; Hub also has an exact pinned WiPay overlay that must be preserved.

**Out of scope for this beta unless explicitly separately contracted:** Sentinel Edge enrolment and NOC machine monitoring; CEO/COO autonomous actions; publishing Marketing, Academy, POS or FFPRO to customers; live merchant charges/refunds; data destruction; brute-force scanning/traffic disruption; modifying DNS/firewall/production images.

## Give the reviewer evidence first — accept it when sufficient

| Existing test | Proof to provide | Not covered by that test |
| --- | --- | --- |
| Exact installed images, synthetic A/B | Operator V4 run `v79x-0c27ad9a7b`, both apps ready, seven SSO/tenant asserts PASS, scratch cleanup and protected production services unchanged; [Issue #113](https://github.com/MrFixITslu/V79hub/issues/113) | Session expiry/revocation across apps, file & WebSocket multi-tenancy, independent penetration review. |
| Paired source CI | Hub [draft PR #149](https://github.com/MrFixITslu/V79hub/pull/149) @ `95315ac...`; [CI PR 38781495458](https://github.com/MrFixITslu/V79hub/actions/runs/38781495458) PASS, including synthetic suspended tenant A denied while B unaffected and logout clears cookie | Copied JWT invalidation (cookie deletion alone does not invalidate JWT), deployed image parity beyond pinned installed-image rehearsal. |
| Human browser MFA/direct launch | Founder completed MFA, landed at Tiquet dashboard with correct org and no secondary login; signed-out direct visit directed to Hub | Complete negative tests, new-customer invitations/reset and mobile role boundaries. |
| Offline recovery | Oct 13 encrypted checkpoint 14/14, 5 saved image imports on Acer, recovered Hub/Tiquet app+PG boot and anonymous deny; [recovery doc](../g12-recovery-and-reversible-cutover-20261013.md) | Fresh full checkpoint off-host custody, exact original user MFA decryptability and full Docker/Compose/WiPay rollback. |
| Release deployment | Tiquet [PR #34 merged](https://github.com/MrFixITslu/V79Tiquet/pull/34); [main CI 38784353601](https://github.com/MrFixITslu/V79Tiquet/actions/runs/38784353601) PASS with publishing/SSH deploy SKIPPED | Explicit manual ecosystem dispatch, repo branch protection and exact rollback still require governance. |

## Focused threat-model questions requiring NEW evidence

1. **MFA, credential/session continuity:** old or copied JWT after logout, MFA step-up recency for organization/finance administrators, stolen session, password reset, session renewal and expiry; fail closed on revocation.
2. **Cross-tenant paths:** direct object IDs, list/filter/pagination, uploads/file URLs, Tiquet WebSocket room join/broadcast, account assignment, error disclosures, admin impersonation; test with disposable orgs A/B only and no real external data.
3. **Entitlement consistency:** organization trial expiration and revocation while Tiquet session already exists; caching upper bounds; Hub outage fail-closed; malicious token organization mismatch.
4. **Access controls:** onboarding invitation lifecycle, origin/CSRF on cookie mutations, signed service-to-service HMAC nonce/time, one-time ticket double consumption, admin-only and organization role separation, log redaction.
5. **Operational recovery:** exact current running release overlay dependencies, encrypted current-state off-host checkpoint & separate key custody, original-identity MFA decryptability inside isolated restore, Tiquet uploads/file access and incident response/RPO/RTO; no production data restore without separate owner authorization.
6. **Dependency/config boundary:** Tiquet local-vs-packaged `package-lock.json` dev-field drift, source-to-image provenance, port/network/mount minimum privileges, production cookies/TLS, rate limits, secret storage/rotation, scanner findings relevant to **deployed** Hub/Tiquet.
7. **Payment boundary (only if contracted for Tier C):** WiPay callback signatures/idempotency/settlement and nonpaid trial logic; manual bank proof/MFA/DB multiwriter uniqueness, refund/audit. Payment GO remains a separate financial decision.

## Acceptable test plan and constraints

- Start with a **read-only document/source/deployed-image/config review**. Report which earlier evidence you accept rather than demanding full journey repetition.
- Agree named target domains and Docker digests, legal permission to test, schedule, source artifact access, approved **disposable** test identities, permitted nonintrusive methods and stop conditions.
- Isolated fixtures first, no testing with real customer information or uncontrolled production writes; do not alter production authentication, users, DBs, keys, firewall, DNS or token vault without fresh scoped founder authorization.
- Keep logs, findings and attachments in restricted owner-controlled storage, using redacted IDs and no private key, MFA seed, password, access token or actual customer record.
- For any confirmed vulnerability: produce **file/line or route, severity, realistic exploit consequence and minimal regression test**; security fix only in a draft review branch; retest just the changed failure path.
- Block external beta on unresolved critical/high customer-data/privacy/authentication findings. If scope or confidence is inadequate, explicitly return NO-GO rather than falsely certifying.

## Requested deliverables

1. Signed scope and rules of engagement, fixed **immutable image ID/date**, reviewer independence declaration and reviewer contact.
2. Short threat model + findings register with Critical/High/Medium/Low, affected customer boundary and reproducible **safe isolated** evidence.
3. Remediation list limited to material remaining risks, plus reviewer retest results tied to final approved image IDs or source commits.
4. Recovery/incident gap assessment: whether full off-host copy, recovered key access, exact Docker restore and tested rollback meet reasonable beta requirements.
5. Signed **Tier B security recommendation**: GO, conditional GO with *specifically bounded non-high findings*, or NO-GO; separate the founder's independent final decision.
6. Separate optional commercial Tier C findings; no assumption that free beta authorizes taking payment.

## Ready-to-send independent reviewer request — draft, not sent

**Subject:** Independent scoped security review — V79 Hub + Tiquet invite-only beta

Hello [reviewer name],

V79 Digital is preparing a small, invitation-only 14-day pilot of its Hub and Tiquet applications for Saint Lucian service businesses.

We have already completed exact-installed-image synthetic two-organization sign-in/tenant tests, a human owner MFA/direct-launch smoke, and several encrypted backup and offline recovery checks. We are seeking an **independent reviewer** to examine the remaining customer-facing security and recovery risks—especially session revocation, file/WebSocket tenant boundaries, invitation/reset flows and off-host recoverability.

We do **not** need a generic replacement of the tests that have already passed. We would like your proposed scope, fee, schedule, approach to handling sensitive source/configuration, and signed findings/retest deliverables. All intrusive testing would require agreed authorization and disposable fixtures; no production tests are authorized by this message.

Could you review the attached scope and propose a focused engagement?

Thank you,
V79 Digital
From Idea to Advantage
https://v79sl.com

## Signoff tracker

`Reviewer | NDA & scope approved | Exact image IDs | Findings report | Critical/high fixed & retested | Recovery assessment | Signed Tier B recommendation | Founder Tier B decision`

Until all required approvals are recorded: **External beta NO-GO. Paid subscriptions NO-GO.** Internal owner-only synthetic operations can continue. See [pilot operations](2026-10-15-beta-pilot-operations.md) and [decision packet](2026-10-15-release-decision-and-evidence.md).
