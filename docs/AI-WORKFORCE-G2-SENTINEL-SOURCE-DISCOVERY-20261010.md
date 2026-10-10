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

## Proposed shape only — not actual Sentinel response schema

The standalone `agent-service/src/sentinel-proposed-contract.ts` accepts synthetic bounded V79-only totals for monitored devices, unreachable devices, critical and warning open incidents, with strict observation time, schema and organization checks.

Even if structurally valid, output status is **`candidate_unverified`** and `readyForExecutiveUse:false`. Nothing from the parser can enter an executive evidence ledger until the real Sentinel route is independently reviewed and a new service-to-service signed source verification layer is implemented and tested. The proposed numbers and field names are **placeholders** and may be revised to match actual Sentinel data.

No external IP addresses, raw packets, usernames, MAC addresses, incident narratives, ticket bodies, device inventories, credentials or arbitrary extra keys are accepted.

## Required next source review

From the existing Acer worktree, inspect **only source code** and redact literal secrets if any:
```sh
WORK=/home/firelion/V79-Sentinel/enterprise-command-center-staging
sed -n '145,275p' "$WORK/noc/server.py"
sed -n '1,95p' "$WORK/noc/sentinel_mission_bridge.py"
sed -n '1,100p' "$WORK/noc/sentinel_private_gateway.py"
```

Confirm exact `GET /api/v1/dashboard` and `GET /api/v1/mission-control` response producer calls, **identity and authorization**, tenant scope, available aggregate metrics and a producer-observed timestamp. If these routes require browser cookies, **do not reuse or export an admin cookie** for machine access. Build a distinct narrow GET-only machine service with signed request ID, nonce/replay protection, expiring responses, server-derived founder/organization scope, strict body size, timeout and immutable read audit.

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
