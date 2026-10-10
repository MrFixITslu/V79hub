# V79 AI Workforce — Phase 1: specialist routing

**Implementation:** isolated feature branch, not deployed to production.

## What is built

The Vision79 Owner Assistant is the coordinator for six read-only specialists:

| Specialist | Initial responsibility | Scoped Hub snapshot |
| --- | --- | --- |
| Operations | Inventory, shipping, operational exceptions | POS, Tiquet |
| Technology | App health, integrations, infrastructure and incidents | Connection summaries and all app health metrics |
| Finance | FFPRO/POS cashflow, expenses and revenue | FFPRO, POS |
| Growth | Campaigns, marketing and website leads | Marketing, Website |
| Customer Experience | Support and enquiries | Tiquet, Website |
| CombatZone Operations | Laser Tag bookings and readiness | CombatZone |

The coordinator handles broad cross-business briefings. Routing uses deterministic, testable rules—**not** tool calling from the local model. Only scoped summary metrics and applicable priority signals are included in a specialist's Ollama request. All specialist outputs are suggestions; none can change data.

The Hub chat UI shows specialist shortcuts and labels assistant replies with the selected specialist. The internal `/api/agent/specialists` endpoint uses the agent-service token guard and returns only static roster metadata.

## Safeguards

- Owner-only Hub login and MFA gates already apply to `/api/agent/chat`; the agent service still requires its internal token. Tests confirm routing does not grant new privileges.
- There are no write tools, unattended schedules, outbound customer messages, payments, bookings, refunds, deployments or security changes in this phase.
- The full owner snapshot is fetched from the existing authenticated internal Hub endpoint, then the fields passed to the model are limited per specialist. This is *context minimisation*, not a tenant-isolation mechanism by itself.
- External text in a snapshot remains untrusted data, not executable instructions.
- The existing deterministic KPI and priority-response logic remains available.
- A model response is not proof of an actual action. All real actions remain behind human approval.

## Test plan

1. TypeScript lint and 24+ agent unit tests; verify role selection and specialist-scoped data.
2. Hub TypeScript lint, 146+ Hub tests and production frontend build.
3. CI builds and disposable staging using **this exact commit**.
4. Owner beta acceptance: Finance, Growth, Tiquet, CombatZone, Technology and Operations prompts; inspect which specialist responds and whether missing data is disclosed honestly.
5. No promotion to production until validated along with rollback plan and explicit approval. Never merge directly to `main` just to test the UI.

## Next build stages

**Stage 2 — Trustworthy specialist evidence.** Add signed, scoped read-only app adapters, data freshness/connection labels, explicit source attribution, timeout handling, and regression cases for missing values.

**Stage 3 — Approval inbox.** Add typed action proposals and a human approval ledger, with idempotency, role/scope checks, expiry and dry-run previews. No agent gets database credentials or unrestricted shell access.

**Stage 4 — Supervised task tools.** One carefully tested action at a time (e.g. draft ticket update, draft campaign, draft finance report). External communications, financial changes, access changes, production deployments and customer-impacting actions require explicit approval.

**Stage 5 — Scheduled routines.** Low-risk monitoring and briefing after rate limits, error budgets, audit logs and opt-in scheduling. Never silently expand trial entitlements or activate commercial billing.

**Known issue:** GitHub [#97](https://github.com/MrFixITslu/V79hub/issues/97) tracks the separate Owner Assistant Ollama tool-call reliability problem. Phase 1 deliberately avoids relying on those calls rather than pretending they are fixed.
