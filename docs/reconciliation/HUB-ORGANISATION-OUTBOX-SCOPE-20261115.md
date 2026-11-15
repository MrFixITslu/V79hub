# Hub PostgreSQL organisation-rename outbox — staged repository layer

Status: **review only; not merged, not deployed and not wired to Hub routes/workers**.

Imported from preserved production-derived source (11f1f8a) into a new branch based on GitHub main (afefdb9). Changes are additive repository queue schema/lease primitives, tenant-and-owner Marketing rename authorisation and focused regression tests. No production database was accessed for testing.

Local tests on current GitHub main:
- Postgres store: 6/6 PASS, including atomic rename/outbox commit and rollback.
- Marketing owner/tenant authorisation: 9/9 PASS, including cross-tenant, inactive and stale-name rejection.
- Existing Hub runtime-store tests: 3/3 PASS.
- TypeScript: lint PASS.

REDTEAM: A repository method does not establish full production rename readiness. The outbox needs route integration, isolated worker lease/retry tests, tenant-mapped Marketing delivery, failure/replay behaviour and existing customer features regression. Table creation is additive but still requires migration/restore evidence. Do not introduce organisation names to an unauthorised tenant, silently overwrite newer GitHub features, or publish a committed credential.

No merge or cutover without a paired Hub/Marketing staging run, production source parity and recovery acceptance. Public review branch changes no live service.
