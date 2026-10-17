# G3 Hub launch QA source-only contract — 15 October 2026

**NONDEPLOYING VALIDATION / COMMERCIAL NO-GO.** Independent QA branch based on the accepted G3 tracking Git source `ffae1c104d6ded918a0028f92c76624bc0501d8b`, not on older Hub `main` or MCP integration branch.

Purpose: evaluate already-existing source tests for owner/staff invitations, two synthetic organizations, one-time launch tickets, mock WiPay failures and mock Resend delivery/deduplication, without introducing new app features or merging into production. Workflow enforces a three-file allowlist against the pinned G3 tracking base (CI workflow, this document, and the paired-app synthetic test) and runs a full typecheck.

The first job starts an ephemeral Hub on localhost with simulated downstream services, while the second job checks out exact public Tiquet commit `c8e00f1b3fe74ecdbfaf4fa60165c8dd3638e08e` and starts **both real Hub and Tiquet application processes** with dummy credentials, disposable Hub JSON state and disposable CI PostgreSQL. It tests actual signed cross-app provisioning, SSO ticket consumption, one-time replay rejection, two-tenant client-record isolation and cross-tenant forged JWT denial. All fixture state remains confined to the GitHub runner; no customer records are read. Mocked provider tests have injected fake HTTP transports, and no real WiPay checkout, merchant callback, Resend send, SMTP, invitation email or reset is performed.

**Evidence categories:**

- Source unit/mock PASS, when CI green: not proof of current WiPay merchant settlement, bank-cleared funds, real provider delivery or full production session acceptance.
- Ephemeral Hub HTTP PASS: the first job mocks downstream Tiquet, so it is not independent real-Tiquet validation.
- Paired source-app CI PASS: the second job exercises two actual application servers and Tiquet PostgreSQL with fake organizations, but **does not** match the owner's locally built Tiquet runtime image `sha256:ee3deff...` or test the complete deployed-image/Compose pair.
- Actual owner positive A02/A04/A05 browser smoke: separately reported and kept out of synthetic checklists.
- Strict customer release remains NO-GO until exact deployed-image pairing/isolated user acceptance, full app files/config/key restore and rollback, independent security, merchant/finance and signed founder release all pass.

Run only as this nondeploying GitHub CI or in separately approved disposable fixtures. Do not run registration/security E2E tests against live Hub or Tiquet, use real account secrets or publish raw login URLs/tickets.

Links: Hub issue #113 master task register; Hub draft #130 HOLD; Tiquet draft #32 HOLD; Tiquet draft #33 isolated real Tiquet API validation; Hub draft #148 disabled MCP candidate.
