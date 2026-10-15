# V79 Hub + Tiquet — consolidated G3 runtime and beta release evidence

**As of:** 2026-10-15T22:48:44Z (18:48 Saint Lucia)  
**Evidence mode:** owner-run SHA-256-verified read-only Acer SSH batch, plus distinct GitHub CI source evidence.  
**Decision:** **INTERNAL OPERATIONS ONLY. Tier B customer-beta NO-GO; Tier C paid NO-GO.**  
**Production changes from this record:** NONE.

## Why one matrix — three options and REDTEAM

1. Continue requesting individual repetitive owner terminal checks: rejected; more interruptions with diminishing new evidence.
2. Deploy currently green draft PRs directly to the server: rejected; risks replacing a protected nine-layer G3 image and breaking pinned payment, grants and login.
3. **Chosen:** use a single owner-verified runtime baseline plus nondeploying CI/reviewer findings. Schedule **one consolidated owner-supervised acceptance window only after a reviewed immutable candidate and recovery plan exist**.

A green GitHub workflow proves its candidate tests ran, not that its code is installed. HTTP 200 establishes only that the checked endpoint answered. Docker `healthy` is not audited tenant isolation or end-to-end payment success. An absent expected container name can reflect Compose service naming, not always an outage. No green label here authorizes production release.

## Immutable/current baseline — do not overwrite

| Runtime subject | Grounded observation | Status / meaning |
| --- | --- | --- |
| Hub | `v79-hub` running, Docker healthy, 0 restarts, image exactly `sha256:33a357c6c73f45ef05edcef57c6c0abf9234022cbec1c30041c463b2f3ff8d06`, revision `045d68a61257c758f2f6ca229d050e4e7a7df618` | MATCHES recorded owner-approved G3 tracking cutover; preserve |
| Marketing | running healthy; image exactly `sha256:32641b8f302b4ec38a56167ee6df9d5e0a185bf017431fa86f5bb9f462f7eaf3`, revision `de806c5c8db2d798ecb94621e3e1b04e9d7c8592` | MATCHES accepted G3 tracking cutover; NOT commercial launch scope |
| Hub Compose chain | **9 ordered layers**, no missing file, dry parse PASS; baseline Compose SHA256 `186175ec20d10f817a9468b305fed86a6b0b4ae7cd380659e574df95ef688261` and WiPay pinned override SHA256 `8aa57bba2c6955ab5affe5394ed7bec2b9b2693bc05556db3bef0420bcc04b74` | Preserve EXACT order and pinned WiPay behavior; dry parse does not prove a restore |
| Hub PostgreSQL | running healthy, 0 restarts | Status only; restore unverified in this batch |
| Business Agent | running healthy under Docker user `1000:1000`; code modules present | Not proof of owner briefing or approved action end-to-end |
| Separate G1.2 agent pilot | running with **NO_HEALTHCHECK**, Docker user unspecified/root possible | Runtime health, token custody and behavior NOT ESTABLISHED |
| Tiquet + its PostgreSQL | both running healthy, 0 restarts; `/health/ready` = HTTP 200 | Current service responding; security candidate not deployed |
| Hub + Academy proxy paths | `/health` both HTTP 200 | Route availability only |
| POS | `v79-pos` running healthy, Compose service label `api` | The missing alias `v79-pos-api` is NOT evidence of a missing API |
| Academy | Course Builder running healthy; Postgres running without healthcheck | No course-publish contract/go-live claim |
| Main server Sentinel containers | no exact names `v79-sentinel`, `v79-sentinel-monitor`, `v79-sentinel-noc` | Standalone server protection unverified; cannot determine independent Acer NOC from this |
| Host capacity | 208 GB / 456 GB root used (48%); 4,734 MB memory available; 29 containers running | Not the current blocker |

## Installed versus candidate modules

| Component | Installed code/behavior observation | Candidate / acceptance |
| --- | --- | --- |
| Owner CEO/COO review and G2 approved-action support | `agent-executive-owner-proxy.mjs`, `workforce-action-routes.mjs` **PRESENT** in Hub | Browser founder MFA, token permissions, queue worker and real data handling NOT rechecked |
| Native COO GitHub workboard | `server/owner-coo-workboard.mjs` **NOT PRESENT** in installed Hub | [Draft PR #155](https://github.com/MrFixITslu/V79hub/pull/155) CI passes synthetic negative and browser-DOM cases only. Flag defaults OFF. No token or deployment approval |
| Tiquet durable session revoke | `tokenRevocation.js` **NOT PRESENT** | [Draft #37](https://github.com/MrFixITslu/V79Tiquet/pull/37) is security-review HOLD |
| Tiquet staff WebSocket Hub-only parity | Existing `tiquetSocketAccess.js` present; exact integrated candidate NOT live | [Draft #38](https://github.com/MrFixITslu/V79Tiquet/pull/38) stacked on #37; CI PASS |
| Tiquet portal live WebSocket revoke | `tiquetPortalSocketAccess.js` **NOT PRESENT** | [Draft #39](https://github.com/MrFixITslu/V79Tiquet/pull/39) stacked on #38; disposable Postgres + WS harness PASS; **not full app-server** |
| Sentinel signed/anti-replay state | No standalone Docker Sentinel names matched; external Acer NOC status UNKNOWN | [Draft #14](https://github.com/MrFixITslu/V79-Sentinel/pull/14) scanner/reviewer HOLD. Draft #16→#18 advisory / signature / checkpoint source tests PASS but **not active protection** |

## Unified gates for ONE future supervised acceptance pass

| Gate | Required proof | Status | Owner action now? |
| --- | --- | --- | --- |
| R1 Independent cumulative security review | Review Tiquet #37→#39, Sentinel #14→#18; resolve GitGuardian hold privately; no waiver for customers | **BLOCKED** | No secret or exception requested |
| R2 Verified immutable release candidate | Exact source-image mapping including protected live-only G3 code; strictly ordered nine-layer Compose and WiPay return; non-root constraints, signed publisher and rollback images | **NOT ESTABLISHED** | No deployment approval requested |
| R3 Current encrypted off-host restore | Validate archival integrity, private-key decrypt and isolated Hub/Tiquet/payment + app/config restore; confirm rollback of exact candidate and Compose stack | **NOT TESTED IN THIS BATCH** | Reserve for one pre-release gate |
| R4 Full tenant/auth browser acceptance | Founder MFA, direct-vs-Hub SSO, two disposable organizations, single-use launch/replay, logout/session revoke, staff/customer portal WebSocket lifecycle, denied old/other tenant | **NOT TESTED ON CURRENT RELEASE** | One supervised signoff window *after* R1–R3 |
| R5 Payment/email policy | WiPay sandbox callback, protected receipt/ledger and manual-funds operator rules, invite/recovery email delivery; no live merchant/paid GO inferred | **PENDING** | Separate Tier C decision |
| R6 Real Sentinel operation | Authorized owned endpoint probe, measurable source identity/freshness, healthy→down→recovery, tested founder alert, no simulated false all-clear | **NOT ESTABLISHED** | Internal isolated pilot after R1–R3 |
| R7 Founder release decision | Exact SHA(s), artifacts, restored backup, rollback procedure, redacted acceptance evidence and explicit Tier B vs Tier C GO | **NO-GO** | **Only request this once prior proof exists** |

**No repeated generic server check required now.** Any further GitHub/source review should proceed independently without user involvement. Ask the founder for one consolidated evidence/approval batch only when reviewer, immutable release and restore prerequisites are ready. Never delete test accounts, reset keys, enable customer billing, merge main, or change production under this document.

Related registers: [Hub #152](https://github.com/MrFixITslu/V79hub/issues/152), [focused launch #113](https://github.com/MrFixITslu/V79hub/issues/113), [Tiquet #35](https://github.com/MrFixITslu/V79Tiquet/issues/35), [Sentinel #15](https://github.com/MrFixITslu/V79-Sentinel/issues/15).
