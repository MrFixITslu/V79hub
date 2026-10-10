# V79 AI Workforce — Phase 2B: aggregate operational investigations

**Release status:** Development candidate only. Do not merge to `main` or deploy without final beta release checks and explicit approval.

## What this increment adds

Phase 2A introduced signed source evidence, owner identity checks, aggregate numeric allowlists, source timestamps and truthful unavailable/stale states. Phase 2B adds **deterministic owner-scoped investigation briefs** derived solely from that verified evidence, independent of local Ollama tool calling.

An investigation includes its specialist, data availability, numbered evidence-backed observations (fixed IDs), source metric, actual numeric value, product-reported timestamp, severity and **suggested review action**. All recommendations are advisory. No state-changing or external tool is invoked.

### Supported product-specific investigations

- **POS / Operations:** critical replenishment count, delayed shipments, unresolved inventory exceptions, open purchase orders and completed sales count for 30 days. Product, location and sales aggregates are added to the reviewed allowlist for context.
- **Tiquet / Customer Experience:** number of jobs and unread notifications; safe counts of clients and team members are available as evidence. Individual ticket content, customer names and ticket attachments are **not** included.
- **FFPRO / Finance:** current-month income, expenses and net cashflow as previously supported. Negative net cashflow and positive recorded expenses produce review suggestions, not transfers or financial decisions.
- **V79 Marketing / Growth:** active campaigns, scheduled posts and connected social accounts. Additional allowlisted workspace aggregates include published posts, customers, repeat customers and remaining AI credits. No campaign is published and no contacts are retrieved.
- **CombatZone and other sources:** retain their Phase 2A aggregate evidence and availability labels. No booking or player details are fetched.

Any stale, unknown, unavailable or undated reading is excluded from findings. Platform-wide admin statistics never trigger owner-workspace findings; no model-authored metrics or unreviewed text can enter the deterministic investigation.

## Surfaces and identity controls

- The authenticated Hub Owner Assistant chat response now attaches `investigation` beside the Phase 2A `evidence` object. A collapsible read-only panel lets the founder inspect suggestions and missing sources.
- A new **internal only** `POST /api/agent/investigate` endpoint takes a fixed specialist ID, uses the existing service-token guard and founder ownership context checks, obtains the current signed Hub snapshot, and returns only aggregate investigation findings. No arbitrary URL, SQL, account ID or HTTP method can be supplied.
- Existing owner MFA and session checks continue to protect the public `/api/agent/chat` path. Cross-tenant customer assistant access remains disabled.

## Verification and limitations

- Eight targeted Phase 2B rules tests validate owner-workspace system scope, fresh-source evidence, strict source attribution, absent/stale source fail-closed logic, true zero versus missing, and no raw customer data.
- The isolated internal HTTP API regression additionally checks 401 missing token, 403 non-owner, 400 unknown specialist and 200 for a valid owner scoped request, without real customer data or product writes.
- Run full agent tests, Hub tests, both TypeScript checks and frontend build, then GitHub CI on the exact feature branch.
- Product contracts were reviewed against actual POS, Tiquet and Marketing summary code. Where product details are not available from existing signed aggregate endpoints, the agent reports that limitation. **This is not individual ticket triage, item-level inventory reconciliation or transaction analysis.**
- The source data is signed between trusted services, but a displayed evidence record is not itself a browser-verifiable cryptographic attestation.
- No autonomous sending, editing, publishing, purchasing, booking, billing, security, code-deployment or customer onboarding actions are enabled.

## Future work

**Phase 2C:** if the owner needs item/ticket-level investigation, add specifically authorised *per-product* GET-only detail endpoints that enforce founder/organisation scope in the source app, redact PII, cap returned rows, apply rate limits and audit each read. Review each app's permission model and retention rules independently before enabling.

**Phase 3:** durable owner approval inbox ([issue #100](https://github.com/MrFixITslu/V79hub/issues/100)) before any action proposals can be executed. Never treat an AI-generated instruction as owner approval.

**Deployment gate:** branch PR remains draft until exact-SHA GitHub CI passes, a disposable smoke test is complete, current Hub+agent rollback images and fresh DB backup are verified, and the owner explicitly approves the controlled restricted-beta deployment.
