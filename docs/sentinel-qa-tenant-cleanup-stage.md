# Guarded Sentinel QA organization lifecycle — staging review

Status: **implemented in a separate Acer checkout, NOT deployed**. No production or test records have been created, modified or deleted.

Branch: `feat/sentinel-qa-tenant-cleanup-20261009`
Base: `1fae5211e187623b5a1e68eca1ac5aebb88f59e0` (deployed V79 Hub code at assessment time)

## Default-deny release flags

The following variables **must both** be set to `1` to allow creation; cleanup requires only the cleanup flag. Both are absent by default:

- `V79_SENTINEL_QA_CREATE_ENABLED`
- `V79_SENTINEL_QA_CLEANUP_ENABLED`

Do not set either flag on the existing V79 server until explicit release verification has passed. Review and enable for a short supervised window, then disable both again.

## Design

Restricted platform-operator endpoints (Hub owner identity required; ordinary workspace owners are denied by `requirePlatformOperator`):

- `POST /api/admin/sentinel-qa/organizations`: with exactly `{"confirm":"CREATE ISOLATED SENTINEL QA"}`. Requires same-origin; rejects email/user IDs/app assignments supplied by caller. Creates one Hub-local test organization, one synthetic organization owner, one staff user and one viewer user. All usernames end with `@sentinel-qa.invalid`, and passwords are securely generated, salted and returned **once** over the protected API. No invitations/emails or external app resources are generated.
- `GET /api/admin/sentinel-qa/organizations/:organizationId/cleanup-preview`: returns an eligibility review only. Requires the exact org name, a unique trusted creation audit marker from the same platform operator, manifest-matched synthetic user membership, and zero billing, app entitlements, tenant mappings, password resets or invitations. Returns a snapshot fingerprint.
- `POST /api/admin/sentinel-qa/organizations/:organizationId/cleanup`: requires same-origin, exact `{"confirmName":"DELETE Sentinel-QA-<uuid>","previewHash":"<fresh fingerprint>"}`, trusted operator session and all preview checks repeated against the current store. Removes only the matching organization/members/synthetic identities and its QA audit records, writes a deletion audit event, and invalidates associated sessions.

No generic customer-organization deletion endpoint is introduced. Other organizations, accounts, memberships, entitlements and subscriptions remain untouched.

## Tested safety invariants

- Preservation of the platform owner and unrelated organizations
- One Sentinel QA organization maximum per Hub store
- No external app tenant, subscription, order or entitlements at creation
- No deletion when any external application mapping, billing reference, invitation, unknown audit record, shared user, password reset request or unexpected team member exists
- No deletion with forged name, marker, operator identity, wrong confirmation, stale hash or malformed store
- End-to-end create → preview → delete against a synthetic in-memory fixture leaves all unrelated customer records unchanged
- No live database calls, container changes, writes to server, or customer data accessed during testing

## Still required before any V79 production deployment

1. Independent code/security review of the two operator-only endpoints, creation proofs and session invalidation.
2. Verify actual request/response auth and CSRF behavior against a disposable local Hub instance with synthetic seed and a separate temporary datastore, not the live server.
3. Confirm ordinary customer signups and entitlements remain unaffected.
4. Test cleanup after a real synthetic login and confirm no lingering authenticated sessions.
5. Run backup and restore checks, complete staging gate and rollback plan.
6. Review deprovision workflows of FFPRO/Tiquet/Marketing/POS. **If any external app tenant or entitlement is provisioned, this cleanup will deliberately refuse deletion until those links are removed and independently verified.**
7. Keep the test-account creation/cleanup feature flags disabled by default and enable only for the verified supervised QA window.
8. Execute synthetic authenticated tests and manually verify deletion, then immediately disable flags.

## Blocking limitation

No synthetic test organization or real Hub test users have been created. This branch has not been pushed, merged or deployed. Existing Sentinel on Acer continues public, unauthenticated checks only.

## Latest validation / release hold

- Full existing Hub suite plus new Sentinel tests: **178 passed, 0 failed**.
- TypeScript `npm run lint`: **passed**.
- Dedicated creation→preview→deletion integration at the **pure state-function level**: **passed**.
- Live authenticated HTTP integration against a disposable local Hub: **NOT RUN**. The remote editing tool blocked a change needed to bind the isolated test server to loopback only. Do not start the development server on an unprotected LAN as a substitute.
- Existing Hub service and Sentinel Acer dashboard were not redeployed by this task.
- Do not enable the two environment flags, push, merge, or deploy until loopback-only staging and a production-style release review succeed.

**Release decision: HOLD.** The code is a candidate pending endpoint-level integration and a separate controlled rollout.
