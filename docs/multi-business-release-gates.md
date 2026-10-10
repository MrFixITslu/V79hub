# Multi-business release gates

Status: invite-only Hub onboarding is production-ready for closed beta. The V79 platform operator can enroll additional SMB workspaces through single-use owner invitations and explicitly provision POS, FFPRO, Tiquet and Marketing tenant mappings. Customer launches remain fail-closed until the exact product mapping is active. Open registration and paid checkout remain disabled.

## 1. Organization data boundary

Implemented for the current single-instance Hub: organizations, memberships, entitlements, customer custom apps and product tenant mappings are keyed by organization ID; the existing V79 workspace was migrated with backup protection. Authenticated Hub reads, writes and realtime updates resolve their organization from the session, and platform administration is restricted to the V79 operator identity rather than customer admin role. Production persistence now uses PostgreSQL with revisioned transactional writes and stale-writer rejection. Organization context remains session-derived, and customer routes do not trust client-supplied organization IDs as authority.

## 2. Controlled onboarding

Implemented at the Hub layer: only the V79 platform operator can issue a single-use, expiring owner invitation tied to an approved business and email. The plaintext token is returned once in the invite URL fragment, exchanged with the Hub in a request header so it stays out of normal URL logs, and only its SHA-256 hash is persisted. Redeeming the same-origin invite creates the organization, owner membership, selected entitlements, pending managed-product tenant mappings, and audit event in one atomic store commit. Replay, revocation and expiry fail closed. Open registration remains disabled. Product-specific provisioning is deliberately separate so a partially configured downstream app cannot become launchable.

## 3. Two-business acceptance

Implemented and automated. The release gate provisions two independent SMB workspaces for the same owner identity, requires explicit workspace selection, confirms tenant-scoped user/catalog reads, provisions POS, FFPRO, Tiquet and Marketing separately for both businesses, launches each product through a one-time signed ticket, and verifies different workspace-scoped product identities. Dashboard summaries must resolve to the exact organization for all four managed products. Academy remains a separate learner account for customer workspaces, while CombatZone / LaserTag, the Vision79 website and Gaming Studio J aggregate metrics remain unavailable to customer organizations.

The release gate is part of the Hub test suite so a future change that reintroduces a cross-tenant mapping, launch, or dashboard leak fails CI.

## 4. Transactional Hub persistence

Production now runs with `V79_HUB_STORE_BACKEND=postgres` and a dedicated `v79-hub-postgres` service on an internal-only network. The original JSON state was backed up, imported with `npm run store:migrate:postgres`, and compared with the PostgreSQL state before cutover. Startup fails closed if `DATABASE_URL` is missing or the PostgreSQL state has not already been initialized. Do not point the Hub at another application's database.

Backup and recovery validation is also complete for the closed-beta gate: the scheduled backup now includes the Hub PostgreSQL dump, POS PostgreSQL dump, protected Hub runtime data and the existing application volumes. A Hub dump was restored into an isolated PostgreSQL 17 container and matched production by revision, organization/member counts and JSON-state hash. The retained pre-cutover JSON copy remains a rollback asset, but production is no longer expected to run on the JSON backend during normal operation.

## 5. Subscription lifecycle

Keep paid checkout off until an approved provider and merchant account are configured. Store plan, entitlement, billing customer, subscription state, grace deadline, and provider event IDs per organization. Verify webhook signatures over the raw body, process event IDs idempotently in a transaction, and audit transitions. The state policy covers trial, active, past due, grace, canceled, and recovery. Billing permissions must not grant product or operator access. Academy learner accounts remain independent.

Before the first external closed-beta customer, use a controlled pilot workspace to smoke-test the live product redirects and normal customer UX without weakening the tenant gates. Before enabling paid checkout, run provider sandbox checkout, retry, cancellation, payment recovery, and duplicate/out-of-order webhook cases; confirm invoice separation for two demo businesses. Restore from backup and rerun owner launches.
