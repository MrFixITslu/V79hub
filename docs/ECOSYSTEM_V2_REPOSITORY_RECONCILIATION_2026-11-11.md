# V79 Ecosystem v2 — repository reconciliation and code-first release baseline

**Evidence snapshot:** 11 November 2026 (Saint Lucia, UTC−04:00). **Owner policy:** complete code, reconcile with actual runtime, stage, test, and only deploy after acceptance. **No deployment or PR merge is authorised by this inventory.**

## Status definitions

- **GREEN = independently verified** for the exact capability cited; not necessarily merged, deployed or accepted in the production browser.
- **YELLOW = existing code, draft or partial integration without complete release evidence.**
- **RED = missing, blocked, failed CI or no sufficient cross-app contract evidence.**
- UNKNOWN must never be represented as a pass. All protected production states and exact deployed image SHAs are UNKNOWN until read directly from the host.

## Release ownership (do not create duplicate sources of truth)

| Domain | Authoritative source | Key contract |
|---|---|---|
| Organisation, memberships, access and entitlements | V79 Hub | Signed app launches; explicit tenant mappings |
| Public web enquiry and early sales CRM | Website CRM | Staff approval; stable lead and intake event IDs |
| Service customers, jobs, appointments, due dates, invoices, provider-verified receipts, files and feedback | V79 Tiquet | Tenant-scoped IDs; a recorded payment is not itself delivery acceptance |
| Products, physical stock, purchase orders and inventory cost ledger | V79 POS | Compensating entries, not speculative stock |
| Budgets, planning and FFPRO financial records | FFPRO | Do not treat FFPRO projections as verified business payment settlements |
| Campaigns, channels and provider publishing evidence | V79 Marketing | Provider consent, official API confirmations and no simulated reach |
| Courses, enrolments, outcomes | V79 Academy | Learner ownership; no fabricated completions |
| Monitoring observations | V79 Sentinel | Read-only evidence until explicit signed escalation contract |
| Owner-approved commands and tool access | Hub/MCP candidates | Default deny and approval-gated writes |
| Cross-app executive reporting | Hub read models | Receipts are not an accounting ledger |

## Audited repositories (GitHub source + latest main branch CI)

| Repository | Main SHA prefix | Source / CI evidence | V2 reconciliation status |
|---|---|---|---|
| [V79hub](https://github.com/MrFixITslu/V79hub) | `afefdb921581` | Main V79 CI/CD PASS; draft [#251](https://github.com/MrFixITslu/V79hub/pull/251) adds signed event inbox; isolated [three-app run #43017926092](https://github.com/MrFixITslu/V79hub/actions/runs/43017926092) PASS | **GREEN only for Website/Tiquet/Hub tested event slice**; **YELLOW** for unmerged Hub changes and live owner SSO |
| [V79Tiquet](https://github.com/MrFixITslu/V79Tiquet) | `2c4d652cab2f` | Main CI PASS; draft [#64](https://github.com/MrFixITslu/V79Tiquet/pull/64) CI/security PASS; tested signed event delivery and real linked IDs | **GREEN** tested intake/event slice; **YELLOW** invoice emails, customer acceptance, billing, feedback and cancellation until live acceptance |
| [v79website](https://github.com/MrFixITslu/v79website) | `cfaf0b04ae12` | Main Production checks PASS; draft [#86](https://github.com/MrFixITslu/v79website/pull/86) checks PASS, staged approval/duplicate semantics | **GREEN** tested website→CRM→Tiquet approval; **YELLOW** exact live homepage/Hub admin login and restored source provenance |
| [V79POS](https://github.com/MrFixITslu/V79POS) | `e4bf7620f5e6` | Main CI and Release Check PASS; draft [#17](https://github.com/MrFixITslu/V79POS/pull/17) technician inventory work | **YELLOW** app code proven by CI; **RED** Tiquet job-part reservation and cost allocation |
| [FFPRO2](https://github.com/MrFixITslu/FFPRO2) | `eafd786301c9` | Main production-readiness PASS and CD success; signed Hub summary documented | **YELLOW** app and summary; **RED** project-level expense/margin or cross-app ledger parity |
| [V79Marketing](https://github.com/MrFixITslu/V79Marketing) | `74a0b4594740` | Main CI PASS; substantial draft [#38](https://github.com/MrFixITslu/V79Marketing/pull/38); provider access dependent on actual OAuth approvals | **YELLOW** code and draft; **RED** verified Marketing attribution→Website CRM→Hub lifecycle |
| [V79acaedmy](https://github.com/MrFixITslu/V79acaedmy) | `584e07c9f518` | Course builder code and publishing branches; most recent publishing workflows SKIPPED rather than PASS | **YELLOW** app source; **RED** verified Hub learner-completion events and integrated billing acceptance |
| [V79-Sentinel](https://github.com/MrFixITslu/V79-Sentinel) | `59eb0f738c3b` | Main isolated regression PASS; source README documents local Acer monitor and draft signed alert chain | **YELLOW** monitoring; **RED** verified incident→Tiquet or owner task end-to-end |
| [V79-MCP](https://github.com/MrFixITslu/V79-MCP) | `526e1c53b0cf` | Main contains one README and no CI; draft [#4](https://github.com/MrFixITslu/V79-MCP/pull/4) and [#6](https://github.com/MrFixITslu/V79-MCP/pull/6) contain proposed action surfaces | **YELLOW** drafts only; **RED** proven deployable production MCP bridge |
| [V79Analytics](https://github.com/MrFixITslu/V79Analytics) | `0eae1a5136b8` | Main V79 CI/CD **FAILED**; standalone app source, not a verified Hub KPI service | **RED** for a V2 reporting integration; keep separate from Hub executive truth |
| [v79netpulse](https://github.com/MrFixITslu/v79netpulse) | `468083892a10` | Desktop installer CI PASS; standalone local lab, not a Hub-integrated service | **YELLOW / adjacent** only; no supported Hub event connection |
| [V79-Inbox-Guard](https://github.com/MrFixITslu/V79-Inbox-Guard) | `5d5feb193d7c` | Main README only, no CI | **RED** as an operational cross-app mail/approval module |

These repository observations do not prove which exact code version is running on `v79sl.com` or each SaaS subdomain.

## VERIFIED GREEN capability — exact synthetic integration proof

[Run #43017926092](https://github.com/MrFixITslu/V79hub/actions/runs/43017926092) built and ran isolated Hub, Tiquet and Website images; all four jobs PASSED. Positive evidence includes:
- two synthetic tenants and real provisioned Tiquet account mapping;
- website form capture, CRM audit/duplicate handling and a staff-review requirement;
- **zero** Tiquet intake tickets before approved conversion;
- approved conversion returns the real customer/job IDs, with exactly one linked job and safe retry;
- signed Website and Tiquet events are received by Hub with opaque correlation;
- second tenant cannot see the first tenant's event.

**Staged source versions:** Tiquet `eb90d4581a8e5906cbe1ad3cd90b05188176ef61`, Website `69b365d4621e25a454832cd7aee527547daac2a5`, Hub `82b6343b9fd8b91a345903a6a474fb4510ed7a4c`. Later documentation commits do not constitute a newly tested binary.

**Not proven by this run:** Google OAuth, MFA, real web admin SSO, live mail, WiPay, signed contracts/proposals, delivery acceptance UI, cancellation payment races, off-host restores, current live icons, or cross-app flows for the additional products.

## RED-TEAM: existing branch collisions that MUST be reconciled before code freeze

1. **Canonical business name (do not merge all variants):** Hub #243/#244; Tiquet #60/#61/#62/#63; POS #18; Marketing #36/#37/#38. Pick Hub as authoritative, implement signed, versioned, tenant-scoped update with retries and audit. Avoid circular edits and overwriting invoice-era legal business names.
2. **Tiquet billing/cancellation overlap:** Tiquet #59 and V2 #64 edit customer workflow/payment/email surface. Compare exactly, preserve the newer approved invoice/PDF requirements, and do not issue automatic refunds or create phantom payment success.
3. **Identity/SSO overlap:** Hub #234/#238/#246 and Website #62 carry security/auth work. Preserve existing Google login, mandatory MFA, session token ownership, Hub launch gating and tenant isolation; stage protected browser flows before promotion.
4. **Website real-source drift:** Website #76–#79 describe guarded overlays already used operationally but unmerged. Rebuild a pristine candidate from the **verified live source**, not blindly from `main`; retain user's approved logo, favicon, hero and public site version.
5. **POS inventory UX:** POS #17 technician stock portal and #18 name sync need reconciliation with exact current POS API, inventory ledger and tenant membership. Never deduct inventory from an unverified ticket update.
6. **Marketing studio and provider state:** Marketing #32/#34/#35/#38 and #39 are overlapping branches. Confirm saved SQLite schema and live source/connection keys before consolidation; no fabricated channel data.
7. **Academy pricing and learner gates:** Academy #29–#37 contain competing pricing/checkout/display and canary fixes. Preserve actual approved XCD prices and correct authenticated learner, without manufacturing paid status.
8. **Sentinel / MCP draft chains:** Sentinel #20–#32 and MCP #3/#4/#6 are stacked and mostly unmerged. Keep read-only or owner approval gates until signed endpoint, replay prevention and custody of secrets are stage-tested.
9. **V79Analytics failing CI** and README-only support repositories must not become required production dependencies just to complete V2.

## Coding and release sequence (the owner will run host commands later)

**R0 — reconcile source and invariants:** read-only verification of deployed image digests, source paths, schema versions and data backup integrity for all eight production-facing apps. Mark UNKNOWN if host evidence unavailable; do not ask the owner to run destructive commands.

**R1 — source consolidation before a new staging run:** create one release candidate branch per affected repository from its authenticated deployed baseline. Diff every competing PR against that baseline; transplant only tested desired deltas; retain favicons, layouts and protected auth. Keep dormant features OFF. Create a common event/tenant/role matrix, not shared databases.

**R2 — finish required coding:** complete tenant-safe canonical name sync, reviewed lead and customer data authority, Tiquet email/quotes/invoices/acceptance/cancellation, POS service-parts cost flow, Marketing attribution, Academy learner signals, Sentinel incident escalation and owner-approved MCP controls, **or mark optional items deferred and remove them from the promised release scope**.

**R3 — code freeze:** immutable commit/digest manifest, contracts and test fixtures across repos. No branch updates or silent floating image tags after this point.

**R4 — isolated cross-app stage:** two tenants and denial tests; replay and restart durability; payment and delivery races; security and consent; no external sends. Run all relevant app CI on the exact frozen SHAs.

**R5 — real staging on V79 host:** backup+restore rehearsal, full Hub Google→MFA→Website and Tiquet SSO, mobile browser/branding, real mail delivery and invoice CC, WiPay gateway confirmation, monitoring, app-by-app rollback.

**R6 — deploy only on evidence:** owner reviews consolidated test matrix, residual risks and rollback proof; promote previously staged pinned digests one app at a time, with all new flags OFF until separately accepted.

## Blockers / decisions that must NOT be guessed

- Exact running deployed sources/image digests and true production customer mappings: **UNKNOWN** (remote host command quota previously blocked access).
- Stacked PRs that conflict or contain features marked deployed: **source reconciliation is NOT complete**.
- Full application-to-application contract, POS parts ledger, FFPRO profit margin, Academy learner events, live Marketing provider integration and Sentinel incident creation: **not end-to-end proven**.
- Live payments, SMTP, MFA/SSO and restore test results: **not verified by disposable staging**.

**Overall:** inventory completed; tested 3-app slice GREEN; multi-repository code reconciliation YELLOW; remaining bridges and live release acceptance RED. No deployment performed.
