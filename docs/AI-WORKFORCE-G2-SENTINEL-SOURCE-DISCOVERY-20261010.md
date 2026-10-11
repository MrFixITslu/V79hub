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

## G2.9 Acer process-to-port triage and safety correction (2026-10-11 AST)

Owner's read-only process discovery established **two separate localhost services**:
- Existing legacy Sentinel: `python3` PID `63629`, working directory `/home/firelion/V79-Sentinel/sentinel`, entrypoint `sentinel.py`, listening `127.0.0.1:8787`. A `GET /readyz` to this legacy service returned HTTP **404**. The old probe targeted this service by mistake.
- Enterprise Command Center NOC: PID `259865`, associated with the isolated checkout `/home/firelion/V79-Sentinel/enterprise-command-center-staging`, listening `127.0.0.1:8788`. The Python entrypoint could not be resolved from the available process arguments. Its HTTP `/readyz` response has **not yet been fetched**.
- The reviewed Enterprise NOC **source** `noc/server.py` declares `GET /readyz` at line `174` with self-reported `collector:"simulated-only"` and `integrations:"disabled"`. This is SOURCE content; actual runtime response at 8788 remains unverified. Do not confuse reported seven service checks with real Edge device collectors.

The G2.9 diagnostic `integrations/sentinel/local_collector_readiness.py` now pins a **single fixed** `http://127.0.0.1:8788/readyz` with no redirects, no environment proxy, no browser cookies, no credentials and bounded response. This is a no-write, localhost-only diagnostic and is NOT a deployable service connector or attestation. Tests assert no fallback to 8787 and no proxy use. The legacy service must remain undisturbed; **do not restart either process** based only on source/port discovery. Production/CEO/COO/customer monitoring remain blocked until source identity, actual collector, key custody, private machine transport and independent security review are verified.

## G2.10 — actual NOC runtime reports simulation; NetPulse capability review and passive evidence boundary (2026-10-11 AST)

**Actual runtime result:** the owner's Acer Enterprise Command Center instance answered `GET http://127.0.0.1:8788/readyz` with HTTP 200, `ready:true`, **`collector: "simulated-only"`**, **`integrations: "disabled"`**. That is confirmed from the running NOC (not just source inspection). Earlier Mission Control `monitorMode:"live"` / 7 reported `up` may reflect local service checks but **must not be represented as active real Edge monitoring, seven verified network devices or trusted executive evidence**.

**Inspected V79 NetPulse repository:** `MrFixITslu/v79netpulse` current `main` is a Tauri desktop network investigation app. It implements host NIC RX/TX counters using Rust `sysinfo::Networks`, optional manually invoked TCP connect and route diagnostics, and `dumpcap`/`tshark` packet capture/decoding using locally installed Wireshark tools. README expressly warns that host byte counters can encompass any traffic on each interface, not selected monitored devices, and that topology discovery via LLDP/SNMP is not integrated. It does NOT yet provide a trusted, multi-tenant service collector endpoint or secure remote device enrollment. Do not borrow packet capture, service discovery, or auto-probe features for a first deployment.

**G2.10 portable offline diagnostic prototype:** `integrations/sentinel/passive_host_counters.py` uses two fixed-file Linux kernel `/proc/net/dev` reads with a one-second interval. It returns only total RX/TX **byte deltas across non-loopback host interfaces**, interface count and sampling elapsed; no interface names, IPs, MACs, packets, DNS or application details. It has no listening socket, background process, elevated privileges, NOC changes, or remote targets, and adds no data to Hub. It fails closed on invalid/too-many interfaces, counters resetting, interface set changes and bad intervals. **Virtual or tunnel interfaces may be counted/double-counted**; a successful read proves a local kernel-counter sample only—not physical NIC attribution, host/device connectivity, bandwidth, loss, service uptime, an authenticated Edge agent, or real NOC collector operation.

The resulting report always includes `networkServicesVerified:false`, `remoteDevicesVerified:false`, `edgeAgentAuthenticated:false`, `trustedForExecutiveUse:false` and `productionReady:false`. Eleven synthetic unit tests enforce these denials and no sensitive data output. Independent on-host Acer execution is still necessary for a real local sample. No need to install Wireshark for this passive read; **do not enable packet capture** for this milestone.

**Remaining engineering/security gates before any real NOC integration:** explicit V79-owned pilot target inventory and consent, authenticated device/agent identity and key custody, service transport ACL/TLS, restart/durable replay requirements, source freshness/provenance, operator review of live NOC route implementation, raw data minimization and role separation, staging-to-production release parity, and independent security approval before customers. No claim of customer Sentinel launch.

## G2.10 Acer kernel source evidence — real single-shot sample (2026-10-11 AST)

The owner executed the exact read-only G2.10 `passive_host_counters.py` implementation at SHA `8cec36651ade8cc0a27514fed5d389a300df26f0` on the Acer in isolated checkout `/home/firelion/v79-g210-review.Z3QjGTJS`. It returned `status=passive_host_counter_sample`, `measurementOrigin=local_linux_kernel_proc_net_dev`, `intervalMs=1000`, `interfacesObserved=3`, `rxBytesObserved=220`, `txBytesObserved=188`, and `includesVirtualInterfaces=possible`. All collector/Edge/device/trusted/production status flags remained **false**. This is a local Linux interface-counter delta sample, not an authenticated remote network monitor, aggregate network bitrate, seven real Sentinel devices or verified interface identity. No user data, addresses, credentials or packet contents were collected; no running services changed.

## G2.11 — passive V79-owned pilot inventory review (development only)

New standalone `integrations/sentinel/passive_inventory_review.py` reads the Linux kernel's **existing** `/proc/net/route` and `/proc/net/arp` tables once. It **does not** send ARP probes, ping, TCP connects, SNMP queries, packet captures or any network traffic, and never starts/changes Sentinel services. The output consists ONLY of bounded route-entry counts, routed-interface count, default-gateway candidate count, cached-neighbor entry and distinct count, plus an explicit **approvedMonitoringTargets:0**, `activeScanPerformed:false`, `deviceOwnershipVerified:false`, `monitoringEnabled:false`, `productionReady:false`. Full interface names, gateway/neighbor addresses, MACs, masks and network details are never included.

**Important limitations:** existing ARP cache entries are passive OS artifacts and may be old/incomplete; they do NOT represent discovered, active or V79-owned devices. A default route is a *candidate* gateway, not a verified router or explicit permission to probe. Kernel tables do not demonstrate any connectivity or ownership. The result is a coarse, privacy-safe local host vantage assessment to inform an owner-reviewed, explicitly scoped pilot target manifest. No scanning, NOC collection, cloud ingestion, target enrollment or customer impact is authorized by this script.

Before genuine remote device checks: explicitly choose and approve each V79-owned pilot target/port or delegated monitoring agent; confirm reachable vantage, ownership and rights, minimum measurement permissions, timeouts/rate limits, locally encrypted storage if needed, signed distinct service identity, TLS/ACL transport, replay protection, incident freshness, one-device rollback and independent security review. Do not silently flip simulated-only to active or promote local source claims into COO/CEO findings. Operational priority remains narrow Hub+Tiquet launch and safely separated Sentinel pilot.

## G2.11 actual Acer passive inventory checkpoint (owner run, 2026-10-11 AST)

The owner checked out exact draft SHA `46ef743a1b7d775deec3cc1ea79e9d955ed823da` at `/home/firelion/v79-g211-review.aZWhhXE4` and ran `passive_inventory_review.py` on the actual Acer. It returned `status:passive_inventory_review`, **2 kernel route entries, 1 routed interface, 1 default-gateway candidate, 23 cached neighbor entries, 23 distinct cached neighbor entries**. Critically, **`approvedMonitoringTargets:0`, `activeScanPerformed:false`, `deviceOwnershipVerified:false`, `deviceReachabilityVerified:false`, `monitoringEnabled:false`, `sourceAuthenticated:false`, `productionReady:false`**. The output revealed no device addresses/MACs or interface names. These are Linux route/ARP cache indicators **not verified device inventory**; cached entries can be old, not connected, virtual or belonging to others.

## G2.12 offline human-owner target proposal, not authorization

Staged `integrations/sentinel/pilot_manifest_review.py` and `pilot-target-proposal.template.json` with **zero targets**. The validator inspects only an explicit local JSON manifest, rejects unrecognized fields, passwords/credentials, unsafe modes, non-RFC1918 target addresses, duplicate target identities, incorrect port types and more than **three proposed** endpoints; it emits only aggregate counts, never names, addresses or raw JSON. Accepted purposes: `gateway-availability` and `service-availability`. There are no network imports, TCP/ICMP/DNS/SNMP requests, captures, service starts, file writes or automations. Manifest status never grants monitoring, even if JSON syntax is valid: **`approvedMonitoringTargets:0`, `ownershipIndependentlyVerified:false`, `activeProbingAuthorized:false`, `collectorEnabled:false`, `productionReady:false`**. Client-side or local JSON `approved` fields are disallowed instead of being trusted.

Owner must **separately** provide an explicit list of V79-owned target IPv4 + permitted TCP port/purpose and confirm authority to perform a bounded check against EACH device. First pilot should be one gateway or owned server, with one-shot TCP connection/HTTP readiness only if separately authorized; not packet capture, broad LAN sweep, exploit scan, default target inference, automatic Sentinel ticket creation or background polling. Independently reviewed machine identity, HMAC/mTLS transport, fixed tenant scope, source attestation, monitoring provenance and customer-readiness security acceptance remain future gates. Existing legacy Sentinel port 8787, Enterprise NOC port 8788 and Hub/Tiquet remain unchanged. `collector:simulated-only` and `integrations:disabled` are still the last actual NOC runtime evidence.

## G2.13 — owner-approved ONE-time V79 server reachability result, separate from Sentinel collector trust

The owner supplied explicit permission for **one** V79 server TCP availability attempt to `192.168.100.163` from the Acer. A narrow HTTPS listener **TCP port 443** was selected for this one-shot check; the owner did not separately specify the port. The owner executed one direct `socket.connect_ex` with a three-second timeout on `firelion-Aspire-A315-51` and pasted this exact result: **`TCP OPEN`, 4ms, Attempts: 1**, no further probes. This is strong user-observed evidence of *one-time* Acer-to-V79 server TCP socket reachability on that port, and is **not** evidence of validated TLS/HTTPS content, application availability, source TLS identity, throughput, network topology, sustained health, or an enrolled authenticated Sentinel collector. The one-shot permission was **consumed**: any repeat/other-port/periodic check needs renewed explicit owner scope.

The running Enterprise NOC `127.0.0.1:8788/readyz` previously returned HTTP 200, `ready:true`, **`collector:simulated-only`**, `integrations:disabled`; this remains the last actual collector-readiness observation. The NOC's seven `up` service indicators are **not independent real-device proof**, regardless of the separate 443 result.

New G2.13 staging-only `integrations/sentinel/pilot_tcp_evidence.py` classifies a manually reported one-shot observation against a **separately supplied, exact IPv4/port/vantage scope**. Outputs only claimed outcome, single-attempt count, measured elapsed milliseconds and **denials** of independent cryptographic attestation, remote inventory, TLS/HTTP health, live collector, continuous monitoring, additional checking, production and executive-report trust. No IP/host names/credential/raw terminal data are printed, no connections are performed or authorized, no files are written, and no NOC/Hub/Tiquet routes are mounted. The scope object is constructed by the caller and is **not a cryptographic authority**; even matched scope is described only as `targetMatchesSuppliedScope:true`. The independent owner authorization resides in owner communication/issue trail, not in this class or a client-side manifest. Also classifies `simulated-only` NOC readiness as `simulation_confirmed`, and even self-reported `live`/ `active` NOC labels as **unattested** until independent source identity and transport requirements are met.

Unit tests enforce strict literal target scope, exactly one attempt, denial of any repeated/automatic probe, no PII output and no false live-collector/CEO claims. All G2 changes remain in **DRAFT PR #125**, unmerged/uninstalled. Do not auto-enable device monitoring, copy the user's one-shot authorization into scheduled jobs, reuse a stale source poll, or perform a second active TCP probe. Before a genuine collector pilot, require reviewed service identity/key custody, restricted V79 ownership/tenant binding, private authenticated transport, objective device evidence/freshness, no false promotion of simulated data, and independent security acceptance.

## G2.14 — owner-approved bounded 15-minute Acer-to-V79 server TCP pilot (2026-10-11 AST)

The owner approved **exactly one supervised pilot session** after the prior single reachability witness. The parameters are fixed by this authorization:
- **Source/vantage:** Acer hostname `firelion-Aspire-A315-51` (not the v79sl server).
- **Target:** one literal IPv4 `192.168.100.163` on **TCP port 443**.
- **Frequency:** at most **one socket connection attempt at each 60-second scheduled slot**, no catch-up bursts/retries.
- **Duration:** a hard **900-second/15-minute window**, starting at the first pilot execution. Schedule t=0,60,...,840 seconds = maximum 15 TCP attempts. The process terminates automatically after the 900-second limit. Per connection maximum timeout is 3 seconds.
- **Exclusions:** no additional IP addresses, ports, ping/ICMP, UDP, DNS, HTTPS content fetch, login, TLS/HTTP certificate checks, packet capture, installer, background service, auto-repeat, SNMP, traceroute, network scan, routing changes, server changes, NOC 8788 changes, legacy Sentinel 8787 changes, Hub or Tiquet changes.
- **Safety:** a local `~/.local/state/v79-sentinel/owner-approved-v79-server-443-one-pilot-20261011.once` (private mode 0600, state dir 0700) is atomically created **before** the first probe, consuming the approval even on an aborted session. A second invocation fails shut unless a separately reviewed/new authorization is granted. Ctrl-C stops early. Late schedule slots are skipped instead of fired in rapid succession.
- **Evidence:** the script displays no more than 15 sanitized per-attempt statuses (`tcp-open`, `refused`, `timeout`, `connection-failed`) with connection duration in milliseconds, followed by a cumulative summary. It uses only standard-library `socket.AF_INET`, `socket.SOCK_STREAM`, `socket.connect_ex`; **no** raw packet recording, credentials or remote writes.
- **Trust:** one-time TCP success or a successful bounded session proves reachability *only during those attempts*, not device identity, TLS correctness, HTTP health, seven NOC service statuses, sustained uptime outside the interval, monitoring enrollment or independent collector provenance. Every summary says `continuousMonitoringEnabled:false`, `independentlyAuthenticatedCollector:false`, `trustedForExecutiveUse:false`, `productionReady:false`.
- **Operational scope:** owner launch must be directly on Acer in a verified exact commit checkout. Acer Remote Desktop Commander connector last reported it **offline** while `v79sl` server was online; therefore, do **not** run the pilot from the server and falsely claim client-to-server reachability.
- **Source:** staged `integrations/sentinel/supervised_v79_tcp_pilot.py` and `test_supervised_v79_tcp_pilot.py`. Unit tests use entirely synthetic monotonic clocks/sockets; CI **never** contacts the actual V79 server. The pilot is NOT a deployed Sentinel Edge agent or NOC integration.

Do NOT assume real execution or an observed 15-minute result until the owner returns terminal output from the Acer. After completion, independently review evidence, decide if a future collector pilot should be permitted, and require new scope approval for additional checks. The running Enterprise NOC remains `collector:simulated-only`, `integrations:disabled` until a separate, audited collector deployment.

## G2.14 completed Acer pilot evidence and G2.15 offline review gate (2026-10-11 AST)

**Actual OWNER terminal output** from the exact G2.14 staging SHA `bc00ac52ef217a45883544befa6914f5f7c7a20d` confirms normal pilot termination: 15/15 scheduled TCP connects `tcp-open`, 0 refused/timeouts/failures, 0 skipped 60-second slots. Source Acer `firelion-Aspire-A315-51`, literal target V79-owned server `192.168.100.163:443`, 900-second window. Connection durations in ms: `3, 7, 6, 4, 5, 6, 5, 6, 6, 4, 6, 8, 5, 2, 3` (mean `5.1ms`, min `2ms`, max `8ms`). The log ends with `Pilot ended. No more probes authorized.` and `PILOT EXECUTION COMPLETE`, and reports `additionalProbesAuthorized:false`, `continuousMonitoringEnabled:false`, `tlsOrHttpVerified:false`, `independentlyAuthenticatedCollector:false`, `trustedForExecutiveUse:false`, `productionReady:false`.

**Not established:** any service availability between sampled TCP connections, WAN/customer reachability, TLS certificate authenticity, HTTP application response, physical network device inventory, production SLA, cryptographic attribution of terminal log, signed collector transport, or NOC monitoring. The user already consumed the specific time-limited permission. **No repeat or other active network check** without new user authorization. The Enterprise NOC last responded on loopback 8788 with `collector:simulated-only`, `integrations:disabled`; do not silently reinterpret this separate witnessed pilot as an active NOC collector.

**G2.15 offline evidence-consistency gate:** Added pure `integrations/sentinel/pilot_session_review.py` and synthetic tests. The reviewer checks exact 900-second/15-slot/60-second scope, one target/port, sequential samples, per-outcome totals and arithmetic mean and refuses extra authorization/collector-trust claims. It does **not** make connections or read/write files and emits aggregate non-identifying counts only. Critically, matching a user-pasted report's arithmetic is **NOT independent timestamp/cadence verification or source authentication**, so return values hardcode `sampleCadenceIndependentlyVerified:false`, `serverIdentityVerified:false`, `httpTlsVerified:false`, `signedTelemetryVerified:false`, `collectorActiveVerified:false`, `ongoingMonitoringAuthorized:false`, `trustedForExecutiveUse:false`, `productionReady:false`. CI tests use user-shaped fixtures but cannot prove original network observations. Keep PR draft/unmerged and do not deploy a real collector or Hub ingestion.

**Next product engineering choices:** review actual local NOC/NetPulse mission UI and add a deliberately separate `operator-reported pilot evidence` visual only after privacy/security review; create a distinct authenticated Edge service if and when renewed owner scope plus independent technical security gates permit continuing pilot monitoring. The most useful customer launch work remains Hub/Tiquet auth/onboarding, release parity, payment-provider KYC and independent security acceptance, not repeated synthetic evidence work.

## G2.16 — unified Command Center evidence preview, source truth boundary (2026-10-11 AST)

Owner has authorized continuation after the completed Acer network pilot. A standalone self-contained **offline HTML Command Center visual review** has been generated for user review; it is not installed into NOC 8788 and never sends network requests. This is a design preview for a future **single native Command Center** experience, not an embedded second application. Its evidence timeline contains 15 owner-witnessed historical TCP opens (mean 5.1ms, minimum 2, maximum 8) and labels them *operator-reported*. Seven Mission Control service statuses are marked *reported-only*, not independently verified physical devices. Collector card prominently states *simulated only*, consistent with actual Acer `GET http://127.0.0.1:8788/readyz` HTTP 200, `collector:simulated-only`, `integrations:disabled`.

New pure, offline TypeScript presenter `agent-service/src/sentinel-evidence-presentation.ts` provides the future UI's fail-closed view model. It accepts a strictly bounded readiness claim, a sanitized manual TCP pilot summary and an optional count of reported local services. Its outputs never include raw addresses, customer names, credentials or host endpoints; it explicitly distinguishes reported services from verified devices, historical one-time checks from continuous monitoring, simulation from unauthenticated `live` claims, and unknown data from a clean bill of health. All input states produce `verifiedEdgeCollectors:0`, `continuousMonitoringVerified:false`, `trustedForExecutiveUse:false`, `tcpPilotIdentityVerified:false` and `customerReady:false`. **Even a self-report that the collector is `live` is rendered `Self-reported; unverified`.** No keys, API routes, polling, live monitoring, network probes or customer-facing privileges were added. Eight isolated adversarial TS tests validate privacy and fail-shut labels.

**Limits of this deliverable:** a type-checked Hub-side presentation policy plus an offline mockup; the real Enterprise NOC source runs on the Acer and its Github remote is not accessible from the current connected repositories, while Remote Desktop Commander access is exhausted. Do not claim the actual Command Center charts/features have been upgraded on the Acer. The concrete next NOC step is an approved **local source review/port of the visual UI**, preserving every existing chart and the NetPulse analyzer, followed by screenshots/browser QA and supervised release. Keep the Enterprise NOC's collector disabled until separately authenticated Edge-source transport, signed fresh evidence, tenant scoping, credential custody and independent security acceptance are verified.

**Separate Hub/Tiquet launch track (do not conflate with Sentinel G2):** Hub issue #113 and P0 issue #117 show independent source-merge/release-parity, supervised founder MFA/SSO/mobile acceptance, WiPay provider/KYC, operator-verified manual bank settlements, supported account terms and legal/privacy/refunds still gating commercial activation. Draft Hub PR #116 manual payment, Hub PR #119 machine grants and Tiquet PR #29 signed Sentinel-ingress must NOT be merged in isolation, and Sentinel automation must NOT be allowed to create tickets in existing tenant workspaces without fresh exact-scope owner approval. Prior source docs mention older blocker states later remediated; use the latest dated independent evidence before a release go/no-go.
