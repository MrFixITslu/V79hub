# V79 P1 — Hub logout vs Tiquet session lifecycle (18 October 2026)

**Status: evidence-only draft; no authentication implementation or customer release.**

## Exact source reconciled

Hub `main`: `df1046151a02dd27db746a2ec5b928f03dcb9b1d`.
Tiquet `main`: `7da53ebb71530366168bd72a7efd52b57d34a23c`.
Paired full-stack base: draft Hub PR #177 `103d8eeccff4076912b8dfdeae61e12ea29325c4`.

### Observed source contract

- Hub `POST /api/auth/logout` deletes only the Hub session token, clearing its cookie.
- Hub frontend `src/App.tsx` clears local state even when logout request fails; it does not call Tiquet logout.
- Hub's managed signed launch ticket currently stores only `userId`, `tenantId`, `product`, `expiresAt` (no parent Hub session identity).
- Tiquet `/api/platform/launch` exchanges the one-use ticket for its own 30-minute JWT and `tiquet_session` cookie, containing Tiquet user/account and Hub organization mapping, but **no Hub browser-session binding**.
- Tiquet `/api/auth/logout` writes a hash of the submitted Tiquet JWT into `revoked_auth_tokens` and clears that app's cookie. It cannot revoke an unsubmitted token during Hub-only logout.
- Tiquet's entitlement checks revalidate org/user access, not whether the *original Hub browser session* is still alive. Hub logout alone is therefore not a reliable global single logout.

## Three approaches; REDTEAM decision

1. **Browser/front-channel fanout:** invoke logout on every app tab/origin from Hub. Rejected as security enforcement: cookies, CORS/CSRF, offline tabs and failed network requests make this unreliable; browser can suppress failures.
2. **Hub introspection on every Tiquet HTTP request and WS heartbeat:** secure if current session is bound, but adds network/database dependencies on every request and depends on an as-yet-unimplemented session reference.
3. **Preferred staged design: session-scoped durable back-channel invalidation plus fail-closed revalidation.** Bind a stable opaque Hub session reference to signed launch tickets, issue Tiquet sessions against it, and authenticate a scoped revocation notice from Hub to Tiquet on logout. Tiquet records revocation durably and denies tokens/sockets linked to that session, including across workers and restarts. A bounded authenticated Hub session-state check (or revocation version) is needed to close partial-delivery windows, with safe retry and transparent partial-failure UX.

### /REDTEAM before implementation

- **Scope:** A logout must revoke *the selected Hub login session only*; not unrelated organizations, users or other devices unless a separate "log out everywhere" choice is made.
- **Signing:** Use existing signed HMAC platform transport with timestamp, nonce/replay protection, exact audience and path; never share JWTs between Hub and Tiquet or place raw tokens in audit/logs.
- **Durability:** Persist session lineage and revocation state before acknowledging global logout; verify multi-worker and restart behavior; require independent migration and rollback rehearsal.
- **Partial failures:** If Tiquet cannot be reached, do not claim all apps logged out. Revoke Hub session locally, queue retry within explicit bounds, and show an honest partial-logout warning. UI currently suppresses errors and would need controlled change.
- **Race:** Concurrent launch and logout must serialize/deny new launch; revoke sessions minted before/during request. Reject late or replayed revocation and ensure timestamps cannot resurrect sessions.
- **WebSockets:** Staff sockets must close/unsubscribe on revocation with bounded heartbeat latency; portal-token access follows its separate portal link policy.
- **Blast radius:** Do not touch WiPay, MFA, customer billing, agents, test accounts, deployment, or standing services. Existing SSO and tenant behavior must remain unchanged.
- **Operational reality:** On-premises server is capacity-constrained; avoid unbounded per-request network calls, large caches or background services without reliability/performance testing.

## Current-source diagnostic

`tests/paired-hub-tiquet-current-security.test.mjs` performs actual disposable Hub logout after customer A's signed Tiquet login, confirms A's old Hub cookie and launch are rejected, probes old Tiquet cookie and Bearer JWT, and confirms tenant B remains unaffected. It prints only HTTP status codes and:

- `HUB_ONLY_GLOBAL_LOGOUT_GATE=NO_GO_TIQUET_TOKEN_SURVIVES` when cross-app single logout is not enforced.
- `HUB_ONLY_GLOBAL_LOGOUT_GATE=CANDIDATE_PASS_REQUIRES_INDEPENDENT_REVIEW` otherwise.

**Important:** This is diagnostic classification, NOT proof that the customer release gate passed. Source-only positive and negative tests do not establish live-image identity or installed runtime behavior. The full future global logout security gate must explicitly require both previously issued Tiquet tokens to be rejected, plus staff WS and multi-worker tests.

## Remaining release decisions

Do not implement, merge or deploy cross-app session changes until the exact installed runtime/recovery has been reconciled and the session-scoped protocol is independently reviewed. No Tiquet or Hub production authentication code is changed in this PR. Customer launch remains **NO-GO**.
