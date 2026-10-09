# V79 AI Workforce — Dedicated disposable staging VM acceptance plan

**9 October 2026 · Founder authorised the staging VM approach · DOCUMENT ONLY · NO VM PROVISIONED**

## Current state and execution boundaries

The separate development PRs are [Hub #103](https://github.com/MrFixITslu/V79hub/pull/103) at `fac95979408d8aefb5e72c2356adfa013da9d6c9` and [Tiquet #21](https://github.com/MrFixITslu/V79Tiquet/pull/21) at `63dd5f0028db899c88202a31d5835def639c728f`. Keep both draft and unmerged; their `main` branches may deploy automatically. The last isolated Tiquet-to-pinned-Hub signer test passed with ephemeral PostgreSQL/key but the **real running Hub+Tiquet MFA staging test remains unexecuted**. Previous attempts to launch full staging and change its CI workflow were blocked by execution safety checks. **Do not route around these controls**.

The founder approved using a dedicated VM; it does not imply a provider account is connected, that cloud charges are authorised without a price cap, that production data/credentials may be copied, or that a production merge/deploy may occur.

## Proposed isolated topology (subject to connected provider and approved cost)

```text
Founder ChatGPT                 V79 production server (NO CHANGES)
       |
       | authorises test VM
       v
Disposable VM / cloud account (NO link to production Tailscale/LAN)
  inbound: management from owner-controlled IP only (or no public inbound)
  outbound: package/GitHub endpoints for initial build, then deny outbound app traffic
  volumes: disposable only; no production mounts, domains or credentials
  Docker network: private internal test network, no public app ports
      |
      +-- PostgreSQL 16/17 (synthetic isolated DB)
      +-- V79Tiquet PR #21 (read-only source signing, staged private key)
      +-- V79hub PR #103 (MFA + owner approval inbox, source public key)
      +-- Egress/no-write observation + HTTP/MFA probe
      +-- Temporary runner logs and redacted pass/fail summary
```

**Minimum starting capacity for estimate:** around 2 vCPU, 4 GiB RAM and 50–60 GiB disposable SSD; size is a target for quoting, not a provider price/availability guarantee. Avoid production resource contention. Provision a brand-new disposable VM; do not install packages, Docker or test containers on `v79sl`. Limit the VM lifetime to the test window. Do not expose Postgres, Hub or Tiquet publicly.

## Prerequisites: fail closed until all can be verified

- Explicit provider connection, a billable VM account, a confirmed maximum budget and a deletion window. A provider plugin/connector suggestion does **not** mean it has been connected.
- The cloud tool must actually support creation, shell/test execution, firewall controls and VM destruction. A plugin advertised for a specialised workspace is not proof it grants a general-purpose VM or network control.
- Exact GitHub feature branch/commit inputs; no production `.env`, deployment SSH key, customer account, OAuth token, billing/Resend/API secret, Tailscale production enrolment or backup import.
- VM has its **own** temporary service HMAC secret, Hub admin password, TOTP seed and app-specific Ed25519 key pair generated inside the disposable environment, never committed, emailed or copied to a chat.
- An execution route explicitly permitted by available safety controls; do **not** reissue previously blocked GitHub workflow edits or blocked full-stage launch under another executor.
- A disposable database with only synthetic tenants. No production data needed.
- All app egress blocked/detected during plan creation/approval; allow only explicit read-only Hub-to-Tiquet requests and test-controlled mocks; no billing, email, social posting or downstream writes.

## Acceptance checks (must be evidenced by logs, not assertions of completion)

1. Verify guest OS/VM identity, tenant/account, firewall, absence of production mounts and app destinations; run startup and read-only health checks.
2. Run the actual Hub and Tiquet applications (not only imported verifier functions) from pinned draft commits. Authenticate founder test account through genuine password + mandatory TOTP; verify unauthenticated, incorrect/expired TOTP and password-only sessions cannot access approvals or source verification.
3. Hub `GET /api/agent/sources/tiquet/metrics` asks Tiquet's actual signed endpoint using a fresh signed request ID/HMAC; verify only five aggregate counters, signed tenant/nonce, source observation/expiry and disabled execution.
4. Wrong organisation, forged/expired signature, wrong/retired public key, invalid nonce, altered metric, unknown tenant, non-JSON/large/redirect response all fail closed with **unavailable**, not false zero.
5. Create and approve/reject *synthetic decision-only* Phase 3A proposals through a verified MFA session. Observe there is **no outbound write** to any app, marketing, billing, email or other service. Replayed/stale/expired proposals and cross-tenant attempts fail closed.
6. Reload a disposable Hub instance; verify audit HMAC linkage, the checkpoint and state revision. Demonstrate independent retention on a genuinely separate operator-controlled immutable/versioned store; a local file vault helper by itself does **not** satisfy this.
7. Repeat through separate Hub writer instances in an authorised isolation setup and verify one-winner revisions/rollback. Existing PR-only PostgreSQL race job verifies a narrower concurrency contract but not a full multi-container system.
8. Review the actual browser UI: Owner Assistant shows limited, expiring Tiquet metrics and clearly distinguishes `source_signed` from `proxy_attested` or `unverified`. Confirm no agent-execution control exists.
9. Record redacted test counts, run IDs/commit SHAs, safety and cleanup evidence. Destroy the VM and all ephemeral volumes/keys when complete. Check cloud console that no billable VM, disk or public IP remains.

**Release requires:** authenticated test evidence, independent audit retention/keys/rollback review and a separate founder confirmation for a precisely named production release. The approved staging VM approach does not authorise production changes.

## Offline preflight added (no cloud side effects)

Run `node --test tests/agent-staging-preflight.test.mjs` to validate the manifest policy helper. The exported `validateIsolatedAgentStagingPlan(plan)` in `scripts/agent-staging-preflight.mjs` evaluates a proposed VM manifest in memory; it **does not** create a VM, connect to any host, read secrets, launch test services, or authorise a previously blocked workflow.

All boolean isolation guarantees must be attested explicitly by a permitted operator. The manifest must provide two exact commit SHAs, private staging hostnames, a named provider, an independently approved USD cost ceiling, a deletion deadline within 48 hours, and test-only keys/data. Local output must stay inside `/tmp/v79-agent-stage-*`. Paths, credentials, endpoints and commands pointing toward the production Hub or LAN are rejected. This syntactic validator is an additional **precondition only**: it cannot verify cloud firewall implementation, billing authorisation, anti-rollback protections or immutable audit storage. Each requires independent provider evidence before the full staging work can begin.

The Phase 3A PR remains **draft**; this helper must not be used to bypass execution safety controls or to merge/deploy any live code.
