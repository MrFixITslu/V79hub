# V79 AI Workforce — Phase 2C read-only adapter contract (design, not enabled)

**Date:** 2026-10-09 · **Status:** development specification only · **Release gate:** separate PR and founder acceptance.

## Hard boundaries
- Keep Phase 2B deployed, aggregate-only adapters unchanged until Phase 2C has independent review.
- New contract is **GET/read-only**, bounded and tenant-scoped; no credential, arbitrary URL, SQL, email dispatch, ticket mutation, payment, booking, publishing, user provisioning, or deploy functions.
- A signed service identity is not by itself authority to view every organisation. Resolve founder, role, permission and organisation **server-side** before every read.
- The model receives only the minimum schema-validated, approved facts. Never pass through raw upstream text or an instruction embedded in a business record as a tool directive.
- Use only mock/synthetic data for tests. No customer data or live beta credentials in test fixtures.

## Proposed response envelope (not implemented)
```json
{
  "version": "2c-draft-1",
  "requestId": "uuid",
  "source": "tiquet",
  "observedAt": "RFC3339 UTC",
  "expiresAt": "RFC3339 UTC",
  "available": true,
  "partial": false,
  "data": {
    "openCount": 4,
    "overdueCount": 1,
    "oldestAgeHoursBucket": "24-48"
  },
  "warnings": []
}
```
The example contains **illustrative synthetic values only**. Identity and tenant identifiers stay in authenticated server context or secure logs; never model context. For outages, return `available:false`, `data:null` and a bounded error code (not raw errors). Unknown is distinct from zero.

## Initial allowed data (proposal, pending app-owner sign-off)
| Adapter | Fields permitted in first pilot | Explicitly excluded |
|---|---|---|
| Tiquet | Open/overdue counts, anonymised SLA age buckets, aggregate MTTR | Ticket body, contact details, attachment, outbound reply |
| POS | Low-stock counts and replenishment category counts | Purchases, suppliers' banking data, raw orders |
| FFPRO | Aggregated planned-vs-actual category deltas, cashflow indicators | Bank account identifiers, individual transactions, payment instruments |
| Marketing | Draft/published campaign counts, aggregate delivery metrics | Contact lists, message content, publishing tokens |
| Academy | Course counts, aggregate enrolment/completion rates | Student identities, assessment answers |
| Hub | Health, entitlement counts and coarse audit health | Session tokens, admin password, MFA secrets, subscription changes |
No customer-specific item or document content is approved by this contract. Item-level drilldown requires its own documented privacy review and separate approval.

## Request validation
1. Use server-side fixed allowlist for app ID, route, method, output schema and field names. Never interpolate user/model-provided URLs.
2. Verify signed caller and owner role; bind organisation from authenticated session, not request text.
3. Enforce per-adapter rate and concurrency limits, body/response size caps, 5–10s bounded timeout, and freshness budgets by source.
4. Treat upstream 404/timeout/invalid signature/malformed schema as `available:false`. Do not fabricate replacements.
5. Tag each result with source, UTC observation time, expiry and requestId; redact identifiers and secrets from model traces.
6. Log metadata to durable protected audit storage. Do not reuse the Phase 3 capped 5,000-event array as the only audit trail.
7. Expose capability as **unavailable** if app permission, source freshness or signed transport cannot be verified.
8. Never let an investigation, source text, or model response create approval or activate an action.

## Required test matrix
- Invalid signature, unknown adapter/route, missing/expired session, non-owner, wrong organisation, cross-tenant UUID probing.
- Missing metric, zero metric, stale metric, partial upstream payload, non-JSON, extra fields, oversized response, timeout, rate limit, upstream 5xx.
- Strings containing prompt injection, spoofed instructions, credentials, Unicode obfuscation, contact details and account identifiers; ensure they never reach model context.
- Parallel requests, retry storms, disabled downstream service, network egress allowlist, method restrictions and **proof of zero writes**.
- Regression: deterministic specialist router works when Ollama returns no `tool_calls`, malformed `tool_calls`, or times out.
- Founder UI shows source/freshness/uncertainty and separates investigative recommendation from permission to act.

## Dependencies and decisions
- Issue #99 tracks Phase 2C; #97 tracks model tool-call reliability; #100 tracks Phase 3 decision-only inbox.
- Before coding app-specific pilots, obtain approved field lists and privacy classifications for each application. Until then remain aggregate-only.
- No production deployment, billing, customer outreach, write-capable tools, or autonomous actions without independent release gates and explicit founder approval.
