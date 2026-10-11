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

## G2.5 — isolated loopback HTTP handoff (tested, NOT installed in Acer NOC)

The `integrations/sentinel/loopback_http_fixture.py` harness uses a **temporary HTTP listener on `127.0.0.1` with a random OS-assigned port** for disposable tests only. It is not a production endpoint, never binds `0.0.0.0`, does not read actual NOC devices/SQLite databases, does not use real Hub/Tiquet accounts, and is not imported by `noc/server.py`. A synthetic Ed25519 private key plus HMAC secret enter only via a test child's stdin; stdout contains its ephemeral port only. The handler suppresses request logs, sends `Cache-Control: no-store` and denies browser cookies, bearer authorization, request bodies and unapproved methods.

`integrations/sentinel/test_loopback_http.mjs` verifies **actual HTTP transport** across the proposed fixture trust contract:
- Node issues a fresh request challenge and signs a GET on the fixed endpoint with an ephemeral HMAC key.
- Python's loopback listener checks authorization, query/method restrictions and one-use request state, builds only local synthetic source-side aggregate counts, and Ed25519-signs those counts.
- Node verifies signed response bytes against the ephemeral pinned public key and single-use challenge, **retaining `sourceVerified:false` and `readyForExecutiveUse:false`**. The response contains no raw service name, IP or QA result.
- HTTP replay -> 409; tampered HMAC/cookies/cross-tenant -> 401; mutation/query paths -> 404; stale monitoring -> generic 503 with no signature or private details. No NOC or customer record is modified.

**Precise scope:** The tests demonstrate cross-language protocol and a disposable loopback HTTP implementation **only**. They do not establish real Sentinel publisher identity or collector freshness, TLS peer identity, durable multi-process replay defense, key rotation/revocation, client org provisioning, operational high availability, firewall policy, or production NOC integration. Real Acer NOC remains unchanged. These issues are mandatory before any production or external-customer connection.

Latest protocol run: https://github.com/MrFixITslu/V79hub/actions/runs/38099901550 (14 Python tests, 11 Node interoperability tests, 0 failures). Full Hub CI is independent; record its exact result before calling the latest draft head fully green.

### Recommended isolated Acer staging transition (not executed)

1. Verify a fresh source SHA, detached backup/restore test and absence of uncommitted work in the real Sentinel worktree.
2. Independently review Python HMAC dispatcher, signer and fixture's strictly loopback binding. Obtain approved immutable source files; **never copy experimental files into a running `noc/` package or substitute the operator authentication handler**.
3. Run only disposable loopback fixture with ephemeral synthetic keys in a separate virtual environment; verify it reaches no real NOC endpoint or customer database.
4. For an eventual real local source integration, create a new designated service identity with server-held V79 org mapping, a private mutually authenticated transport, dedicated signed GET route, source-key custody and auditable durable replay protection. Require independent security acceptance and owner authorization before enabling.

## G2.5 Acer-specific test evidence received — 2026-10-11 AST

The owner ran the exact isolated clone at `/home/firelion/v79-g2-staging.lqW04ehw` with pinned G2.5 SHA `fa14b046ac938baf7a4a5d4c2e622ea8817297a6` and Node `v24.18.0`. Ubuntu was missing `python3.12-venv`; that dependency was installed, `cryptography==46.0.4` was installed in an isolated virtual environment, and `npm ci` completed. The `npm allow-scripts` notice regarding esbuild was non-fatal; **do not approve install scripts without necessity**.

Actual Acer results: **14 Python unit tests passed** and **11 Node interoperability/HTTP tests passed, zero failures/skips**, with the literal completion marker `=== G2.5 ACER STAGING TESTS PASSED ===`. This is host-specific evidence beyond the earlier GitHub CI success; it is **not** production Sentinel operation, independent security certification or a real NOC API connection. No existing services were restarted or modified.

## G2.6 read-only source-layout preflight (development only)

Added `integrations/sentinel/read_only_acer_preflight.py` and fail-closed tests. The tool requires a **fully specified expected staging SHA**; checks both worktrees are distinct, reads only git revision identifiers and presence of the isolated protocol files and Acer NOC source modules. It emits **no credential, source code, port or host data**, performs no file writes, no HTTP, no port checks, no sudo and no restart. It deliberately reports `productionReady:false`, `trustedLiveCollectorVerified:false` and `liveDeploymentAuthorized:false` regardless of source layout.

This is only a convenience for the next source/transport **review**. It does not validate real secure key custody, cryptographic trust binding to running NOC, mTLS/Tailscale ACLs, monitored device readiness, multi-worker replay resistance, external audit, or customer activation. The full source review and live activation still require independent approval and controlled change management.

## G2.8 first owner-observed local NOC source shape (2026-10-11 AST)

The owner executed a read-only `sentinel_mission_bridge.snapshot()` call inside the actual Acer `enterprise-command-center-staging` checkout (NOC source head previously verified as `5f7b226eb5e8`), reporting ONLY:
- `source` = `local-mission-control`
- `monitorMode` = `live` (**a string in the source response, not proof of actual collector state or device inventory**)
- `lastCheck` present, string's trailing-`Z` test **false** (actual timestamp value and timezone not supplied)
- `services` count 7; reported states: `up` 7 (not independent proof of seven real device health measurements)
- `qa` object present.

The existing G2.7 prototype demanded trailing Z for all raw source timestamps. That can reject a *valid, timezone-aware* native Python ISO string with `+00:00` or `-04:00`. New G2.8 producer logic accepts explicit ISO-8601 timezone offsets **only**, normalizes to canonical `YYYY-MM-DDTHH:MM:SS.mmmZ` before signing, and rejects timezone-naive/ambiguous values. The signed contract itself remains **strict canonical UTC**; it is NOT relaxed to permit ambiguous time. Signed observation freshness/expiry and source identity checks remain enforced. New unit tests cover UTC offsets, Caribbean offset, timezone-less rejection, stale/future source, unbounded offsets and wire-format rejection.

New `integrations/sentinel/source_contract_probe.py` reports **only** a timestamp type category, field-shape match flags, bounded service counts and whether the current local snapshot is compatible. It does not print raw time, device names, addresses, QA records, exceptions, or secrets. It always emits `trustedLiveCollectorVerified:false`, `sourceIdentityVerified:false`, `readyForExecutiveUse:false`, `productionReady:false`, even when the source reports `live`. Nine synthetic tests verify these exclusions.

**Actual timestamp format, source object field names and independent real monitored-source/collector attestation remain unknown until the new local read-only compatibility probe runs.** Do not claim G2.8 is integrated or the collector verified from a reported `live` label. No NOC server, process, key or device configuration has been changed.

## G2.9 — real bridge projection + independent local readiness report (2026-10-11)

**Owner-observed Acer result at G2.8 immutable SHA `e553247c2a26fa1a9b59ac40474ad42dd27ed6fc`:** the new `source_contract_probe.py` imported the existing `noc/sentinel_mission_bridge.py`, obtained one local NOC snapshot and returned `producerProjectionCompatible:true`, source/service field matches `true`, `timestampKind:"explicit_offset"`, `reportedMode:"live"`, `reportedServiceCount:7`, `stateCounts:{up:7,down:0,degraded:0,unknown:0}`. It correctly returned `sourceIdentityVerified:false`, `trustedLiveCollectorVerified:false`, `readyForExecutiveUse:false`, `productionReady:false`. No raw NOC details were printed, and no running services changed.

**G2.9 staged development** (still ONLY on this Hub draft feature branch):
- `integrations/sentinel/local_snapshot_projection.py` reads one local Mission Control snapshot using the same strict `aggregate_mission_snapshot` validation (bounded count, exact fields, known states, freshness and explicit timezone), then prints **only** aggregate counts and non-attestation flags. It deliberately omits exact timestamps, names, internal addresses, QA, incident details and all signer keys, and claims no real collector verification or production readiness.
- `integrations/sentinel/local_collector_readiness.py` makes a single **bounded GET to fixed `http://127.0.0.1:8787/readyz`**, no redirects, no cookies/auth headers, no arbitrary destination, no writes. Prints a short allowlisted representation of reported collector/integration state, never raw HTTP body, arbitrary fields or exceptions. A self-reported `live` or `active` is **not** independent attestation. Unavailable endpoint returns generic `readiness_unavailable`.
- 17 new synthetic unit tests prove redaction, fixed destination, deny redirects, malformed input, missing timezone, unbounded data, no false monitoring claims, generic failure.
- The actual Acer local source projection and local NOC `/readyz` probe **have not** yet run. There is NO newly installed NOC route, production key, network listener, authenticated Hub agent feed or customer monitor.

**Next safe on-host gate:** clone an exact reviewed G2.9 commit to another isolated Acer directory and invoke each standalone diagnostic once, using the existing isolated Python venv, with `PYTHONPATH` pointed to the separately reviewed Acer `noc/` source. Do not disable source checks or copy experimental code into the running NOC. Compare reported services vs reported readiness without asserting actual device collection. Real signed-source ingestion remains gated by secured on-host signer key custody, private authenticated transport, validated collector provenance and independent security review.
