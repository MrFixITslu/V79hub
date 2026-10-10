# V79 Sentinel Hub machine-entitlement contract — isolated staging

Date: 2026-10-10 AST. Status: NOT DEPLOYED, DISABLED BY DEFAULT.
Branch: feature/sentinel-service-entitlement-20261010.

This separate endpoint does not reuse end-user Hub sessions, membership
impersonation or Tiquet's ordinary signed-in user entitlement endpoint.

## Endpoint and default safety

POST /api/platform/sentinel/service/check

- Returns HTTP 404 unless V79_SENTINEL_HUB_SERVICE_ENABLED=1.
- Authenticates V79Tiquet as service caller using an **independent** high-entropy
  V79_SENTINEL_HUB_SHARED_SECRET (48+ characters). The signed canonical
  request and two-minute timestamp window use Hub's platform HMAC contract.
- Rejects browser Origin, Cookie, Authorization, weak/missing secrets,
  invalid signatures and oversized or non-JSON requests. No access tokens
  or private credentials are returned.
- Request identifies one serviceId v79-sentinel, one approved Sentinel
  customer UUID, exact owner Hub organization ID, Tiquet account ID, client
  ID and the ticket.create or ticket.add_recovery_evidence action.
- Response contains only allowed boolean and a bounded maximum five-second
  recheck lifetime, with Cache-Control: no-store.

## Business policy enforced

- Owner scope only: organization must match the Hub's internal owner
  organization and be active; cannot apply to customer organizations.
- App entitlement for app-tiquet must be enabled and tenant readiness must
  pass at check time.
- Exact, SINGLE matching stored machine grant required in
  store.sentinelServiceGrants, with status active, enabled true, action
  allowlist, not revoked and a future expiry. No name/email/domain matching
  or human membership impersonation is allowed.
- Duplicate, revoked, expired or mismatched machine grants fail closed.
  A no-grants store fails closed; no grant is synthesized by this endpoint.

## Blocking gaps

**CRITICAL:** Hub's persistent store schema/admin workflow does not yet
provision, save, or revoke machine grants. Current running Hub has no
authorized machine-grant records; the staging endpoint can therefore only
deny until grant persistence/approved provisioning exists.

**CRITICAL:** The corresponding Tiquet-to-Hub signed client adapter is not
yet wired. The Tiquet receiver still requires both active service entitlement
and a separate independently authorized human reviewer, with a fresh signed
approval and verified observation evidence. The current NOC signing prototype
is disconnected from the live NOC and uses disposable test-only keys.

No production Hub service, customer, subscription, Tiquet account or ticket
was modified. This code has no owner approval to deploy, enable or issue
production machine service secrets.
