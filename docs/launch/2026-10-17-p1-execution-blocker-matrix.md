# V79 P1 release closure — 17 October 2026
**Control:** owner-only internal Tier A allowed; outside customer Tier B and paid Tier C **NO-GO**.
**Program:** Hub + Tiquet customer launch, supervised internal CEO/COO operations; Sentinel is internal owner-service protection, not a customer monitoring product.
**Source of truth:** [Hub issue #152](https://github.com/MrFixITslu/V79hub/issues/152) and [focused launch board #113](https://github.com/MrFixITslu/V79hub/issues/113).

This is a release coordinator's evidence ledger, **not** a live server measurement, security sign-off, payment settlement, runtime deploy instruction or authorization to merge.

## Execution sequence — only retest changed properties

| Gate | Locked evidence | Exact remaining evidence | Disposition / role / impact |
|---|---|---|---|
| **G0. Preserve tested existing owner flow** | Host reported live Hub and Tiquet image integrity/health; exact installed prior two-org Hub→Tiquet SSO and replay/anonymous/legacy-login negative tests PASS; owner browser login/MFA and direct Tiquet dashboard PASS | Pin current effective image IDs, DB versions, secrets **names not values**, 13 ordered Hub Compose files, Tiquet Compose, proxy/Entitlement flags, private mounts; preserve WiPay and report/timer settings; record rollback before altering anything | Internal Tier A CONTINUE. Release coordinator. Never re-run full prior SSO rehearsal if original image remains unchanged |
| **G1. Tiquet cumulative auth/WebSocket hardening** | [Tiquet PR #40](https://github.com/MrFixITslu/V79Tiquet/pull/40) consolidates #37/#38/#39. Isolated actual-code source tests and disposable PG portal close tests pass. Current installed Tiquet is **not** this candidate | Independent review of exact cumulative source; verify effective \`V79_ENTITLEMENT_RECHECK_ENABLED=1\`, Hub URL and shared-secret bindings at target runtime; decide Hub-only vs Tiquet logout semantics; test bounded revoke-to-close and DB failure on final image; make schema+rollback explicit | **BLOCKS Tier B**. Reviewer/security lead + release coordinator. Current Hub logout **does not prove global Tiquet single logout** |
| **G2. Signed ticket and two tenant boundaries on final candidate** | Original-image synthetic A/B one-use Hub launch ticket, own-tenant access, anonymous/legacy denial PASS (v79x-0c27ad9a7b). Unmerged [Hub PR #149](https://github.com/MrFixITslu/V79hub/pull/149) has mocked paired-app acceptance | Narrow *changed-code* synthetic A/B negative check: same-ticket reuse denied, revoked/expired staff and portal sockets closed, cross-tenant read/write/socket refused, original login preserved. Record exact final Tiquet and Hub digests + identity-scope fixture receipt; clean isolated test resources | **BLOCKS Tier B**. QA+reviewer. Do not create real customer tenants merely to test |
| **G3. Full current encrypted offhost recovery** | [Hub PR #158](https://github.com/MrFixITslu/V79hub/pull/158): founder's Acer capture reported **14 encrypted off-host streams captured**. Prior historical checkpoints verified restored DBs/offline boot on older images | Revalidate existing 14 archives via updated verifier (no recapture), with local PostgreSQL 17+ client for PG17 structural checks; independently restore current Hub+Tiquet config, volumes, both databases, apps and exact images to isolated runtime; verify health/auth/tenant controls and exercise measured rollback. Store receipt IDs privately; no secret output | **BLOCKS Tier B**. Recovery owner and independent reviewer. Last \`--verify\` was stopped by decrypt/pg_restore validation; neither corrupted backup nor successful full restore may be assumed |
| **G4. Owner MFA, release provenance and delivery guard** | Real Hub G2 creator worker: approved job → one COO task and worker actor; rejected job → zero tasks; in-memory replay/idempotency passed. Draft [Hub #159](https://github.com/MrFixITslu/V79hub/pull/159) CI PASS. Tiquet automatic deployment on main is disabled | Reconcile exact live G3 + signed G2 with draft #155/#156/#159, and paired Tiquet #40; independently verify current backup/rollback + planned deploy-only-image diff; ensure no hidden Tiquet auto-deploy, price/WiPay drift or privilege widening; independent reviewer / founder authorizes exact immutable release | **BLOCKS Tier B**. Technical release owner. Draft code must not be merged or published automatically |
| **G5. CEO/COO briefing sustained reliability** | Oct 16 19:00 AST unattended evening run reported available; owner approved+rejected real G2 task cases; isolated 88/88 source tests PASS, draft host uppercase status parity fixed | Observe Oct 17 08:00 AST run **after it occurs** and subsequent 3 full days both slots, authenticated private report inventory, evidence freshness; confirm real source coverage and report ownership. Delivery/marketing adapters and measured provider costs not yet proven | **BLOCKS full AI Workforce acceptance**, **not by itself** a reason to disable current owner-only Tier A Hub/Tiquet |
| **G6. Sentinel real V79-owned service alarms** | Acer Sentinel staging/UI and isolated signed observation/replay candidates exist; no real V79 server collector shown live | Resolve Sentinel [independent review #3](https://github.com/MrFixITslu/V79-Sentinel/issues/3) and confidential GitGuardian finding before promotion; attest real canary collectors, source clock, data freshness, signed replay, alarms and local escalation without fabricated telemetry | Internal monitoring P1 / Sentinel external customers **NO-GO**. Operations/security owner. Do not conflate simulated seven-device network with genuine probes |
| **G7. Customer beta and privacy** | [Hub #150](https://github.com/MrFixITslu/V79hub/pull/150) contains draft 3–5 organization/14-day Tier B onboarding, support, trial and reviewer kit. No beta invites authorized | Founder approves final privacy terms, service support commitment, exact list of invited real organizations; one authorized owner invitation/reset delivery test; support, export/delete and incident rehearsal. Confirm zero unintended test accounts | **BLOCKS Tier B**. Founder + reviewer. Do not send customer invites yet |
| **G8. Merchant settlement and finance** | WiPay sandbox checkout and manual fallback design were demonstrated earlier; Hub merchant-live entitlement cannot be inferred from a payment screen | Merchant/KYC authorization, live callback authenticity + idempotent reconciliation, deposit settlement, refund and reversal, unpaid invoice handling, manual bank-cleared-funds + MFA + two-person audit and customer legal copy | **BLOCKS Tier C paid GO**. Founder/finance. Tier B free cannot silently collect funds |

## Work allowed without further owner action

1. Review GitHub cumulative candidates against source ancestry and record exact SHA/diff/CI outcomes, not guess at installed images.
2. Add **test-only**, negative-security and documentation improvements to existing draft branches, preserving tested runtime dependencies.
3. Run GitHub-hosted, non-deploying synthetic CI (isolated DB/loopback only). Separate CI infrastructure failures from app failures.
4. Prepare a narrow immutable-image release verification plan and independent reviewer brief, keeping P1, P2 and Sentinel contracts separate.
5. Continue P2 development **only in already-scoped isolated branches**, with no live deployment.

## Operations prohibited until explicit exact release approval

- No production merges, deployments, Compose/image switches, database migrations or backup overwrites.
- No new owner credentials, admin/tenant privileges, secrets, MFA bypasses, autonomous privileged tool calls or Sentinel customer monitors.
- No real customer invitations, messages, subscription entitlements, WiPay transactions or paid claims.
- No broad acceptance statement derived only from green CI. Independent reviewer and owner decision are distinct.

## Release decision record (unapproved template)

**Tier B:** NO-GO pending G1, G2, G3, G4, G7 and applicable service security. Date/owner/immutable code and running image IDs **UNSET**.

**Tier C:** NO-GO pending Tier B plus G8. Provider KYC, cleared funds and refund policy **UNVERIFIED**.

**Sentinel external release:** NO-GO independent of Hub/Tiquet (G6 and separate reviewer).

**Next owner-supplied evidence, only when practical:** Oct 17 morning report run (no changes); existing offhost capture reverify on Acer using exact new verifier and local PG17 client, *not another capture*. Then independent security/recovery signoff and exact-SHA release decision. Do not ask founder to redo previous approved/rejected G2 task tests.
