# V79 Ecosystem v2 — Five-role architecture decision review

**Date:** 11 November 2026 (Saint Lucia). **Status:** draft technical decision; no code merges or deployment approved.

> **Evidence integrity:** These are five separately articulated *role-based evaluations produced in this review* — COO, Technology, Finance, Sales and Marketing. They are **not** authenticated votes from five running V79 Hub agents. The available V79 evidence connector is read-only and cannot send work to those agents. Scores are recommendations, not historical agent ballots. A proposal is **recommended** only when at least 4 of the 5 roles support it.

## Three routes considered, and chosen route

1. **Adopt the critique verbatim:** fastest on paper, but invents new event names, duplicates Tiquet's Files capability, creates unnecessary services and risks privacy/accounting.
2. **Dismiss the critique:** lowest immediate change, but identity, replay recovery, cost/margin truth and real operational acceptance remain weak.
3. **Adopt only evidence-compatible changes (chosen):** preserve existing tested three-app integration; reconcile current live source; extend owned modules with versioned signed contracts and well-defined release gates.

**/REDTEAM before any code writes:** Source divergence across unmerged PRs; current live image SHA UNKNOWN; GDPR/privacy and Caribbean customer marketing consent; inadvertent cross-tenant access; loops or double-posting between independent finance ledgers; confusing payments with delivery acceptance; false confidence from CI-only tests; rollback safety. No cross-app business action may be inferred solely from a signed read-only event.

## Role-based recommendation matrix

Legend: Y = recommend, N = do not recommend. Order of roles: COO, Technology, Finance, Sales, Marketing.

| Recommendation | COO | Tech | Finance | Sales | Marketing | Support | Decision and scope |
|---|---|---|---|---|---|---|---|
| Reconcile live-source baselines, SSO/MFA and **tested restore/rollback** before production | Y | Y | Y | Y | Y | 5/5 | **KEEP · V2 launch blocker** |
| Publish actual event names, schema v1, stable subject/tenant/correlation IDs, bounded payloads; retry, duplicate and dead-letter observation | Y | Y | Y | Y | Y | 5/5 | **KEEP · V2 must-code**; avoid incompatible renames |
| Extend **Tiquet's existing Files** model with scope/proposal, document revision, signed approval, client portal permissions and retention | Y | Y | Y | Y | Y | 5/5 | **KEEP · V2 must-code**; do not start separate Files microservice |
| Real project costs: Tiquet labour/time + POS cost-of-stock + authorised expenses, invoice/payment reconciliation and Hub read model | Y | Y | Y | Y | Y | 5/5 | **KEEP · V2 must-code**; never substitute FFPRO projections for payment proof |
| Safe rejected/duplicate lead, cancelled ticket, settlement-in-flight and failed communications paths; compensate explicitly | Y | Y | Y | Y | Y | 5/5 | **KEEP · V2 must-code**; all payment exceptions human-reviewed |
| Distinct legend for contract written, CI verified, synthetic staged, live deployed, monitored | Y | Y | Y | Y | Y | 5/5 | **KEEP · immediate documentation** |
| Consent-aware Marketing→CRM attribution and CRM won/lost→Marketing suppression/update signal | Y | Y | N | Y | Y | 4/5 | **KEEP · V2.1 after core**; Finance objection: consent and scope risk |
| Academy completion→Hub verified, tenant-scoped learning outcome | Y | Y | N | Y | Y | 4/5 | **KEEP · V2.1**; learner consent/minimisation first |
| Sentinel alert→owner-reviewed Tiquet ticket; dedupe and recovery audit | Y | Y | Y | Y | N | 4/5 | **KEEP · V2.1**; builds on existing draft integration, no autonomous remediation |
| Build an independent Files/Knowledge microservice now | N | N | N | N | N | 0/5 | **REJECT** duplicate storage/auth/retention overhead |
| Auto-upload CRM customer lists to lookalike ads by default | N | N | N | N | Y | 1/5 | **REJECT**; violates consent-by-default, provider-policy and data-governance principles |
| Auto-recommend/send Academy offers from individual job outcomes | N | N | N | Y | Y | 2/5 | **DEFER**; optional customer-initiated recommendations only |
| Permit two-way writes between Tiquet and FFPRO/POS/Hub financial ledgers | N | N | N | N | N | 0/5 | **REJECT**; each ledger owns its entries, Hub is a projection |
| Rename tested `lead.created`/`job.created` events to `lead.signed`/`job.signed` with no migration | N | N | N | N | N | 0/5 | **REJECT**; new events only with versioned compatibility |

## Code truths checked before this decision

- **Already implemented in draft:** Hub ingress `input.version===1`, HMAC service-signature checking, tenant mapping and bounded category payloads; signed Website/Tiquet receipts and PostgreSQL duplicate key; Tiquet durable outbox/retries; the isolated three-app [run #43017926092](https://github.com/MrFixITslu/V79hub/actions/runs/43017926092) passed.
- **Already exists, not yet a document lifecycle:** Tiquet `files` table includes `jobId` and `account_id`; scoped proposal approval, revisions, contractual signatures, version hashes, retention and delivery evidence need independent validation.
- **Existing partial Sentinel integration:** Tiquet has `sentinel_incident_jobs`, `sentinel_ingest_events` and `sentinel_ticket_approvals` schema; end-to-end monitored production incident lifecycle is not proven.
- **Not proven:** real SSO/MFA and marketing consent across all apps, exact deployed source pins, live SMTP/WiPay, purchase costs allocated to jobs, time-to-job ledger, cross-app staff UI, and restored backups.
- **Schema naming:** use `lead.created`, `job.created`, `job.status_changed`, `payment.recorded`, `customer.feedback_submitted` where currently defined. Do not invent `job.signed` semantics.

## Data ownership rules

- **Hub:** tenant identity, membership, entitlement, signed read projections, event/correlation search and CEO dashboard. Never source-of-truth for transaction-level ledger truth.
- **Website CRM:** source lead, attribution and enquiry consent; staff qualification and approval.
- **Tiquet:** client service profile, jobs, time booked to job, service invoices, receipt evidence, acceptance and service documents. Same individual in Website CRM and Tiquet requires explicit mapping, not email/phone guesswork.
- **POS:** stock ledger, part reservations, stock movements, item cost layers and compensations. Each item-to-job allocation carries an exact job ID and a reviewed invoice-cost projection.
- **FFPRO:** budget/projection and its own financial records. Read-only correlated actual costs, not cross-writing payment transactions.
- **Marketing:** opt-in campaign/prospect state and provider evidence; never raw CRM export by default.
- **Academy:** learning records and learner consent; only minimal completion signal to Hub.
- **Sentinel:** monitoring observations and deduplicated incident evidence; no independent authority to close Tiquet tickets or remediate production.
- **MCP/automations:** owner-approved proposals and signed actions only; actions must be authorised in owning app.

## Event delivery / failure contract for each included V2 producer

1. Versioned, schema-validated canonical event name with `eventId`, `occurredAt`, `organizationRef`, `accountRef`, stable `subjectId`, `correlationId`, provider identity and allowlisted event payload.
2. Source DB commits business mutation and local outbox in a single transaction where possible. Destination receipt uses a unique event ID; retries are **at-least-once attempts** with idempotent effects, **not globally exactly-once delivery**.
3. Retry with bounded exponential backoff; define maximum age/attempt and a durable held/dead-letter state visible to owners. 409 conflicts, permanent 4xx schema rejects and cross-tenant mismatches require review; no blind customer email/financial replay.
4. Per-subject ordering or monotonic revision check when events might arrive out of order. Event timestamps alone cannot establish ledger truth.
5. Hub read-side must support tenant + correlation ID queries, source system, status, occurred/received time and non-sensitive rejection/retry evidence.
6. Negative tests: duplicate, replay with changed body, bad tenant, missing entitlement, cancelled/settled race, delayed event, unreachable consumer, restore recovery and event backlog.
7. Never show a green production badge based solely on CI. Status should distinguish **contract defined / code committed / CI verified / isolated stage verified / deployed / monitored**, and separately flag unknown.

## Scope and sequence decision

**Required before V2 code freeze:** reconcile actual deployed baselines with overlapping PRs; SSO and tenant contract; error/retry/audit; Tiquet Files and scope lifecycle; job labour and POS part-cost truth; cancellation/payment exception handling; event/projection documentation; full suite at exact commit SHAs. Some financial and file-related features may need smaller approved release slices; do not mark them live until tested.

**V2.1 planned, not a blocker for the initial customer service release:** consented CRM↔Marketing signals; Academy completion events; authorised Sentinel→Tiquet escalation; broader product metrics.

**Stage only after code freeze; deploy only after:** synthetic multi-app tests and two-tenant negative tests, V79 host staging, Google/MFA SSO browser acceptance, real email delivery, provider-verified payment, customer portal accessibility, reproducible restore/rollback, feature flag gates, owner sign-off. Production remains unchanged.
