# V79 Digital — controlled Hub + Tiquet pilot readiness
**Evidence date:** 2 November 2026 (Saint Lucia AST)  
**Decision boundary:** Internal/owner operational scope is GO; **external non-owner customer invitation is HOLD until independent security/privacy sign-off and explicit founder customer-release approval**. WiPay live and paid activation remain HOLD. Do not turn on Tiquet self-service registration.

## LATEST OWNER DIRECTION — 2 November 2026 (supersedes earlier review hold)
- Founder completed the existing Humble Bee internal pilot and explicitly directed V79 to **skip the independent security/privacy assessment and move to the next phase**. That external assessment is **WAIVED BY OWNER, NOT PASSED**, and residual third-party security/privacy risk remains.
- **Stage gates still enforced:** invite-only; 3–5 externally selected businesses in first cohort; 72-hour invitations; Hub MFA/operator-only administration; Tiquet-only 14-day trial; no public sign-up, no payment capture, no autonomous customer invites; explicit recipient approval and basic customer terms/privacy notice still required. No external customer addresses were supplied in this phase, so none was invited. This is a limited risk-accepted pilot, **not** certification of unrestricted commercial readiness.
- Internal non-owner Humble Bee test: **owner reported successful completion**; accepted existing trial and Tiquet mapping retained, no duplicate invitation or extension. Live Hub, Website and Tiquet healthy with zero restarts on current deployed images.
- **Phase 2 WiPay read-only verification:** effective Hub configuration on 2026-11-02: `WIPAY_ENV=sandbox`, `WIPAY_CURRENCY=TTD`, `WIPAY_COUNTRY_CODE=TT`, `WIPAY_ENABLED=1`, `V79_BILLING_PROVIDER=disabled`. WiPay's provider response (27 Oct) confirmed **Saint Lucia transactions/settlement are USD-only**, with a distinct Saint Lucia gateway. The owner requested authoritative return verification, trusted recurring charges and server-to-server status; no provider answer after the 28 Oct follow-up was found during the search. **DO NOT flip the sandbox flag, reuse public test credentials, change a production currency alone or credit customer entitlements on a browser redirect.** Live billing GO is blocked until merchant verification, dedicated credentials, response verification and settlement reconciliation.
- **Next unblocked Phase 3 action:** prepare and owner-select a shortlist of **3–5 consenting businesses** for a controlled, free Tiquet-only 14-day pilot; review existing invited/active records to avoid duplicates; issue 72h invitations only to specifically approved addresses; confirm delivery/acceptance, provision the mapped tenant, and verify customer identity, least privilege, logout, support channel and trial expiry. Never claim a waiver removes legal privacy or information-security duties.
- This addendum overrides contradictory earlier references below that say the independent reviewer is mandatory before any invitation. All other protective controls and the live-payment HOLD remain applicable.

## 1. Exact currently verified production release
| Component | Image digest | Verified |
| --- | --- | --- |
| Hub | `sha256:248550f677563449e8b5ddf2c389d869beee7bb95160f0bc8f10dd0dcbbed3a6` | healthy, zero restarts, HTTPS 200 |
| Website/Web Admin | `sha256:8b72baad211ec8313402f9961f7704dff635bcfe604301dd889443b8239352bb` | healthy, zero restarts, HTTPS 200 |
| Tiquet | `sha256:7b5ef21d4f0858b41224fc523622aa56db293ff1ad07535528817c1ec602d721` | healthy, zero restarts, HTTPS 200; anonymous /api/jobs 401 |

Hub session lineage bound to Tiquet: ON; entitlement recheck: ON; legacy Tiquet sign-in: OFF. Owner reported successful Hub MFA → Tiquet navigation and logout acceptance, 2 Nov. The pinned Tiquet security-only release is in [PR #55](https://github.com/MrFixITslu/V79Tiquet/pull/55); Hub/Website sessions in Hub #224 and website #62. Do not confuse an unmerged PR with an undeployed image. Tiquet prior image remains in stopped `v79-tiquet-rollback-20261102`.

## 2. New isolation evidence (scope matters)
A new **production-mode, actual Tiquet image + disposable PostgreSQL 16 + two synthetic business tenants + mock signed Hub** test on the Dell reported PASS. Tests covered:
- Tenant A and B each reading only its own jobs and denial of cross-business job files.
- Anonymous protected API denial, two separate staff WebSockets, cross-business socket rejection.
- Revoking Hub session A denied A's HTTP access, closed its existing staff WebSocket at revalidation and **left B active**.
- 16 authenticated HMAC-bound mock Hub backchannel requests. No real customer records, real payment, live Hub impersonation or production database writes.
- The disposable network and containers were removed; live containers remained healthy, zero restarts.

Protected local test receipt: `/home/firelion/.v79-tiquet-p1-20261102/safe-release/pilot-isolation-20261102.receipt`, SHA256 `814dbcc1c81b8212b1572e5ae11034d2d00a57ff05411fada87a6357272d10f0`. This is **not** an external penetration test or real two-customer browser verification. Existing earlier synthetic/backup tests need not be repeated without changes.

## 3. Recovery and email evidence
- Acer P1 encrypted off-host Hub+Tiquet backup service and health check **succeeded 2 November**; earlier Tiquet PG16 (25 table) and Hub PG17 restores PASS. Prior Tiquet image and unchanged /app/data and /app/uploads volumes retained for guarded rollback. New backup scheduler retention and a full live recovery drill have distinct limits.
- Connected Resend account: sending ENABLED; DKIM and two SPF CNAME statuses VERIFIED. Overall domain `partially_failed` because optional tracking CNAMEs are pending/failed. **No assertion that a trial invitation reaches an actual recipient inbox**; do not change Hub DNS to fix email tracking.

## 4. Launch tiers and controls
**Tier A — founder internal operations: CONTINUE.** Existing owner uses live Hub+Tiquet without unapproved external customers or payment.

**Tier A+ — one non-owner internal disposable test organization: PREPARED, not activated.** Founder chooses an internal consenting tester. Do not invent an email, publish invite tokens, or use existing customer addresses. Existing Hub Admin Customers UI has a platform-operator-only invite route; validated source sets a **72-hour invitation expiry default**, supports Tiquet-only `app-tiquet`, and issues a **14-day `V79 Hub Beta Trial`** upon accepted invitation. The application does not automatically provision Tiquet on invitation acceptance; operator provisions it separately. This requires an actual tester and private delivery channel; no internal invite has been sent in this work order.

**Tier B — invite-only 3–5 external business pilot:** HOLD until independent security/privacy review of exact live source, invitation/recovery email delivery to the intended inbox, lawful terms/privacy review, owner GO and bounded support/rollback. Scaling toward 10–15 invitees should follow initial test results, not precede them.

**Tier C — paid access:** HOLD pending verified WiPay Saint Lucia merchant currency/settlement/return flow, independent payment integrity, invoicing/refund procedures and separate founder GO. No checkout or subscription billing to be enabled now.

## 5. Operator one-pass pilot checklist
1. In **Hub → Customers**, inspect existing Invited and Active customers first to avoid duplicate live invitations. Reuse only an explicitly approved internal pilot.
2. For a consenting test organization with a real controlled inbox, select **Invite a new business owner**, expiration 72h, **V79Tiquet only**. Deliver the invitation privately and verify inbox receipt; never log, print, or paste invite URLs into issues.
3. Let the tester accept and set credentials. Confirm exactly one scoped organization and **14-day trial timestamp/expiry**, without manually granting paid entitlement.
4. Use **Provision selected apps** for Tiquet; confirm the **active** organization mapping. Do not assume acceptance provisioned it.
5. In a fresh browser/private profile, tester must see only assigned Tiquet, launch directly without secondary login, create one clearly labelled disposable job, see only their own records, and be denied platform admin, other org, agent, billing and application scopes.
6. Verify Hub logout denies subsequent Tiquet HTTP activity and closes an already-open staff socket; retain only minimal non-sensitive results and timestamps. Check phone viewport and recovery email if available.
7. Record explicit owner decision, incident/support contact, privacy/terms delivery, how feedback is collected, and safe 14-day expiry/withdrawal handling. Revoke invitations rather than deleting real data. Independently verify suspected security failures before expansion.

## 6. REDTEAM / Do not confuse
- Synthetic A/B denial != real-user browser separation on a live service.
- Signed SSO backchannel checks != independent audit or penetration-test certificate.
- Healthy Docker + HTTP 200 != customer login/purchase acceptance.
- Provider delivery *accepted* != delivered to the inbox.
- Internal founder GO != approval to enroll 3–5 external businesses.
- Running Tiquet customer portal branch #54 would be a separate schema + provider release; **keep it default-OFF**.
- Keep live payment, marketing publishing, autonomous writes, data cleanup and public registration OFF absent separate explicit approvals.

## 7. Next authorised action and status
**Status: TECHNICAL SECURITY TESTS COMPLETED; INTERNAL NON-OWNER INVITATION READY TO INITIATE BY FOUNDER.** The two still-required human/external facts are an explicitly approved internal tester's real inbox and an independent reviewer/customer release decision before invitations to external businesses. Neither can be manufactured by automation. Update [focused launch board #113](https://github.com/MrFixITslu/V79hub/issues/113) and [internal pilot #144](https://github.com/MrFixITslu/V79hub/issues/144) with scoped evidence; retain old proof and do not restart completed restore tests.
