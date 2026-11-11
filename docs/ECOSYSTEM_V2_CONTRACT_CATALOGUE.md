# V79 Ecosystem v2 — implemented contract catalogue

**Revision:** 11 November 2026. **Scope:** candidate code in [Hub #251](https://github.com/MrFixITslu/V79hub/pull/251), [Tiquet #64](https://github.com/MrFixITslu/V79Tiquet/pull/64), [Website #86](https://github.com/MrFixITslu/v79website/pull/86) and [POS #19](https://github.com/MrFixITslu/V79POS/pull/19). **This is not a declaration of deployment or live customer readiness.**

## Authority and tenant data

| Authority | Owns authoritative records | Never inferred from |
|---|---|---|
| Hub | Organisations, memberships, entitlements, signed external event receipts | marketing interactions, unverified revenue |
| Website CRM | Public enquiry, consent, attribution, staff approval; website CRM lead reference | shared email/phone/name alone |
| Tiquet | Service customers, ticket and line items, quote, service time, invoices, gateway receipts, scoped job documents and client acknowledgement | a POS typed job reference |
| POS | Stock and technician FIFO usage with immutable cost layers and approved stock movements | Tiquet invoice total |
| FFPRO | Budgets and financial projections | a Hub event as proof of receipt |

A single natural person may have distinct website CRM and Tiquet customer records. Link them by trusted source IDs only.

## Tested cross-app event envelope (v1)

The signed platform ingress accepts only these identities and payload shapes:

| Source | Type | Allowed payload keys | V2 state |
|---|---|---|---|
| Website | `lead.created` | `source` (sanitised attribution) | Website→Hub tested |
| Tiquet | `job.created` | `status`, `priority`, `origin` | Tiquet→Hub tested |
| Tiquet | `job.status_changed` | `status`, `previousStatus` | Contract coded |
| Tiquet | `customer.created` | `origin` | Tiquet→Hub tested |
| Tiquet | `job.paid` | `status` | Receipt contract; **not financial settlement** |
| Tiquet | `payment.recorded` | `currency`, `method`, `provider` | Receipt contract; **no amount** |
| Tiquet | `customer.feedback_submitted` | `rating`, `contactAllowed` | Code, staged privacy gate pending |
| Tiquet | `job.scope_acknowledged` | `version` (positive integer as string) | Newly coded; not yet cross-app accepted |

The source event body contains: UUID `id`, numeric `version=1`, `type`, ISO `occurredAt`, verified `organizationRef`, `accountRef`, stable `subjectId`, optional UUID `correlationId`, and allowlisted `payload`. HMAC covers the exact HTTP method, pathname, timestamp and raw-body SHA-256. Each application uses a dedicated signing secret. The Hub does not accept arbitrary additional fields, free-text customer details or unbounded values.

**Delivery semantics:** at-least-once attempts with durable outbox, backoff and receiver deduplication by source/event ID. This is **not** globally exactly-once processing or guaranteed cross-source total order. 409 conflicting replay is rejected; unmapped tenant and unsafe payload are held/rejected for review. Failed-event status and reason-audited manual retry are candidate code behind an OFF-by-default switch. A queued event is **not** a delivered event.

**Hub observation:** owner/admin can read up to 30 non-sensitive receipts for their active organisation, optionally filtered by a UUID correlation ID. Hub validates tenant ID on every query. Current read model is not an accounting ledger, not a message broker and not live-provider settlement confirmation.

## Scope/file contract

Tiquet's existing job file storage remains authoritative; no separate document microservice is created. Candidate V2 adds versioned scope PDF archive:
- Staff selects an existing ticket-uploaded PDF and publishes an immutable copy under the tenant/job key, with SHA-256 and version metadata.
- Client portal can open the latest archived PDF and explicitly acknowledge its exact version/digest.
- A later version invalidates the relevance of earlier scope acknowledgement. After delivery acceptance, scope replacement is forbidden; staff open a new change request.
- Portal evidence is a timestamped token-fingerprint acknowledgement, **not a qualified e-signature**. Existing access and retention permissions apply.
- Owner-managed backups must include the new scope archive before release.
- Flag: `V79_ECOSYSTEM_V2_SCOPE_ENABLED=0`.

## POS material cost evidence v1

Signed Hub→POS read: `GET /api/platform/job-cost-evidence/:organizationId/:jobId` (POS), gated by `V79_ECOSYSTEM_V2_JOB_COST_READ_ENABLED=0`. POS uses existing `TechnicianUsage` and FIFO `unitCost`, not catalogue list prices. It returns currency, usage count, decimal material cost, last actual usage timestamp and:

`linkage: "staff_entered_reference_unverified"`

`costCompleteness: "unverified"`

`profitMargin: null`

Hub owner/admin's `GET /api/ecosystem/v2/job-cost-evidence/:jobId` requires both POS/Tiquet entitlements, a tenant-scoped signed `job.created` receipt and Hub→POS HMAC. Hub returns `status:"provisional_cost_evidence"` with `verifiedPosJobAssociation:false`. Flag: `V79_ECOSYSTEM_V2_POS_COST_READ_ENABLED=0`.

This does NOT prove a technician entered the correct Tiquet ticket, that all parts/time/expenses were recorded, or that any invoice has settled. It cannot be used to display a **verified job margin**. The approved usage↔job association and full costing ledger remain RED/outstanding.

## Failure rules

- **Rejected/duplicate lead:** preserve both audit records and hold duplicate for manual CRM review. Never associate customers by shared name or phone.
- **No approval:** Website lead and CRM task can exist; no Tiquet ticket may be generated in V2 review mode.
- **Invalid service identity/HMAC/tenant:** reject, do not write business state or fall back to other shared secrets.
- **Hub unavailable:** Tiquet outbound stays pending; transparent retry status. Never report receipt without Hub acknowledgement.
- **SMTP uncertain:** queue for manual review; never blindly resend invoice/acknowledgement as though provider did not accept it.
- **Customer cancels:** preserve ticket, reason, history and finance exceptions; do not auto-refund or erase verified provider receipts.
- **Scope revision:** new PDF version requires new client acknowledgement, never silently reuses an old one.
- **POS cost unavailable:** cost/margin must remain unknown, not zero or 'healthy'.

## Explicitly NOT YET production-verified

Hub Google→MFA→Website/Tiquet browser SSO; exact host-image pins and rollback; live SMTP (including owner-only invoice CC); WiPay settlement and cancellations; cross-app cost association; trusted staff time and expenses; Marketing consent/attribution; Academy completion; Sentinel escalation; MCP owner-approved actions.

Any new event must be implemented in both source projection and Hub allowlist, with signature/tenant/PII/duplicate tests, and its own staging acceptance. Do not rename a tested event without compatibility/versioning.
