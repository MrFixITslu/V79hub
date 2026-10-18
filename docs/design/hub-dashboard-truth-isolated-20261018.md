# V79 Hub — isolated dashboard data-trust candidate (18 Oct 2026)

**Status:** SOURCE-ONLY / NOT DEPLOYED / NOT A CUSTOMER RELEASE

**Repository:** MrFixITslu/V79hub
**Immutable starting commit:** `df1046151a02dd27db746a2ec5b928f03dcb9b1d`
**Branch:** `design/hub-dashboard-truth-isolated-20261018`

## Narrow implementation (existing approved redesign remains intact)
- `src/lib/dashboardTruth.ts`: pure nullable number/count/percentage helpers; financial amounts require an explicit product-supplied three-letter currency; empty source values never become zero; missing job-status totals stay unknown; availability does not equal uptime.
- `src/components/HubOverview.tsx`: existing UX and signed launch paths retained; safe source-truth labels, source-vs-Hub timestamps, nullable Tiquet open jobs, neutral zero-app states, abortable dashboard refresh, hidden-tab polling suspension and stale-result rejection.
- `tests/hub-dashboard-truth.test.mjs`: source-truth unit and regression checks.
- `src/index.css`: scoped light-theme contrast fix for dashboard action text and navy workspace navigation, based on actual isolated screenshots.
- `.github/workflows/hub-dashboard-truth-browser.yml`: read-only synthetic browser screenshots across desktop, tablet and phone (mock data; not production).

## Scoped REDTEAM / intentionally unchanged
1. The running production image, mixed UI overlay, accepted Compose configuration and off-host recovery remain **UNVERIFIED in this session**. This source candidate is **not production-targeted** until provenance is established.
2. App metrics may lack a trusted ISO currency. In that case monetary values intentionally display an unknown-state dash rather than assuming XCD or USD. A backend data-contract review is required before showing the amount.
3. Signed app launch, SSO/entitlement, MFA, staff permissions, tenant isolation, billing, WiPay and owner operations are untouched. Existing negative tests and independent security review are still required.
4. No charts from one-time snapshots. No new network requests, backend routes, package dependencies, token grants or persistent data changes.
5. The visual redesign requires real synthetic-browser comparison against the approved mockups before acceptance.
6. Product source timestamps may be unknown even when Hub checked recently; no uptime or freshness claims are inferred.

## Required nondeploying validation
- Node 24 `npm ci --no-audit --no-fund`
- `npm run lint`, `npm test`, `npm run build`
- Existing app launch, billing, tenancy, auth, owner approval, and invited-user contracts
- Isolated synthetic browser: owner, employee, empty workspace, missing/0 metrics, absent currency, network failure, hidden tab, manual refresh
- Compare desktop/mobile/light/dark screenshots and measure requests before/after

**Release decision: NO MERGE / NO DEPLOY / NO CUSTOMER ACTIVATION.**
Draft PR review is only source QA. Do not equate passing GitHub CI with live runtime parity.
