# V79 Digital AI Workforce — CEO + COO Blueprint v1.0

**Date:** 2026-10-10  
**Owner decision:** Two-agent CEO + COO structure approved.  
**Status:** GOVERNANCE BLUEPRINT FOR REVIEW. This file is a proposed implementation contract, not a claim that any autonomy, integration or security capability is deployed. No application code, configuration, production service, account or data is changed by this document.  
**Target users:** V79 Digital founder/operator only. Any future customer-agent feature requires a new, separately approved design and release.

## 1. Mission and fixed structural decisions

Build an owner-controlled AI workforce that can eventually operate routine V79 Digital business processes around the clock, using accurate evidence from V79 Hub, Sentinel and connected products, while escalating material decisions through the CEO to the human founder.

The following are the v1.0 architectural invariants:

1. Exactly **two accountable autonomous agent identities**: CEO and COO. Existing domain specialists are constrained skills, prompts, deterministic playbooks and tools, **not additional independent autonomous agents**.
2. The human owner is ultimate authority. COO reports to CEO. CEO is the **single channel for owner approval requests** and cannot impersonate or substitute owner approval.
3. Both agents initially work only for the owner's V79 Digital workspace. Default access to customer tenant content is **denied**. No delegation or sharing to customers in v1.0.
4. All product access passes through the Hub's authenticated, organization-scoped, signed, allowlisted application adapters. No unrestricted production shell, database, network scanning or arbitrary URL tools exposed to a model.
5. A separate deterministic **policy, approval and audit service** enforces boundaries; agent text is never proof of permission or successful execution.
6. Agents may continuously learn through *measured outcomes, curated knowledge, tested prompts and versioned playbooks*. They may not independently modify permissions, deployed source code, production agents, billing policy or deployment pipelines.
7. Prioritize the focused **Hub + Tiquet** customer launch. Other ecosystem integrations must not block that commercial milestone.
8. Preserve current users, organizations, MFA, paid/trial entitlements, Sentinel modules, backups and recoverability. Never merge/deploy merely because a blueprint exists.
9. Keep the solution model-agnostic and containerized for later cloud migration; the owner approves any data hosting, cloud spend and migration plan.
10. Deviations from these fixed decisions require explicit owner-approved architecture change control. Maintenance and bug fixes may proceed within these controls; changing the design silently may not.

### Functional organization chart

    V79 Owner / Founder
        ↑ high-impact approval requests; ↓ signed founder decisions
      CEO AGENT  [strategy, oversight, risk, priorities]
        ↑ reports and escalations; ↓ objectives and authorized policies
      COO AGENT  [operations, execution planning, continuous improvement]
        ↕ approved tools, domain playbooks and signed integrations
      HUB CONTROL PLANE: identity • policy • approval inbox • jobs • evidence • audit
        ↕ organization-scoped application adapters
      Sentinel • Tiquet • FFPRO2 • Marketing • POS • Academy • Website
        + SIWM • CombatZone • Gaming Studio J • approved other V79 modules

## 2. Role charters

### Agent A — CEO (executive oversight)

- Owns strategy, revenue priorities, operating targets, daily management review, risk and compliance oversight.
- Reads evidence-backed briefings from Hub and COO; compares performance to owner-set goals and flags uncertainty, missing data or stale sources.
- Assigns objectives and priorities to COO. Reviews exceptions, work quality and cost/impact of proposed improvements.
- Produces *one consolidated approval request* for owner decisions with alternatives, risks, expected benefits, rollback and clear approve/reject options.
- Can authorize only low-risk work **within prior owner-approved policy limits** enforced by code; it cannot mint itself more authority, bypass MFA or authorize high-risk actions.
- Issues an owner-facing morning brief and an end-of-day brief at times the owner later sets.

### Agent B — COO (operational execution)

- Runs jobs and checked workflows: service desk triage, follow-ups, inventory and sales analysis, marketing preparations, reporting, web lead intake, product monitoring, education/content QA and security-alert coordination.
- Selects the relevant domain *capability* (Technology/Sentinel, Customer Experience/Tiquet, Finance/FFPRO, Growth/Marketing, Operations/POS/SIWM, Academy, Website/CombatZone) without creating another agent identity.
- Verifies product evidence before reporting a fact; proposes action with owner/organization, scope, affected product, source and outcome.
- Executes only an explicit allowlisted tool action with a policy-approved grant, idempotency key and audit trail. Otherwise drafts a proposal to CEO.
- Investigates failures, retries bounded reversible work safely, and escalates unresolved or high-risk items to CEO.
- Identifies improvements, tests candidate prompt/playbook changes in staging and sends evidence to CEO. Never directly modifies live services by self-generated code.

### Separation of duties

- CEO cannot quietly bypass the rule engine; COO cannot approve its own exceptional actions.
- Owner must approve restricted decisions through authenticated Hub session with **recent MFA** where applicable.
- For high-risk releases, owner approval is necessary but **not sufficient**: independent review and automated safety gates also must pass.
- Neither agent controls its own credential issuance, credential rotation policy, permission grants, safety kill switch or audit retention.

## 3. Clear action / approval policy

| Level | Examples | v1.0 rule |
| --- | --- | --- |
| L0 Observe | Read signed summaries, report health, prepare CEO briefs | May automate after permissions, freshness and privacy checks pass. |
| L1 Internal reversible | Create a private analysis, internal task or *unsent* draft using approved app adapter | Can become automatic **only after** isolated tests, explicit owner-authorized scope, quota and rollback; otherwise read/draft only. |
| L2 External or customer affecting | Send any external email, publish a post, modify a customer ticket, create bookings, change content visible to customers | CEO proposes to owner; approved narrowly and once, with adapter revalidation. Future bounded recurring authorization requires separate explicit approval. |
| L3 Sensitive or high risk | Charge/refund/settle, change prices or plans, sign contracts, grant access, change Sentinel security posture, merge/deploy production code, delete data, migrate cloud | CEO asks owner. Distinct security/finance/release checks and qualified review apply. No agent-only approval. |
| L4 Prohibited | Approve itself, bypass owner MFA, rewrite its own guardrails, exfiltrate secrets, cross tenant boundaries, delete production databases unattended, disable logs/kill switch | Never executable by an AI agent in v1.0. |

**Financial default:** zero autonomous financial transactions and zero unapproved spend. Display read-only cashflow and invoicing facts but never infer a bank settlement from a screenshot or generated statement. WiPay and manually verified payments stay subject to the existing business/payment control workflow.

**Customer default:** no autonomous customer-facing send or publish, booking, refund or production onboarding. V79 internal experiments use synthetic data with explicit cleanup targets.

**Safety stop:** owner can pause all agent writes centrally without taking down Hub or Sentinel monitoring; running jobs fail closed. Disable model-triggered action execution separately from read-only monitoring. Maintain bounded concurrency, rate limits, budgets, expiry and incident alerts.

## 4. Integration model and product registry

For each app, register its owner-approved connection, authorized tenant, service identity, allowed data fields, provenance timestamp, health contract, available actions, limits, audit target and disable switch. An app must be listed as **unavailable** when its integration is not proven; never invent transactions or assume missing metric = zero.

| Product | Read first | Candidate supervised action (future, not active by this document) |
| --- | --- | --- |
| V79 Hub | Accounts, authorized workspace status, plans/trials, platform KPI, job status | Draft owner tasks; approved entitlement/onboarding workflow only after full gates |
| V79 Sentinel / Command Center | Monitored device health, qualified incidents, security findings and service status | Propose a Tiquet incident; require signed machine grants, verified entitlement/mapping and separate one-ticket pilot before creating a ticket |
| V79Tiquet | Workspace-scoped tickets, service status, queue/response KPIs | Internal draft/reply suggestion, then individually authorized ticket update |
| FFPRO2 | Cashflow, revenue/expense, budgets and exception summaries | Finance forecast or report draft; no transaction/transfer |
| V79 Marketing | Campaign performance, prospects, channel status | Campaign and post drafts; sending/publishing always gated |
| V79 POS | Sales, stock levels, exceptions and purchase orders | Replenishment suggestion or internal task; no purchase or price change |
| V79 Academy | Courses, learner metrics and service health | Course update proposal/staging preview; publish only with owner authorization |
| V79 Website | Leads and service/site health | Lead follow-up draft and proposed content updates |
| SIWM | Authorized inventory, shipping, workload and service KPIs | Operational task suggestions |
| CombatZone / LaserTag | V79-owned availability and booking aggregates | Event promotion draft; no booking acceptance without controls |
| Gaming Studio J and other Vision79 services | Owner-only health and aggregate usage where available | Product QA tasks; no access to children's personal data by default |

**Deployment status rule:** Registry entries distinguish PLAN / READ-ONLY VERIFIED / DRAFT ENABLED / OWNER-GATED WRITE / DISABLED, separately for development, staging and production. Nothing in this table declares a service integrated or write-enabled.

**Sentinel trust boundary:** Do not send unverified scanner output or arbitrary logs into a model with execution privileges. Ingest normalized, signed evidence; classify alert severity; map an incident to the exact authorized V79 tenant. A Sentinel alert may generate an internal draft; real Tiquet creation requires validated machine identity and a separately approved one-ticket pilot. No unattended network isolation, firewall changes or privilege grants.

**Customer isolation:** The company-owner workforce is not a multi-tenant AI service. Customer workspaces, student accounts and Vision79-only services retain their current distinct boundaries. Any future customer offering requires new identity, billing, data retention, model privacy and authorization design.

## 5. Technical control plane (implementation contract)

Architecture must preserve existing signed read-only app summary contracts and deterministic specialist routing. Avoid relying on small local Ollama models for unconstrained function calling.

    PRODUCT APIs / SENTINEL event feed
            ↓ signed, tenant-scoped, read-only adapters
      Evidence ledger (source, timestamp, freshness, owner, quality)
            ↓
      Reliable event/job queue → COO task planner
            ↓
      Independent policy engine → Allowed? → bounded action adapter
            ↓ no, or restricted action
      CEO risk/priorities review → Owner MFA approval inbox
            ↓ verified approval token for *specific* action
      Adapter rechecks state, scope and idempotency → execute at most once
            ↓
      Append-only audit + outcome metrics + incident / rollback handling
            ↓
      Curated learning proposal → test → CEO review → owner gate if material

Mandatory common fields for an evidence record: record ID, source app, V79 authorized workspace ID, source observation time, collection time, availability, evidence quality, privacy classification and trace ID. Preserve the existing 15-minute freshness classification where relevant; missing, stale or undated data cannot be treated as current.

Mandatory common fields for action proposals: proposer, reviewer, owner ID, workspace ID, target app, operation from allowlist, strict parameters/digest, evidence IDs/timestamps, preview, risk class, expected result, financial impact, irreversible effects, rollback, expiry, version of source object and unique idempotency key. Approval identity comes **only** from trusted server-side owner session/MFA. Changed, expired, replayed, out-of-tenant or already-completed actions must be rejected.

The execution system needs encrypted secret management, short-lived service credentials, auditable grants, policy-controlled background workers, bounded retry and job lock, durable PostgreSQL state, key management and a safe operator kill switch. Use a transactional outbox where operations span systems; don't promise exactly-once effects across two apps without tested reconciliation. Never share signing secrets with the language model.

## 6. Continuous learning without uncontrolled self-modification

**Daily:** Collect real outcomes: successful work, errors, Sentinel false positives, tickets resolved, time saved, revenue opportunities and human rejections. Verify data quality.

**Weekly:** COO proposes improvements to instructions, domain knowledge, heuristics and internal workflow playbooks. CEO ranks proposals based on evidence, business value and risk.

**Staging:** Replay anonymized/synthetic cases and adversarial tests. Compare the new candidate with the previous approved version using the same metrics. Protect customer data and respect tool costs.

**Promotion:** Cosmetic/internal reversible prompt edits within documented guardrails may follow a pre-approved release path; changes touching security, permissions, financial behavior, customer communications, model/provider data sharing or production code require owner authorization plus applicable independent review. Log old/new version, test evidence and rollback.

A model's claim to be an expert is not a credential. Each finance, security, legal, engineering and operational capability needs curated references, narrow tooling, uncertainty reporting and independent verification when stakes are high.

## 7. Daily operating rhythm

1. **Monitor:** COO reads fresh approved app/Sentinel information. If a connector is down, report unavailable, not zero.
2. **Investigate:** COO creates evidence-backed problem/opportunity briefs and safe internal drafts.
3. **Prioritize:** CEO sets daily work order against owner-approved commercial goals and operating budgets.
4. **Act:** COO executes only the permitted class of task. Restricted matters become clear owner decisions from CEO.
5. **Measure:** Verify external API result and affected records; report unfinished, reverted or failed outcomes accurately.
6. **Improve:** Compare performance with goals, create a versioned improvement proposal and run tests in isolation.
7. **Brief:** CEO delivers morning and end-of-day consolidated dashboard/summary. Exact delivery times and channels are separate owner settings, not presumed approvals.

Initial operational focus: Hub + Tiquet beta stability, founder lead-generation support, Tiquet support quality, Sentinel availability, billing control and onboarding readiness. Do not block the first 3–5 pilot-business validation goals by forcing unfinished secondary modules into the launch.

## 8. Build phases and acceptance gates

| Gate | Deliverable | Evidence needed before advancing |
| --- | --- | --- |
| G0 — Baseline inventory | Reconcile current source/production modules, proposals, deployments and backups | Exact Hub+Sentinel+agent source/image parity documented. No unsafe merge. |
| G1 — Two roles | Map existing Owner Assistant/six specialists under CEO/COO identities, no extra autonomous workers | Owner-only access, deterministic specialist routing, no write permissions, passing current tests. |
| G2 — Read-only V79 connectors | Registry + Hub, Sentinel, Tiquet, finance, POS, Marketing, Academy and website evidence | Signed tenant checks, freshness/unknown truthfulness, outages, malicious-input and leak tests. |
| G3 — Approval and audit | Durable job/proposal queue, CEO inbox and owner MFA approvals | Atomic idempotency, digest/signature, tamper checks, expiry, concurrency, reject/withdraw, audit, emergency stop. No app writes yet. |
| G4 — Supervised actions | One reversible Tiquet/Marketing draft workflow then carefully scoped extensions; Sentinel-to-Tiquet draft pilot | Exact tenant and entitlement mapping, source-state revalidation, isolated tests, rollback, individual activation decision. |
| G5 — Bounded autonomy | Schedules, retry, owner briefs and pre-approved low-risk routine actions | Stable metrics, alerting, action budget and rate limits, false-action tests, incident response and revoke switch. |
| G6 — Cloud readiness | Provider-neutral containers, reliable queue, managed data/backup, secret custody and monitoring design | Written owner-approved data residency, cost budget, restore, cutover and rollback. No cloud spend or migration before approval. |

G0 precedes all new rollout. G1-G4 may reuse completed code/tests but each capability must be proven against **the exact integrated release candidate**, not inferred from earlier branches or PR claims. Existing CI failures, release-blocking external security review and product-specific grants remain unresolved until independently verified.

### Release and test conditions for any production activation

- Tests: owner MFA and session, approval bypass/replay/race, tenant isolation, prompt injection, tool allowlist, stale data, wrong source, lost connectivity, model failure, retries, rate limits and rollback.
- Regression: working Hub single sign-on launches, Sentinel modules, all active V79 apps, current accounts/orgs/plan state, backups and immutable release guard preserved.
- Recovery: fresh compatible PostgreSQL restore checkpoint, proven rollback images, safe stop/restart and no cross-app data loss.
- Finance: no spend/refund/plan change; a manual-payment request or screenshot is not a cleared-funds event.
- Privacy: no unrelated customer data or secrets passed to a model; local Ollama remains first option, external model only under owner-approved data handling.
- Gate: exact release commit SHA, green validation, staged acceptance, independent qualified security review when applicable, and explicit owner production authorization.

## 9. Red-team register: major failure modes

| Threat | Required defense |
| --- | --- |
| Bad instructions embedded in a ticket, web page, log or email | Treat all external content as data; fixed tool allowlists and schema validation; never obey embedded role changes. |
| COO asks CEO to rubber-stamp unauthorized work | Separate policy engine and owner MFA bound to the exact action; high-risk release independent reviewer. |
| Wrong workspace, customer-data leakage | Session-derived org mapping, signed evidence, adapter-side authorization; deny customer access by default. |
| Hallucinated revenue, missing metrics as zero | Evidence provenance, reported timestamp and freshness, unavailable states, no action from unsupported facts. |
| Duplicate charges, tickets, posts or payments | Transactional idempotency, single-operation grants, concurrency tests, reconciliation. |
| Escalating runaway jobs or expenses | Cost/request caps, concurrency/timeouts, breaker, kill switch, nightly audits. |
| Self-improving agent breaks services | Versioned proposals, staging evaluations, immutable release gates, independent check and rollback. |
| Sentinel compromise used to control Hub | Signed machine identity with narrow revocable grant; never trust alerts as authority. |
| Cloud lock-in or loss of business data | Portable workload definitions, separated secrets, proven backup restore and approved cloud-migration plan. |

## 10. Measurement dashboard

CEO and owner view a short scorecard: qualified leads and demos; pilot conversions; cash position (verified source only); Tiquet response/completion quality; Sentinel service availability and incident severity; successful/rejected agent tasks; pending approvals and age; false/duplicate actions; cost per useful action; prevented or rolled-back incidents. Every KPI must display its source and last observation time.

## 11. Approved history and current implementation caveats

- Existing Phase 1 routes six read-only specialist personas under the Owner Assistant. **Retain their tested narrow capabilities**, but expose them as internal CEO/COO functions rather than six additional independent agents.
- Existing Phase 2A/2B evidence and investigations were designed to be signed, read-only, founder scoped and honest about stale/unavailable metrics. Do not replace them with broad model-generated data access.
- Existing Stage 3A work includes proposal contracts and in-memory draft/audit experiments. That is **not** itself a durable, independently reviewed, production-approved inbox/execution system.
- Hub main and currently deployed Sentinel-preserved code have had source-parity differences; do not assume a direct main build preserves all modules. Keep established manual exact-SHA release and rollback guard.
- A draft Sentinel owner-MFA machine-grant path remains review-only and disabled; any genuine Sentinel-to-Tiquet write requires a distinct owner-approved and independently reviewed integration test.
- Hub + Tiquet customer readiness, WiPay and optional verified manual payments continue under their **own** release gates. This AI Workforce blueprint is not authorization to activate billing, customer onboarding or multi-tenant AI.

Relevant work: Hub issues #99 (evidence), #100 (approval), #113 (focused launch); Hub PR #118 (review-only preserved Sentinel merge), #119 (review-only Sentinel grant), and current Phase 1/2/3A documentation.

## 12. Version lock and change control

**Decision record AWF-001** — 2026-10-10: founder **approved two accountable agents, CEO + COO**, with CEO reporting to founder and COO reporting to CEO.

This document defines the proposed **v1.0 control contract**. The decision above is locked now; the rest must be reviewed/accepted by the owner before it is marked as the fully ratified governance baseline. Once ratified, preserve the immutable tagged baseline and a version-controlled decision log. Every subsequent architectural exception requires: written reason, changed section, user-visible before/after, risk/red-team analysis, test plan, rollback, explicit founder approval and revision tag. Normal bug fixes and playbook improvements must stay within these guardrails. Never silently alter the two-agent structure, private-owner scope, or security/approval gates.

**Immediate next authorized work:** Reconcile actual Hub source/production/agent/Sentinel baseline (G0), map existing specialist UI and service code to CEO/COO responsibilities (G1 design), define integration registry and tests. Treat production release, credentials, customer-facing tasks and financial activation as separately gated actions.
