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

## Signed machine-response prototype (isolated, not connected)

New `agent-service/src/sentinel-signed-response-prototype.ts` performs **in-memory verification with an injected trusted Ed25519 public key only**. There is no network client, API endpoint, key provisioning, private key, credential, storage change, or model integration in this PR.

The proposed synthetic envelope contains precisely:
`{schemaVersion:1,keyId,organizationId,requestId,issuedAt,expiresAt,payloadJson,signature}`.

The signature covers the **exact UTF-8 bytes** `V79-SENTINEL-READ-G2-v1\\n` followed by the JSON serialization of the ordered seven signed fields excluding signature (the source contract code is authoritative). `payloadJson` is a string, not an arbitrary object to be re-canonicalized by a receiver. Only ephemeral test keys are generated in the tests. The verifier pins an externally supplied Ed25519 public key and key ID and refuses unexpected keys.

The source must **aggregate locally before signing**. The signed `payloadJson` is required to be exactly `{schemaVersion:1,source:"local-mission-control",observedAt,monitorMode,counts:{servicesObserved,up,down,degraded,unknown}}`. It is NOT the raw `mission_control_snapshot()` response: browser-QA data, per-service names, HTTP details, incident descriptions, IP addresses and packet bodies are forbidden in the signed transport itself. `sentinel-signed-aggregate.ts` validates this strict pre-aggregate schema independently from the source-side projection.

The test-only verifier issues random UUID challenges, enforces single-use nonces in a bounded **in-process map**, verifies the expected organization ID, strict key ID, issue/expiry windows, payload size (UTF-8 bytes), Ed25519 signature, and pre-aggregated service-health schema with observation age. Even malformed responses burn a matching request ID. No service identifiers, QA details or free-text strings can traverse the proposed transport boundary. **Even a cryptographically valid fixture returns `sourceVerified:false`, `readyForExecutiveUse:false` and `signature_valid_synthetic_only`.** This avoids presenting a synthetic signing key as a verified actual Sentinel publisher.

Critical future obligations *not* met by this experiment:

1. Implement a separate **GET-only, owner-tenant-bound machine read endpoint in actual Sentinel NOC**; do not reuse browser sessions, `/api/v1/sentinel/service/approver/check`, arbitrary service URLs or incident acknowledgement routes.
2. Provision and independently verify the **real Sentinel public-key binding**, rotation/revocation policy, owner org mapping, trusted issuer, outbound HTTPS/mTLS trust and service network restrictions; signing a synthetic payload does not establish identity.
3. Preserve challenge ownership and replay safety across **multiple instances/restarts** using an authoritative shared, expiring nonce store or an equivalent request-bound design. The prototype's in-process replay map alone is not a distributed production security guarantee.
4. Confirm separate server-side entitlement and founder context before any executive read; do not promote `candidate_unverified` parser results or test signatures into the existing signed Hub product ledger.
5. Use approved signed freshness and monitor-state semantics; the currently observed NOC `/readyz` says **simulated-only**. A browser monitor claiming `live` is not sufficient to report active network protection.
6. Demonstrate a no-write, no-customer-data, no-session-reuse, fail-closed end-to-end test against an **isolated running NOC** with a real source signing implementation before any deployment decision.

This is an intentionally *non-integrated* security contract prototype, not operational monitoring.

## G2.3 prototype: Python producer + authenticated GET policy (still not installed)

Added `integrations/sentinel/source_signer.py`, `read_only_dispatcher.py` and isolated fixtures/tests to the Hub G2 feature branch **as staging source material only**. The modules have **not** been copied to the Acer Sentinel worktree or wired into `noc/server.py` and do **not** expose an HTTP listener.

The current prototype uses two independent protections: (1) a fixed-path, GET-only request HMAC for a provisioned caller and (2) an Ed25519 signature on the returned pre-aggregated status envelope. Only a scoped owner organization and key ID from trusted server configuration can be accepted. Replay attempts are blocked by a bounded in-process nonce cache; the final Node verifier also requires a matching single-use challenge. **Neither ephemeral replay map is durable across workers/restarts.** An external trusted read proxy/TLS identity and centralized replay protection are mandatory before production.

The Python producer accepts the locally constructed Mission Control bridge schema at the trusted source. It validates freshness and state values, discards browser QA and all service names, and signs only `{schemaVersion,source,observedAt,monitorMode,counts}`. Private keys belong only in a future protected file/secret store with least privilege; none are shipped here. **Do not reuse the existing machine-approver signature secret for this read service.**

### Exact integration proof / development test

- `integrations/sentinel/test_source_signer.py`: ephemeral Python Ed25519 keys, source-side raw filtering, timestamp bounds, challenge scope and private fields.
- `integrations/sentinel/test_read_only_dispatcher.py`: HMAC caller validation, GET-only/no query, wrong tenant/key, replay, stale request, no secret in error responses and no raw-data output.
- `integrations/sentinel/test_cross_language.mjs` + `emit_test_fixture.py`: Python creates a signed fixture, Node validates using the existing G2 verifier and rejects replay/tamper. **No live networks, browsers, actual keys or customer records**.
- `.github/workflows/sentinel-g2-interoperability.yml`: separate isolated PR/workflow test gate with Python cryptography pinned to `46.0.4`. It makes no deployment artifact or production release.

### Explicit remaining gates before connection

1. Owner/maintainer must inspect and patch real Acer `noc/server.py` to mount a **distinct** authenticated GET-only machine endpoint after security code review. Never replace operator authorization with caller-controlled headers.
2. Provision real source identity: Ed25519 signing private key in a secured source-side secret store, pin/rotate/revoke its public key in the Hub agent verifier, provision **separate** request-HMAC credentials and bind them to V79 founder organization server-side.
3. Require actual transport trust: private tailnet/mTLS or equally reviewed mutually authenticated channel and allowlisted origin host; absolutely no public Internet listener, arbitrary proxy URL or credential printing.
4. Implement and test a shared/durable nonce store for a multi-instance service, rate limits, credential rotation, failed-read audit without sensitive payloads and appropriate time sync.
5. Validate with a disposable isolated NOC using real Python signing code and the Node verifier; test authentic/forged/wrong tenant/replayed/stale/overlong responses and *prove zero writes*.
6. Distinguish the independent Mission Control browser/public QA page checks from NOC's actual collector. At reviewed SHA `5f7b226`, NOC `/readyz` still declares **simulated-only** and integrations disabled, so no real live Edge device/incident claims are permitted on this pathway.
7. Obtain separate technical security acceptance and explicit owner release approval with exact immutable commit, backup and rollback plan. Keep Hub/Tiquet launch controls and paid onboarding unchanged.

**Until these gates are completed, nothing in the Python prototype authorizes ingestion into COO/CEO business evidence, and absolutely nothing is activated in production.**
