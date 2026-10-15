# V79 Hub command centre redesign · 15 October 2026

## Source of design direction

The founder supplied a seven-screen Canva concept: sign-in; overview; application launcher; workspace/team; platform administration; security/profile; mobile Hub. The supplied SVGs are **concept artwork**, not trusted source code or runtime data.

## Adopted visual language

- Dark navy surfaces with restrained V79 electric blue and product-specific application accents.
- Clear sidebar, workspace identity, stronger accessibility/focus states, responsive mobile bottom navigation.
- Split welcome/sign-in composition, without any change to sign-in endpoints, workspace selection, password recovery or MFA.
- Performance-first dashboard with source-defined KPI periods, then attention signals, then workspace-enabled app cards.
- Searchable application quick switcher using existing managed launch URLs and native links.
- App descriptions, accessible card tap targets, clearer empty/unknown status labels.
- Low-cost CSS effects; no heavyweight Canva graphics or remote fonts embedded into production.

## Red-team / release restrictions

1. No illustrative revenue, transaction, uptime, user, team, trend or other fabricated data is rendered as live information.
2. Product status describes data-connection availability; it does not certify whole-product uptime.
3. Only existing user-visible apps and permissions can appear; server remains the source of authorization and tenant boundaries.
4. Current Hub SSO one-time routes remain unchanged; no direct-login fallback for managed apps is added.
5. Platform Admin remains gated by platformOperator, not merely by visual controls.
6. No billing, WiPay, manual-payment, invites, customer records, service credentials, security, platform APIs or deployment workflow is modified.
7. The incoming concept's 'Analytics', 'Integrations', 'Workspace', and 'Settings' labels are not exposed as fake pages where the current product does not have corresponding authorized routes.
8. Mobile, reduced-motion and keyboard use need browser acceptance before a release decision.
9. PR validation is nondeploying, has read-only GitHub permissions and uses no secrets.
10. Never merge/deploy from this design PR until owner browser acceptance, QA and independent launch security/recovery prerequisites applicable to the proposed release are met.

## Additional template-to-product fidelity

- Workspace & Team: the member-management entry screen now uses the shared cobalt/navy command-centre header. Existing invitations and team role rules are unchanged.
- My Apps: existing connected-services page now presents an ecosystem launcher title with matching visual shell, while preserving checks and signed launch logic.
- Security, Billing and Platform Admin: reuse the same responsive page treatment; internal tab, payment and MFA logic remains unchanged.

## File scope

- `src/components/Login.tsx`: visual split login shell only
- `src/components/Sidebar.tsx`: brand and navigation labels
- `src/components/HubOverview.tsx`: visual density, KPI-first hierarchy, truthful no-data states, app tiles
- `src/components/AppSwitcher.tsx`: searchable, accessible quick switcher
- `src/App.tsx`: header and My Apps shortcut
- `src/components/WorkspaceTeam.tsx`, `WorkspaceConnections.tsx`, `WorkspaceSecurity.tsx`, `WorkspaceBilling.tsx`, `AdminConsole.tsx`: shared branded page shells only
- `src/index.css`: scoped command-centre styling with reduced-motion controls
- `tests/hub-design-contract.test.mjs`: regression constraints
- `.github/workflows/hub-design-validate.yml`: validation-only PR pipeline

## Acceptance before any live cutover

- CI: full TypeScript lint, existing isolated tests, design contract test, Vite build all pass.
- Browser: desktop width 1440, tablet 768 and mobile 390; dark and light modes; no clipped launcher or nav.
- Owner: login, MFA, recovery, overview, My Apps, tenant-specific app launch, team/security/billing permissions all verify in an isolated test.
- A no-data workspace displays no invented positive data or false green status.
- Production image/code mapping, recovery, deployment and rollout remain separate approvals.

Reference base: `feature/marketing-production-20261014` at `ffae1c104d6ded918a0028f92c76624bc0501d8b`. Not a merge or a deployment authorization.
