# R18 P1 — pinned security + truthful dashboard reconciliation

Status: **DRAFT SOURCE CANDIDATE ONLY. NO MERGE. NO DEPLOY. NO CUSTOMER RELEASE.**

## Exact provenance
- Tested live Hub OCI: `sha256:c84ea1e85a7604fa855219b3e1f2f9c47a035320c7e3c8f15260b36717d136a2`
- Tested captured Hub Git revision / draft PR #179: `795cbaad27a238ddd3a9e724a03cc4313e34ec0c`
- Tested live Tiquet OCI: `sha256:18fc67f82ec3dc33a7b281da79d6ab8e6b17f2983f419833bd008101d5711fc3`
- Required paired Tiquet Git revision / draft PR #44: `775d9f6c9afae70760896f5ef5cf090272d6a2af`
- Exact upstream Hub UI source: current main snapshotted at `0cf77a6b65a982c5c65dd57e5c6a74070b171209`.
- Original running Hub static `dist/index.html` SHA256: `0fa3768ba7ac27051862458bdebedcf1f80896d51538105471d1df2ea82d43ab`.
- Original running Hub 2-file JavaScript/CSS SHA256-set fingerprint: `2af00002fabda37ae32fd95afd23fbdb096b25377ffd6b7b1e07f637c0e36eed`.
These are source/runtime observations, **not proof that a new build is deployed**.

## Narrow overlay
Starting from exact captured Hub PR #179, transplant only the six Git blob-identical dashboard source/test/docs/workflow files from the immutable main SHA above:
- `src/components/HubOverview.tsx`
- `src/index.css`
- `src/lib/dashboardTruth.ts`
- `tests/hub-dashboard-truth.test.mjs`
- `.github/workflows/hub-dashboard-truth-browser.yml`
- `docs/design/hub-dashboard-truth-isolated-20261018.md`

No changes to the Hub backend/server.ts, login, MFA, signed launch, entitlement, billing, WiPay, customer mapping, staff privileges or runtime Compose. No changes to Tiquet code. The sibling PR #44 must remain paired for future coordinated acceptance.

## /REDTEAM failure conditions
1. Any pinned backend or shared auth/layout source blob differs from the frozen audited parent — STOP, do not release.
2. Unknown KPI values rendered as 0, invented currency, false uptime or non-source timestamps — FAIL.
3. Browser preview network request to any host except the CI loopback server — FAIL.
4. CI lint, source/visual tests, build, SSO/tenant/MFA acceptance regression or artifact preview fails — NO MERGE.
5. Exact running Docker OCI/config fingerprint and source provenance not verified against a candidate — NO DEPLOY.
6. Real production snapshot/rollback/cutover strategy not separately approved and proven — NO DEPLOY.
7. Desktop 1440, tablet 768, mobile 390, dark/light, no-data states and owner login/MFA/signed app launch not visually and functionally reviewed — NO CUSTOMER RELEASE.
8. GitHub Actions release approval is an independent operator gate, not satisfied by PR checks or this document.

## Current accepted isolated evidence (Acer, 2026-10-19)
Encrypted 12/12, images 5/5, PostgreSQL 2/2, mounts 8/8, both app boots PASS, negative auth/restart PASS, synthetic positive SSO/replay/session logout PASS, 2-tenant read/write isolation PASS, synthetic MFA/TOTP PASS, full invited-customer 14-day trial Tiquet mapping/SSO PASS, failed-candidate configuration rollback PASS. All were on disposable isolated Acer Docker resources. **A real production image cutover/rollback was NOT TESTED.**

Candidate owner review must compare screenshot artifact and source commit before authorizing any change. This PR must remain draft.