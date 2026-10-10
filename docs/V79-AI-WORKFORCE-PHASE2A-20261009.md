# V79 AI Workforce — Phase 2A: signed-summary evidence ledger

**Status:** Draft code; production unchanged until approved. Depends on the deployed Phase 1 specialist routing in Hub.

## What is actually integrated

The Hub's existing `/internal/agent/snapshot` owner-agent endpoint reads product metrics through its service-to-service, HMAC-signed, GET-only summary contracts and restricted platform admin-stats contracts. The agent does **not** connect directly to product databases or arbitrary external URLs.

This change normalises those existing signed data feeds into an **owner-scoped, read-only evidence ledger** for each specialist. It validates the returned Hub snapshot owner email, organisation and collection timestamp against the authenticated Hub owner context, then only includes explicitly allowlisted aggregate numeric metrics. Values such as customer details, free-form text, credentials and arbitrary new API fields are excluded from model inputs and the UI.

The ledgers contain system name, whether product HTTP health was online, provenance (`signed_product_summary`, `signed_platform_admin_stats` or `hub_owner_summary`), `collectedAt`, `reportedAt`, age when known, evidence status, and bounded approved numeric metrics. A metric is **fresh** only if its product-reported timestamp is valid and no more than 15 minutes old. Future-dated, stale, missing, misconfigured and undated metrics are **not** treated as fresh facts. In particular, Hub's fallback `generatedAt` timestamp is distinct from the product's `sourceReportedAt`. The platform admin-stats endpoint currently lacks a product-reported measurement time; its metrics are labelled **unknown freshness**, not fresh.

## How it appears to the owner

The Owner Assistant retains the Phase 1 six specialist shortcuts, sends evidence-only model context (regardless of local or cloud provider), and returns an `evidence` object alongside its answer. The chat displays a collapsible "Verified data sources" explanation, showing the service, source type, reported time, available aggregate values and unavailable/stale statuses. The existing deterministic KPI responses are fed by fresh, reviewed source values only. In particular, missing POS sales, Marketing campaigns or CombatZone bookings are never silently interpreted as zero.

The internal `POST /api/agent/evidence` API is token-guarded and validates founder owner context; it serves one specialist's ledger without invoking a language model. This endpoint is **not exposed as a new public URL**.

## Security and operational boundaries

- Existing public Hub owner-only session + MFA and the internal agent service-token gates are unchanged.
- The Hub signature verification for products and read-only admin endpoint allowlists remain the source of trust. No secret, payment token, raw database or arbitrary app URL goes to the model.
- App integration errors are explicit; no invented values and no cross-specialist metric access.
- Signed owner-envelope scope and timestamps are validated again in the agent process, before ledger construction.
- Both the Ollama local path and the optional OpenAI model path use the same evidence-only context. The Agents SDK `get_business_snapshot` tool also returns redacted evidence records, rather than the raw snapshot.
- Data is fetched on demand from existing read-only endpoints with bounded timeouts; no periodic polling, email sends, bookings, payment changes, deployments, user provisioning or new autonomous tools are introduced.
- Evidence is an audit aid, not a cryptographic proof in the browser. Upstream accuracy is limited to what each product reports.

## Verification requirements

1. Agent and Hub lint, automated tests and production frontend build must pass.
2. Signed summary source presence/absence, timestamp freshness and owner organisation mismatch must be tested.
3. Test the actual agent-service API against a fake Hub server with an internal token; confirm 401 without token, 403 non-owner, 502 mismatched Hub ownership, and only allowlisted fields in successful results.
4. CI on the exact feature SHA must pass, with image publishing/deployment skipped for the draft PR.
5. Before production cutover: verify safe Hub and agent rollback images, a fresh Hub DB backup, disposable staging and founder acceptance of Finance, Growth, Customer Care, Technology, Operations and CombatZone evidence displays.
6. After production approval: all six apps remain healthy; confirm owner-only access, source labels, missing-data honesty, unchanged beta entitlements, trial end, MFA and billing gate.

## Known limitations and further work

This is Phase **2A**, based on the Hub's *existing* signed read-only app summaries. Additional product-specific read-only adapters, detailed ticket/inventory investigation, data-source contracts, rate limits, source freshness service-level objectives, idempotent evidence caching and cross-app provenance reconciliation remain open in [Stage 2 issue #99](https://github.com/MrFixITslu/V79hub/issues/99). Cross-tenant customer-agent access is not enabled.

Write-capable agents remain prohibited pending the separately approved human approval inbox in [issue #100](https://github.com/MrFixITslu/V79hub/issues/100). Ollama structured tool-calling quality remains [issue #97](https://github.com/MrFixITslu/V79hub/issues/97) and is not needed for this phase.
