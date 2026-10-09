# V79 AI Workforce — Phase 3A: owner decision-only approval inbox

**Build status:** feature branch only. **Not approved for production merge or release.**

## Purpose

Allow the verified V79 founder to turn an aggregate, fresh-source AI Workforce investigation finding into an owner-review proposal, then approve or reject the **plan only**. No proposal is allowed to execute a Tiquet update, send an email, publish a campaign, create a purchase order, transfer funds, change identities, deploy code, or otherwise mutate any connected product.

This is the prerequisite durable decision and audit layer for a later, separately reviewed supervised-action engine—not that engine.

## Source and user workflow

1. The existing authenticated owner assistant shows a read-only operational investigation and its suggested *manual* next step. Freshness is reported by the agent and is not yet independently re-signed by Hub.
2. The founder selects **Propose a review draft** on a finding. For an available finding matching a read-only evidence-ledger metric, Hub adds a transient opaque, ten-minute owner-and-organisation-scoped receipt to the proxied response. The UI prepares one draft with a fixed target application and operation; no arbitrary URL, database command, customer detail or code is accepted. A manually authored draft without attested evidence is labelled `unverified`.
3. **Add draft for review** sends a same-origin POST through a founder session with completed MFA. The server checks owner identity, operation-to-app allowlist, bounded text, schema, idempotency and (if a source reference is claimed) the receipt matching source, proposal fields, owner and organisation. Missing, expired, edited or cross-tenant receipts are rejected. Inbox caps are 80 live pending and 500 total per founder organisation.
4. A founder MFA-verified session may list, approve or reject pending drafts. Every decision requires the expected integer revision and must occur before its 72-hour expiry. Already-decided, expired and replayed requests cannot change status.
5. Hub persists proposal metadata alongside the existing application store, and appends a limited metadata-only audit event. The UI never displays raw idempotency hashes, owner IDs or internal source secrets.
6. Every stored and returned proposal has `executionStatus: "disabled"`. Approving changes only the ledger status and audit record; **there is no action dispatcher**, no write-capable app adapter, no agent-generated email and no outgoing integration request on the approval path.

## Security controls

- Hub's existing `/api` session enforcement protects all routes. Cookie-authenticated POSTs require the correct request origin. Each approval endpoint separately verifies **Vision79 founder-specific access, a completed session-bound MFA challenge and a currently MFA-enabled account**, not merely an admin role.
- Proposals are bound to the founder organisation server-side, rather than accepting a client-supplied organisation or user ID. A known UUID from another organisation yields 404.
- The module validates draft action IDs, expected application, bounded text, source evidence ID and client-generated idempotency keys. Basic NFKC-aware filters reject obvious emails, phone numbers, secret labels and zero-width characters; they are **not comprehensive PII protection**. Unknown keys and execution operations are rejected.
- Approve/reject calls require the current revision; replay/duplicate requests reject with 409. Expired drafts reject with 410. Create retries using the same payload/key return the existing proposal; a changed payload with the same key rejects.
- A server-side serial queue prevents concurrent proposal writes within one Hub process from overwriting each other. Existing Hub persistent-store revision checks remain active. **Cross-process writes and the transient receipt registry are not coordinated between replicas.** A restart or different replica invalidates receipts safely but can interrupt proposal submission.
- The decision audit contains only proposal ID, approved action category, status, revision and disabled execution mode. No proposal body, customer contacts, banking details, credentials, payment API token or model conversation is logged in approval audit metadata. At 10,000 shared events the approval ledger fails closed instead of truncating history; this **does not constitute immutable or tamper-evident audit retention**.
- The UI explicitly states that approval is for **planning**, not execution. Neither a chat message nor a forged model response can directly approve anything.

## Tests

Pure `tests/agent-approval-ledger.test.mjs` covers eight independent security/data cases including allowed actions, wrong apps, PII/secret rejection, owner-scoped listing, idempotency, replay, expiry, stale revisions, cross-tenant UUIDs and metadata-only audit. Hub TypeScript lint and build must pass, followed by all Hub tests with bounded concurrency and GitHub PR CI.

The isolated synthetic Hub owner-session test covers anonymous access, same-origin/CSRF rejection, draft creation, duplicate retry, approval and stale revision replay. Synthetic agent-proxy integration verifies receipt issuance only from a matching, available ledger metric and blocks downstream write methods during owner decisions. Dedicated pure tests check receipt expiry, tampering, cross-owner/cross-tenant use, stale/mismatched source metrics and idempotency-key rebinding. A separate integration test now also confirms the owner completes mandatory MFA **before** the approval inbox becomes available, then rejects a plan with execution still disabled. **Persistence tests added:** JSON and PostgreSQL store reload preserve decisions with execution disabled; a competing stale PostgreSQL writer is rejected by revision validation. **Outstanding release gates:** (a) founder visual acceptance and a dedicated staging proof of no downstream app calls, (b) exact-SHA CI and disposable end-to-end staging rehearsal, (c) production rollback image and backup checks plus explicit release authorisation. The concurrency test covers the persistent-store revision; it does not claim distributed queue coordination is fully solved. Do **not** deploy this feature merely because unit/CI checks pass. Use only synthetic data for these tests.

## Planned Stage 3B and beyond

- Separate, reviewed, per-app **draft-only adapters**, each with narrowly typed tool schemas, owner approval verification, expiry, idempotency and audit. Begin with reversible draft artefacts, never a production customer communication or payment.
- Explicit approval verification and a just-in-time resource version/freshness recheck before future execution. No action executes merely because a model proposed it or an owner approved a draft plan in this stage.
- Dedicated observability for pending/approved/expired/rejected proposals and failed/raced actions, with organisation-scoped permissions and rate limits across multiple Hub replicas.
- Retention and expiry management, source evidence linkage, isolation/multi-instance concurrency and per-app data minimisation.
- Production deployment only after exact-SHA CI, staging rehearsal, recovery snapshot, safe rollback images, owner UI acceptance and explicit production authorisation.

**Critical evidence limitation:** A `proxy_attested` proposal proves that Hub observed a matching investigation and ledger result through the authenticated agent proxy, not that a business application separately signed that result. Full per-app source authenticity and replay-safe multi-replica storage remain separate release gates.

**UI/retention:** The owner inbox now supports authenticated read-only paging of older decisions in groups of up to 100, while live pending records sort first. A lifecycle and archival solution for the 500-record cap remains pending.

The deployed **Phase 2B** workforce is unaffected by this feature branch. Marketing and billing remain separately gated.
