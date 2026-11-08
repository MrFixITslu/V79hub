# Cross-app internal review proposals — separate phase, NOT actual app writes

The first Action Broker prototype can only create PENDING founder-reviewed
work items in the Hub G2 ledger. This phase extends system labels to Tiquet
and V79 Marketing, without any app API, database, message or payment access.

Hub proposal ingress still authorises only operation=create_work_item,
systems hub/tiquet/marketing, the verified founder organisation and a
dedicated HMAC, and checks that the existing G2 action gate is enabled.
All existing signature, owner, idempotency, expiration and rate protections
remain in place. An approved task still requires the existing owner workflow.

Tiquet review: an INTERNAL SUPPORT REVIEW task, not a customer ticket.
The already-running high-priority Hub Help integration may be used later
only after a separate customer/owner-confirmed signed handoff, with verified
requester identity, no model-selected destination and no duplicate sends.

Marketing review: an INTERNAL CONTENT REVIEW task, not a real campaign,
draft, media generation request or publication. Any future API call needs
creator-owned skill, business identity, user connection and explicit approval.
Existing live Studio publication and paid-cloud flags remain disabled.

Do not activate this stack until the first Hub-only MCP Action Broker
is independently deployed, permission-scoped and accepted. This PR is
source-only and is intentionally stacked on the first phase.
