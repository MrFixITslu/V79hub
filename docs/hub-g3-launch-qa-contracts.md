# G3 Hub launch QA source-only contract — 15 October 2026

**NONDEPLOYING VALIDATION / COMMERCIAL NO-GO.** Independent QA branch based on the accepted G3 tracking Git source `ffae1c104d6ded918a0028f92c76624bc0501d8b`, not on older Hub `main` or MCP integration branch.

Purpose: evaluate already-existing source tests for owner/staff invitations, two synthetic organizations, one-time launch tickets, mock WiPay failures and mock Resend delivery/deduplication, without introducing new app features or merging into production. Workflow proves only the two QA files changed since the pinned base and runs a full typecheck.

Tests that start Hub do so on disposable loopback ports and synthetic temporary data directories, with simulated Tiquet/other services. Provider tests inject mock HTTP transports and artificial payment data; no real WiPay checkout, merchant callback, customer records, Resend send, SMTP, invitation or reset is performed. Existing CI environment intentionally disables payment and MCP flags.

**Evidence categories:**

- Source unit/mock PASS, when CI green: not proof of current WiPay merchant settlement, bank-cleared funds, real provider delivery or full production session acceptance.
- Ephemeral Hub HTTP PASS: not proof of real Tiquet binary pairing or exact production image/overlay parity; downstream Tiquet is simulated.
- Actual owner positive A02/A04/A05 browser smoke: separately reported and kept out of synthetic checklists.
- Strict customer release remains NO-GO until two-real-app isolated negative cases, whole-app restore/rollback, independent security, merchant/finance and signed founder release all pass.

Run only as this nondeploying GitHub CI or in separately approved disposable fixtures. Do not run registration/security E2E tests against live Hub or Tiquet, use real account secrets or publish raw login URLs/tickets.

Links: Hub issue #113 master task register; Hub draft #130 HOLD; Tiquet draft #32 HOLD; Tiquet draft #33 isolated real Tiquet API validation; Hub draft #148 disabled MCP candidate.
