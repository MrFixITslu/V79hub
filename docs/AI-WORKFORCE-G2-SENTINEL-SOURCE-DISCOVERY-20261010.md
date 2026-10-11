# G2 — Sentinel NOC source contract discovery (development-only)

**Date:** 2026-10-10  
**Sentinel source worktree:** `/home/firelion/V79-Sentinel/enterprise-command-center-staging`  
**Observed Sentinel branch/SHA:** `feature/enterprise-command-center-20261010` / `5f7b226`  
**Hub target:** founder-only AI Workforce. **NO new production endpoint/connection is enabled by this PR.**

## Verified route locations from founder's Acer source search

| Existing code location | Observed callsite | G2 interpretation |
| --- | --- | --- |
| `noc/server.py:158` | `authorized(self,mutate=False)` | Need to inspect actual session, MFA, scope and reuse restrictions |
| `noc/server.py:247-249` | `GET /api/v1/mission-control` calls `self.authorized()` | Candidate *human UI read*, not yet an M2M evidence source |
| `noc/server.py:254-255` | `GET /api/v1/dashboard` calls `self.authorized()` | Candidate *human UI read*, not yet an M2M evidence source |
| `noc/server.py:258-259` | `GET /api/v1/owner-pilot` calls `self.authorized()` | Candidate *owner UI read*, not yet a verified API for AI |
| `noc/server.py:267-268` | `GET /api/v1/reports/incidents.csv` calls `self.authorized()` | Potentially sensitive incident export; **not approved** for model access |
| `noc/server.py:412` | `POST /api/v1/incidents/ack` | **Prohibited** in read-only AI pilot |
| `noc/server.py:287-301` | `POST /api/v1/sentinel/service/approver/check` machine signature validation | Approval/security route, **not** a read-only metrics feed |
| `noc/sentinel_mission_bridge.py:16,33-34` | local `/api/status` and `/api/qa/latest` | Mission Control internal bridge; must review scope and privacy before use |

These are source callsites; **not** proof of working HTTP responses, safe field shapes, signer identities or production readiness.

## Actual source contract discovery — 2026-10-10

The founder provided actual Acer source excerpts from `5f7b226`:

- `noc/server.py:150-168`: `current()` hashes an existing operator session value, looks up `sessions` joined to non-disabled operators and enforces expiry. `authorized(mutate=False)` requires that operator session; mutation additionally verifies origin and `X-Sentinel-CSRF`. **This is a human-session authorization boundary, not a signed organization-bound machine read grant. Do not export/reuse admin cookies.**
- `noc/server.py:169-178`: `GET /healthz` is a text liveness response; `GET /readyz` reports `collector:"simulated-only"` and `integrations:"disabled"`. **A Docker healthy status or a monitorMode "live" claim must not override this limited collector status.**
- `noc/server.py:247-256`: authenticated `GET /api/v1/mission-control` invokes `mission_control_snapshot()` while `GET /api/v1/dashboard` invokes `self.server.store.snapshot()`. The latter's fields remain unreviewed and are **not** an approved AI source.
- `noc/server.py:258-269`: `/api/v1/owner-pilot` needs an operator with `admin` role; `/api/v1/reports/incidents.csv` is operator-gated and is **not** an AI source.
- `noc/sentinel_mission_bridge.py:1-75`: `snapshot()` fetches only local `http://127.0.0.1:8787/api/status` and `/api/qa/latest` with a 1.6-second timeout and 250 KB body cap per source. It constructs `source:"local-mission-control"`, `monitorMode:"live"|"staging"`, `lastCheck`, up to 24 `services` with `name/state/http/latencyMs`, and a QA object with aggregate result counts and bounded named results. **The local read is not proof of signing, source identity, or tenant isolation.** No owner organization ID appears in the observed summary fields.

The new `agent-service/src/sentinel-proposed-contract.ts` is a **pure synthetic-only projection aligned to these observed Mission Control fields**. It accepts a strictly bounded shape, rejects unknown fields, invalid timestamps, implausible latencies/HTTP statuses and more than 24 service rows; it discards service names and the entire QA payload. It returns *only counts by service state* (up, down, degraded, unknown) and observation time. Zero services is `no_data`, not "all healthy."

**All outputs remain `sourceVerified:false` and `readyForExecutiveUse:false`**, including structurally valid `candidate_unverified` results. The parser does **not** know the genuine founder tenant or validate a signer and must never be used as a replacement for server-side authorization. It is not integrated with Hub or any AI tool.

No raw packet data, IP addresses, usernames, MAC addresses, incident narratives, ticket bodies, QA names, credentials or source service names are forwarded in the resulting projection.

## Required next source review

From the existing Acer worktree, inspect **only source code** and redact literal secrets if any:
```sh
WORK=/home/firelion/V79-Sentinel/enterprise-command-center-staging
sed -n '72,110p' "$WORK/noc/sentinel_mission_bridge.py"
sed -n '1,100p' "$WORK/noc/sentinel_private_gateway.py"
grep -nE 'def snapshot|def mission_control_snapshot|def current|self.server.store.snapshot' "$WORK/noc/server.py" "$WORK/noc/store.py" "$WORK/noc/sentinel_mission_bridge.py"
```

Confirm the remaining Mission Control return fields and exact timestamp formats, then verify whether `store.snapshot()` includes sensitive inventory before ruling the dashboard source out permanently. The human-session authorization boundary is now confirmed; the dedicated machine GET contract, owner tenant mapping and signed envelope remain unimplemented. If these routes require browser cookies, **do not reuse or export an admin cookie** for machine access. Build a distinct narrow GET-only machine service with signed request ID, nonce/replay protection, expiring responses, server-derived founder/organization scope, strict body size, timeout and immutable read audit.

## G2 acceptance and future promotion criteria

1. Confirm source SHA and protected NOC runtime health; no device enrollment, packet capture, network scan or customer data access.
2. Agree real source field allowlist from actual producer code. Missing/undated/stale source becomes **unknown/unavailable**, never zero.
3. Authenticate signed machine callers and distinguish their grant scope from human MFA approval routes. No arbitrary URL, SQL or parameters accepted from the model.
4. Test forged/stale/replayed/wrong-org source, oversized payload, unknown fields, quote-injection, missing metric and no outgoing POST.
5. Reuse proven owner-scoped Hub evidence ledger; COO technology specialist may analyze *verified* bounded aggregate counts only; CEO receives source-backed priorities.
6. Keep Sentinel→Tiquet ticket creation out of scope. Any future one-ticket pilot requires separate technical/security review, owner MFA and explicit enablement.
7. Preserve Hub/Sentinel protected modules, rollback, backups and no-workflow-auto-deploy policy.
8. Run GitHub CI on exact candidate SHA, independent review if required, and owner acceptance before any production activation.

**This PR is a non-integrated synthetic contract/test artifact only.** It does not modify live Sentinel or Hub source paths, expose an API endpoint, request credentials or activate automated agents.
