# Website lead receiver — candidate, not deployed

Observed operator evidence: V79-TEST-20261028-A has website ID 2, one website
record and one CRM record, Tiquet `sent`, Hub `disabled`. Running Hub scan
found no `/api/platform/events` literal in server.ts or 61 server modules.
Website endpoint is set; event secret is below minimum and organisation is
absent. Six public website checks remain passed and need no replay.

## Scope and contract

This patch adds POST `/api/platform/events` for signed `website` service
`lead.created` v1 envelopes. Canonical HMAC format matches the existing website
sender. Dedicated credentials, 5-minute timestamp window, 16-KiB event limit,
bounded metadata schema and verified platform-owner workspace binding apply.
It returns `201` only after persisting an immutable private, fsynced receipt
under existing DATA_DIR/website-lead-events. Exact retries return `200`;
changed contents with the same ID return `409`. Invalid signatures/tenants
cannot write. Storage failure returns `503`. No schema migration is needed.

This is an ingestion receipt, not a CRM conversion, task assignment, account
provisioning, notification, payment, entitlement or autonomous execution.
GET `/api/admin/website-lead-events/:eventId` uses existing authentication and
platform-operator/MFA gates and returns bounded receipt metadata only.
No customer session gains permission to enumerate receipts.

Receiver is OFF by default. Required Hub configuration:
- V79_WEBSITE_EVENTS_ENABLED=1
- V79_WEBSITE_EVENT_SECRET: new dedicated random secret, at least 32 characters
- V79_WEBSITE_ORGANIZATION_REF: exact existing platform-owner organisation ID

The website's V79_HUB_EVENT_SECRET must match that dedicated secret, and
V79_HUB_ORGANIZATION_REF must match the same existing organisation ID. Do not
reuse security, SSO, payment, read-only or general platform master keys.

## Paired website retry correction

The existing website sweep retries all disabled historical leads once enabled.
The accompanying website patch parks disabled leads by default. Set
V79_HUB_EVENT_REPLAY_LEAD_IDS=2 to restrict that sweep to the existing test lead
without reposting the contact form or resending Tiquet. Original Hub event and
correlation IDs are retained. Direct new lead submissions continue their normal
delivery flow. A selected lead already `sent` is never swept again. An invalid
selection matches nothing. Empty selection retries ordinary pending leads only.

Do not enable website credentials before that retry correction is deployed.
Do not manually alter stored sync status or generate a replacement event ID.

## Verification and next operation

Focused new tests cover real loopback HTTP signatures, bad service/body/time,
wrong tenant, disabled/missing config, schema boundaries, persistence permissions,
concurrent duplicate receipt, fresh-process replay, conflicting identity,
owner receipt metadata and persistence failure. Website tests cover default,
selected and invalid retry scopes. Existing unrelated suites are not repeated.
The focused receiver harness is not a full Express application/browser test.

Build immutable candidates from these branches; execute the focused tests in
the actual Hub runtime image before releasing. Keep Hub receiver off and website
credentials unset while preparing. Use the existing guarded release engine with
a newly bound image/config baseline; no historical deployment command or seal
is valid for this candidate. No repeat restore or backup drill is justified by
this bounded change; retain the existing recovery evidence.

After both candidates and precise configuration are installed through the
guarded release path: allow only lead 2 in website sweep, wait up to five minutes,
then read that existing lead and its Hub event ID through authenticated website
admin. Require website Hub status `sent`, then read the matching protected Hub
receipt and verify subjectId `2`, intended organisation and correlation. This
is the only pending end-to-end receipt gate for this patch. Tiquet destination
entity/tenant verification remains separate from its existing `sent` ack.

No production change, secret creation, customer invitation or paid access is
performed by authoring or testing this patch.
