# Hub + Tiquet + AI Workforce closeout — 22 October 2026

## Acceptance ledger

The owner reported all browser checks passed on 22 October 2026: Hub-to-Tiquet owner and customer SSO, coordinated owner/customer logout, customer permissions and separation between two test organizations. These are owner-reported results, not a new automated live audit.

The owner accepted chat usefulness after deployment of canonical eight-role bindings. The Google lifecycle passed: draft saved unsent, appointment created, updated, cancelled. Cancellation succeeded after agenda refresh. The calendar UI fix in this release refreshes appointments and clears old event selection after successful mutations; it does not change Google access or approval policy.

## Deployed baseline before calendar refresh update

| Component | Immutable image | Source |
| --- | --- | --- |
| Hub | sha256:faf3b22f6b09b2ea9d4a537077a05605b19b1f419c02c1e760e49de7aad56430 | b77eaad0f913062f6962534926de1efb593f58e5 |
| Business Agent | sha256:1ba26d22055b53dc99278673b774e480006143f80222509a3255e75d54526f4b | cb9d39376c29812cb26d33de0c9bf54327183835 with pinned older runtime index overlay |
| Tiquet | sha256:18fc67f82ec3dc33a7b281da79d6ab8e6b17f2983f419833bd008101d5711fc3 | 775d9f6c9afae70760896f5ef5cf090272d6a2af |
| Hub PostgreSQL 17 | sha256:b0f9560a2de083e2cc7382e75f808c7381a32852a7ec49117deedb300e552b24 | Existing pinned database |
| Tiquet PostgreSQL 16 | sha256:cf78e76683b9ca8c5733cbbdce6c9262b45b6767934dd0a95e671f9a0fc20685 | Existing pinned database |

This is the last operator-reported baseline. Revalidate all five images and health before another cutover.

## Source reconciliation

PR #185 (3f19684300e753c639fe9aaf9864df588d55669b) → #186 (f971120cc06a0b2ee85a69cdf50ed044f5fc811b) → #187 (b77eaad0f913062f6962534926de1efb593f58e5) → #188 (e06868f7154be9168307cb236400a0eb3f08b24c) → #189 (198bf2214836970cb1260781b70e8aa223547b82) → #190 (cb9d39376c29812cb26d33de0c9bf54327183835). All six were verified open and unmerged on 22 October 2026. Preserve these refs until an integrated mainline candidate is independently reconciled and rehearsed. Do not merge main as a shortcut to reproducing production.

Hub and Agent run independently built immutable images. In particular the Agent runtime retained the accepted older index.ts and applied only the reviewed chat changes; the full repository branch contains newer development routes. A whole-branch rebuild is not equivalent to the accepted runtime. The accepted runtime overlay, source blob manifest and rehearsal proof must remain associated with its image.

## Operating boundaries

Eight canonical local chat roles provide evidence-bound advisory outputs. They do not independently deploy, contact customers, spend, change privileges or complete engineering tasks. Task creation receipts prove creation, not delivery. Ollama output token limit is -1; model context and request timeout remain finite. One model evaluation case required a targeted retry; the other eleven results were preserved in the merged 12-case proof.

Google effects require explicit owner review. Email actions save drafts only; the owner sends in Gmail. Calendar creation, update and cancellation can notify attendees. The normal valid owner MFA session is reused for Google/workforce actions. Billing retains its separate fresh-MFA requirements.

## Recovery handoff

Verified encrypted checkpoint on Acer:
/home/firelion/V79-Portfolio-Checkpoints/s2-20261021T123846Z-f7b53863

Fourteen ciphertext artifacts passed off-host hashes and decryption. Isolated restore passed both PostgreSQL databases, nine app mounts and three app boots, then cleaned up. Proof: isolated-restore-proof-s2restore-d6764c69b540.json. This checkpoint predates subsequent releases; retain their image archives, overlay manifests and rollback files as well.

Current Agent release recovery directory:
/home/firelion/.v79-canonical-chat-roles-cb9d39376c29

Previous Hub release recovery directory:
/home/firelion/.v79-owner-session-mfa-b77eaad0f913

Each guarded release records a private runtime-before.json, original timer states and rollback.sh. Never print runtime snapshots or credential contents. For a failed cutover, check its status and service health before rerunning anything. Use the exact release-specific rollback, then verify all five images/health and timer restoration. The manual command file is not itself proof rollback was rehearsed on the current state.

## Billing and invite-only onboarding handoff

WiPay merchant activation and real settlement are not established by these chat/deployment logs. Keep testing/unavailable states truthful. Manual fallback is an owner-approved invoice and bank-transfer process; an invoice, uploaded receipt, checkout redirect or customer request must never grant paid access by itself. The owner independently checks cleared funds and exact amount/currency before reconciliation. Keep unique bank references and an audit trail; do not recycle a receipt across invoices.

Invite customers through Hub using the approved 14-day trial and assigned Tiquet entitlement. Verify invitation delivery, password setup, displayed plan/currency/trial end and direct dashboard launch. Limit the pilot to invited accounts. Record support contact, an onboarding checklist and a rollback/stop decision for the first customer.

## Remaining release gates

1. Run and inspect the packaged exact-image rehearsal and guarded calendar refresh deployment.
2. Obtain a current read-only five-service, billing/trial-policy and recovery-artifact audit. Local source tests are insufficient to establish live payment readiness.
3. Confirm owner billing UI/manual payment fallback and invitation email delivery on this deployed build using designated test identities. Do not settle real money or send new invitations automatically.
4. Prepare a fresh checkpoint after final changes and verify off-host retention. A fresh restore may be needed if recovery-sensitive inputs have changed.
5. Record explicit invite-only beta release scope and the commercial payment route before real customer invitations. Paid launch and broader app launches remain separate.

Customer beta sign-off remains pending these closeout gates. Already accepted owner/browser tests should be repeated only if the subsequent change affects them or new evidence exposes a regression.
