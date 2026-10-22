# V79 P1 — Isolated coordinated Hub/Tiquet session binding (18 October 2026)

**Draft source only. No merge, deployment, payment changes, production environment updates, or external beta.**

## Exact candidate lineage
Hub base: `df1046151a02dd27db746a2ec5b928f03dcb9b1d`.
Tiquet base: `7da53ebb71530366168bd72a7efd52b57d34a23c`.
Paired Tiquet draft PR #44 source: `775d9f6c9afae70760896f5ef5cf090272d6a2af`.

## Three architectures / REDTEAM

1. Browser cross-origin logout calls: unreliable with absent tabs, rejected.
2. Asynchronous durable signed revocation fanout: eventual delivery requires a new delivery journal, retry worker, schema and observable failure handling. Strong longer-term option, but expanded blast radius.
3. **Selected narrow prototype:** exact parent Hub session status, authenticated by product HMAC. Existing Hub server persists hashes of session tokens across restarts; signed one-use Tiquet launch ticket now binds that hash. After Hub removes the session, every bound Tiquet HTTP request checks Hub directly with no positive cache, and bound staff WS rechecks during existing heartbeat. This closes previously observed Hub-only logout gap in isolated execution without a new database migration.

### Flags (both OFF by default)

- Hub `V79_HUB_TIQUET_SESSION_BINDING=1`.
- Tiquet `V79_TIQUET_SESSION_BINDING_ENABLED=1`, requires `V79_ENTITLEMENT_RECHECK_ENABLED=1`.
- **Both** sources must be tested and ultimately rolled together; mixed configuration can lock users out or leave older sessions unbound. Existing unbound JWTs are denied under enabled Tiquet flag.
- Do not set flags on live infrastructure during development.

### Behavioral boundaries

- Exact Hub session ID is a SHA-256 reference, not the raw bearer/cookie; only Tiquet receives it via an authenticated service request.
- Tiquet HMAC status request includes exact scoped Hub identity, organization and product. Wrong service/signature, absent session, expired session, wrong tenant/member or Hub timeout deny.
- A ticket minted before Hub logout cannot be consumed after that session ends. A still-active separate session/tenant remains valid.
- Existing explicit Tiquet logout token fingerprint denial remains intact.
- Staff WS rechecks bound Hub session at handshake and heartbeat; customer portal scoped links use their independent mechanism and are not asserted to be globally signed out.

### Serious /REDTEAM release issues

- **Hub dependency and load:** every Tiquet authenticated HTTP request invokes a signed Hub check, up to 3.5s timeout. Offline Hub means Tiquet fail closed. Test realistic rates, timeout, resource use on 4-core/8-GB server; consider durable back-channel and bounded fail-closed local state before production.
- **Network race:** an already-authorized Tiquet HTTP request may finish just after logout; there is no global transactional boundary across products. WebSocket revocation is bounded by heartbeat, not instantaneous.
- **Session migration:** older Tiquet JWT lacks parent ID; rollout intentionally denies it. Document and test planned user re-authentication, rollback, stale-cookie handling and mixed-version failure.
- **Durability:** Hub deletion persists session map; independent encrypted restored-stack and multi-worker restart tests required; protected status identity must not leak session IDs in logs.
- **Release authority:** despite test pass, live OCI/Compose source mapping, SSO staging verified flags, backups, rollback, and independent security review remain outstanding.

## Test gates

- Tiquet PR #44 runs pure signed-client, HTTP middleware, staff socket/heartbeat unit checks and existing suites with flag default OFF.
- This Hub draft runs real isolated Hub and Tiquet candidates with two wholly synthetic tenants plus Postgres 16, flags ON: replay, cross-tenant reads/writes, existing JWT rejection after parent Hub logout, separate-tenant access intact, and explicit Tiquet logout.
- No production network, no customers, no secrets and no service deployment.

**Customer paid/live rollout: NO-GO.** Approval to merge/deploy and enable session binding must be obtained separately.
