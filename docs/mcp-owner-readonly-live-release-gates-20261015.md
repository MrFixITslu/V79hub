# V79 Hub — MCP owner read-only integration candidate (NOT DEPLOYED)

Owner conditional authorization: 2026-10-15, to PREPARE the limited read-only MCP authentication/API integration and deploy only AFTER security review plus proven rollback. Production Hub and Tiquet must not be modified merely because source tests pass. Feature-branch-only. No main merge or production rollout until remaining gates.

## Code and scope
- Candidate feature branch: feature/mcp-owner-readonly-api-20261015.
- Branch source base observed: b450db70ece047f74aa502bca862a870e5d74c00 (GitHub main); NOT verified as the running production Hub source/image.
- New server/mcp-owner-readonly.mjs.
- New GET-only route declared in server.ts: /api/integrations/mcp/v1/apps.
- V79_MCP_READONLY_ENABLE must be exactly 1; missing/other disables the endpoint with 404. Do NOT enable it before all gates pass.
- No browser sessions, launch tickets, platform shared HMAC, POS JWT/JWKS or inbound MCP bearer tokens authenticate this route.
- Route accepts only a separately-issued short-lived RSA-signed downstream assertion whose EXACT audience is v79-hub-mcp-readonly, whose client is v79-mcp-internal, with scope hub.apps.read, authorized owner organization/user, CEO or COO agent, and signed recent MFA proof (acr=urn:v79:mfa and auth_time within 900 seconds).
- Assertion header kid and signature are checked against an exact operator-pinned RSA public key. Max lifetime 120 seconds. Expiration enforced.
- This is an INTERNAL downstream assertion contract; it is not a complete OAuth 2.1 issuer/resource server and cannot replace MCP's inbound OAuth discovery/authorization requirements.
- Re-evaluates Hub active owner membership and organization plan/app entitlements on EVERY successful read.
- Output is only a bounded array of authorized app IDs and names. No ticket, financial, user, private/customer records, or write endpoints.
- Safe responses set Cache-Control no-store. Unknown/disabled identities fail closed.
- Source compiled or CI-tested is NOT equivalent to a verified runtime deployment.

## Required environment variables (never commit values or print them in logs)
- V79_MCP_READONLY_ENABLE: unset or 0 until release gate.
- V79_MCP_DOWNSTREAM_ISSUER: exact separately reviewed trusted downstream credential issuer.
- V79_MCP_DOWNSTREAM_KEY_ID: exact key identifier.
- V79_MCP_DOWNSTREAM_PUBLIC_KEY_PEM: trusted RSA public key, never a model-provided or token-header-loaded key.

No sensitive values, tokens, keys or production database contents are included in this branch.

## Security review: outstanding high-priority blockers
- REAL OAuth authorization server and MCP protected resource metadata are NOT implemented/deployed. The candidate verifier does not mint tokens.
- An independently authenticated MFA step-up and agent delegation consent must precede issuance of the approved downstream assertion. The assertion must NEVER simply copy a client bearer token.
- Trusted issuer key lifecycle, revocation and rotation need independent review. Token lifetime is short but this is not immediate server-side revocation.
- The app list's display names can be user-authored: classify them as untrusted text to any model.
- Rate limits, upstream egress policy, durable audit events and abuse monitoring require deployment-level review.
- No independent third-party security review, authorized live protected request, or real-tenant isolation penetration test.
- The *GitHub main source and the actual running container image/digest have NOT been proven identical*; existing V79 Hub history includes release provenance discrepancies. Treat this as a HARD blocker for deployment.

## CI and test evidence
- Initial 26 new Hub tests plus 6 regression tests passed; subsequent MFA-hardening generated a verified run at commit cd80f006fe6ff1ffb63f5ff3f1ba8360435367e7 with 27/27 focused tests and 6/6 existing access tests.
- Hub security CI URL: https://github.com/MrFixITslu/V79hub/actions/runs/38710047054
- A later workflow adds npm ci and a full TypeScript no-emit lint/typecheck. Check actual GitHub run conclusion before treating this gate as cleared.
- Failed intermediate runs are retained in CI history; they must not be presented as passing.

## Rollback and release rehearsal — required before enabling
1. Read-only: capture running Hub container ID, pinned image digest, source commit/build provenance, health, active compose path and deployment inputs WITHOUT exposing secrets. Compare against reviewed feature commit and exact runtime source.
2. Verify successful encrypted backups, independently stored key access, and isolated restore rehearsals for currently running Hub data and databases. Preserve original backed-up artifacts and manifests.
3. Confirm the pinned PRE-CHANGE running image is present and recoverable. Prepare the exact existing Compose file/image rollback procedure and validate it away from production. Do not use broad Docker prune, compose down -v, volume deletion, or drop databases.
4. Obtain independent security review of exact candidate source/diff; resolve critical/high issues and verify approval authority.
5. Schedule a controlled window and deploy the exact reviewed image with MCP feature DISABLED first. Revalidate Hub login, MFA, Tiquet launch, WiPay sandbox/manually approved billing flows and app health.
6. If all safety gates pass, use a dedicated service identity and short-lived downstream assertion to test ONLY synthetic/owner-authorized app-list projection. Do not transmit production tokens in CI.
7. Emergency rollback: disable MCP feature/route access and restore the previously pinned image using the approved existing deployment path; verify container health, auth, app launch and data integrity. Keep evidence of the exact old/new image digests.
8. Do not promote or merge either repository to main under this approval.

## GO/NO-GO
GO: branch-only development, isolated tests, public health monitoring.
NO-GO: deployment, enabling live protected endpoint, customer read/write permissions, external ChatGPT connection, autonomous actions — until all gates above have actual evidence.
