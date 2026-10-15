# MCP read-only protected route — current G3 tracking candidate (DRAFT / NO-GO)

## Exact scope

- Base: Hub `feature/marketing-production-20261014` at `ffae1c104d6ded918a0028f92c76624bc0501d8b`. This branch is a descendant of accepted application source `045d68a61257c758f2f6ca229d050e4e7a7df618`; the additional base commits are G3 build/cutover/recovery tooling, not changes to deployed application source.
- The earlier MCP/G3-UI branch `feature/mcp-owner-readonly-g3-ui-20261015` forked at `8d82b21` and was 15 commits behind the accepted application source. Do not deploy it.
- This candidate copies only the reviewed `server/mcp-owner-readonly.mjs` and its negative tests and inserts the original gated route/import into `server.ts`. The *entire* Hub server source recovers byte-for-byte to `ffae1c104d6ded918a0028f92c76624bc0501d8b:server.ts` after removing that insertion.
- The route `/api/integrations/mcp/v1/apps` is **disabled by default**; `V79_MCP_READONLY_ENABLE=1` is neither set nor authorized here. No production credentials, downstream signer, customer data or MCP listener are introduced.
- This branch changes no application defaults, deployed images, Compose overlays, payment, tenant records or Tiquet.

## Automated proof (branch-local, validation only)

Workflow `mcp-g3-tracking-readonly-contract.yml` pins the base commit, allows only five reviewed paths, reconstructs the exact base `server.ts`, executes the MCP authorization-negative and legacy organization/agent tests, full Hub lint/typecheck, and existing G3 panel/approval regression tests. No publish or deploy job, no credentials, no push to main.

Test outcomes must be read from the *actual* branch CI run before claiming PASS. A new branch head requires renewed review. Do not infer actual OAuth/consent/tenant integration, an authenticated owner end-to-end request, or current runtime parity from tests.

## Mandatory before any production consideration

1. Re-inventory the accepted production Hub image/source and every ordered Compose overlay, verify immutable pre-change rollback image and encrypted backups plus a genuinely isolated compatible restore. No old eight-layer assumption.
2. Independent exact-head review: assertion trust model, owner-MFA delegation, consent and tenant entitlement mapping, JWT issuer/audience/keys, revocation, replay, logging, rate limits and egress.
3. Implement a compliant external MCP OAuth protected resource/authorization service and separately trusted narrow downstream Hub token issuer. Never pass an MCP inbound bearer token as the Hub assertion or reuse live Hub login/platform credentials.
4. Prove an isolated synthetic owner-approved end-to-end flow plus separate live browser MFA/SSO/WiPay/G3 acceptance and a pinned single-service rollback. No customer data or production auth-bypass testing.
5. Respect existing main-only approved-SHA workflow, branch-only development guardrail, formal founder/independent review and separate exact release approval. **No merge, deployment, activation or actual private read is authorized here.**

Reference: https://github.com/MrFixITslu/V79hub/issues/147 and https://github.com/MrFixITslu/V79-MCP/issues/2.
