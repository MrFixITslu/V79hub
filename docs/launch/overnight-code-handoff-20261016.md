# V79 overnight code-preparation handoff (16 October 2026 AST)

**Audience:** Founder and release coordinator. **State:** source-only preparation for next owner-controlled review. No production changes, merge, paid activation or customer invitation.

## Known live baseline (founder-provided grouped audits)
- Hub `sha256:d0dfba263dbfec8a08e6c46995c2172daf234206fe8d0f6484bb98b938cd3c65`; currently labeled `ui-overlay-b1c2a24e903509d4037d0166bc31813fcf25e228`.
- Tiquet `sha256:5e69de603794f0e318c75a10eefd0f62d1d80f75fb40979658416292ce44ec42`, candidate tag `v79-tiquet-p1-sec:59b8e51fd1c`.
- Agent `sha256:3d5f280fb5c8703b4a429e7541cbd8a079dea0cbb26e67df291ce9dee25e334f`.
- Hub has **13 ordered Compose overlays**, not the earlier nine. Current MFA ON, Tiquet entitlement recheck ON, legacy login OFF, WiPay sandbox.
- All five current-image/DB container identities in the v4.1 inspection healthy. Founder-only browser suite passed before the latest Hub UI-overlay image; do a narrow post-change smoke, not the full earlier suite.
- Historical ciphertext backups and isolated DB restorations PASS for their historical release only. v5 located 47 matching component ciphertext hashes between Acer/server, but **no complete current-release restorable set**, and no verified Tiquet DB ciphertext pair on Acer. Acer scan was truncated. Current full app/keys/config/rollback boot remains NO-GO.

## New isolated code packages (do not merge automatically)
| Lane | Draft PR | Scope | Tested at exact branch HEAD |
| --- | --- | --- | --- |
| Hub recovery | [Hub #157](https://github.com/MrFixITslu/V79hub/pull/157) stacked on draft #156 | Fail-closed read-only exact-image/health/security/ordered-Compose SHA contract; no backup or restore | [isolated workflow 38996153935](https://github.com/MrFixITslu/V79hub/actions/runs/38996153935) PASS |
| Academy | [Academy #28](https://github.com/MrFixITslu/V79acaedmy/pull/28) stacked on draft #27 | Explicit publication target, accurate Academy/website success UI, Published state handling | [corrected workflow 38996430736](https://github.com/MrFixITslu/V79acaedmy/actions/runs/38996430736) PASS |
| POS | [POS #14](https://github.com/MrFixITslu/V79POS/pull/14) stacked on draft #13 | Reject external/mismatched Hub JWKS, DB/Redis host-published ports, host network | [isolated workflow 38996395079](https://github.com/MrFixITslu/V79POS/actions/runs/38996395079) PASS |
| FFPRO | [FFPRO2 #40](https://github.com/MrFixITslu/FFPRO2/pull/40) from main | Move PostgreSQL off shared proxy onto internal network; app remains dual-network | [boundary workflow 38996571720](https://github.com/MrFixITslu/FFPRO2/actions/runs/38996571720) PASS; [broader production-readiness 38996571686](https://github.com/MrFixITslu/FFPRO2/actions/runs/38996571686) PASS |
| Games | [Gaming Studio J #20](https://github.com/MrFixITslu/Gaming-Studio-J/pull/20) from main | Spelling Bee stale takeoff/gate/landing timer guards and double-start smoke | [existing CI 38996826260](https://github.com/MrFixITslu/Gaming-Studio-J/actions/runs/38996826260) PASS |

Only these five code packages were edited. All are **DRAFT**, separate from main, and no runtime test or production deployment is implied by CI.

## Existing candidate reconciliation (no additional parallel implementation)
- Tiquet [#40](https://github.com/MrFixITslu/V79Tiquet/pull/40) is the cumulative #37→#38→#39 JWT and WS revocation candidate, already tagged by current running image. Need actual installed-image negative tests and independent security review. Hub-only logout does not necessarily invalidate a 30-minute Tiquet session; agree policy before changing it.
- Marketing [#28](https://github.com/MrFixITslu/V79Marketing/pull/28) already deployed to its tracked image according to previous reports. Its local projection tests cover duplicate provider dispatch and confirmed receipt handling. **First actual provider receipt→calendar acceptance remains unverified.** Do not merge to main as housekeeping: auto deployment is a risk.
- Sentinel [#14](https://github.com/MrFixITslu/V79-Sentinel/pull/14) security-scan hold persists; #16–#18 are advisory synthetic signed evidence only. No verified real collector or live protective alert cycle.
- Website, LaserTag, SIWM, MCP and additional P2 modules: no unverified production changes were attempted; preserve their own release guards and perform scoped defect-driven work after P1.

## Morning review order (must not be automated)
1. **Freeze** production image identities and preserve all 13 Hub Compose overlays including pinned WiPay. Check whether the Hub UI-overlay browser owner MFA→Workboard→Tiquet smoke still passes.
2. Review Hub #157 read-only contract and inspect non-secret mount destinations/backup source inventory. **Do not run obsolete** `scripts/workforce-offhost-backup.sh` or `scripts/workforce-recovery-rehearsal.py`: both hard-code image `33a357...` and nine overlays.
3. Owner separately authorize fresh encrypted, off-server backups of *current* Hub+Tiquet images/DB/data/config/keys; preserve all historical archives. Only then authorize a no-production-network/no-live-mount isolated full boot/rollback rehearsal with a reviewed secret-handling plan.
4. Independent reviewer signs off current Hub/Tiquet security and checks narrow Tiquet logout JWT replay, multi-tenant API denial, staff+portal WS revoke timing (including Hub outage). Existing complete synthetic replay tests should not be repeated indiscriminately.
5. After recovery/security gates, check one non-owner internal Tiquet invite/trial and inbox delivery, mobile, support/legal and 3–5 business prospect plan. External customer beta needs **separate** signed founder GO; paid WiPay/settlement needs a later separate GO.
6. P2 review stacked Academy #27→#28 and POS #13→#14 **in order**. FFPRO #40 requires isolated DB-private-network reachability proof and correct Hub SSO before deployment; Games #20 requires phone/keyboard actual retry acceptance. Do not merge to main while CI/CD auto deploy may be present.
7. Marketing first provider receipt and calendar reconciliation is a supervised external-provider acceptance, not a source deficiency confirmed by current evidence.
8. Continue LaserTag, SIWM, MCP, website and other app development in their respective feature branches after provenance review, without adding new release blockers to P1.

## Explicit release holds
- **GO:** Founder-only supervised internal Hub/Tiquet work and read-only CEO/COO reporting (based on previous owner tests).
- **NO-GO:** Customer beta; paid subscriptions; Sentinel as proven protective monitoring; unattended privileged AI actions.
- **UNKNOWN:** Whether latest UI-overlay image retains every older runtime module, until accepted current source/mount parity and narrow browser smoke.
- The five new PRs do **not** demonstrate complete app implementation or recovery. Treat errors as separate blockers and preserve immutable evidence.

**No live server, customer data, WiPay credentials, MFA seeds, SSH sessions, production images, volumes or DNS were touched by this code-preparation batch.**
