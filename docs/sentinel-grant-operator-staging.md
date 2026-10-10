# V79 Sentinel owner pilot — scoped Hub machine grant administration

Date: 2026-10-10 AST. **STAGING ONLY. NO LIVE GRANT OR TICKET DISPATCH.**

### New default-off endpoints

`GET /api/admin/sentinel/service-grants` lists only owner-organization machine
grants, without service secrets. `POST /api/admin/sentinel/service-grants`
creates one signed machine-scope grant only following:
- Hub-authenticated **platform operator owner**, current active owner membership
- same-origin mutation and a currently MFA-enabled owner identity
- MFA completed **in this session within the preceding five minutes**
- exact confirmation `AUTHORIZE_ONE_V79_SENTINEL_PILOT`
- exactly one action `ticket.create` and expiry in 1–24 hours
- explicit `V79_SENTINEL_GRANT_ADMIN_ENABLED=1`, with
  `V79_SENTINEL_OWNER_MAPPING_ATTESTED=1` following independently verified
  source-of-truth account/client mapping
- env-pinned `V79_SENTINEL_OWNER_CUSTOMER_ID`,
  `V79_SENTINEL_OWNER_TIQUET_ACCOUNT_ID`, and
  `V79_SENTINEL_OWNER_TIQUET_CLIENT_ID`
- exact owner Hub organization and active Tiquet entitlement readiness
- no other current active conflicting grant, active store transaction serialization
- explicit audit event and persisted durable Hub store revision update

`POST /api/admin/sentinel/service-grants/revoke` requires the same owner
auth, same-origin, fresh MFA, exact active grant ID and literal
`REVOKE_V79_SENTINEL_PILOT`; preserves revoked grant/audit record.
No grant is created by code import. Both URLs return 404 by default.
Any job dispatch still independently requires the NOC human signature,
current NOC operator authorization and its own HMAC machine identity.

### Deployment/release gates NOT yet met

- Hub grant API currently exists only in a **staging worktree**. There is
  no live administrator button/UI, no real MFA-session owner acceptance
  test, no final reviewer signoff, no production rollout.
- `V79_SENTINEL_OWNER_MAPPING_ATTESTED` is a **release operator assertion**,
  not cryptographic proof by itself. Release engineer must read-only verify
  current owner org, active Tiquet account and dedicated client in actual
  PostgreSQL, record verification with timestamp, and independently review.
- Test with existing authenticated owner without affecting other Hub
  organizations; reject stale/no MFA, cross-tenant attempts and replay.
- Hub machine service ingress remains independently OFF. Do not set
  `V79_SENTINEL_HUB_SERVICE_ENABLED` or issue active grants until
  live Tiquet ingress deployment and rollback are safe.
- Need exact-commit independent security review and supervised owner consent
  for the first actual Tiquet job.

### Release identifiers (nonsecret)

Owner Hub organization: `44289786-2583-4bf1-9db2-99eca95dfd96`
Sentinel owner customer: `dda6ced3-5718-4a0b-b58b-fc0f8aa3f7da`
Tiquet owner account: `4864426e-841d-4536-a0fb-8103d504d746`
Dedicated pilot client: `8b759c3d-3309-4926-a271-7bce91f89e89`

No private authentication key, PIN, MFA code or shared secret is stored
in this document.
