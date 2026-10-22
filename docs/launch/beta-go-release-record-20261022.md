# V79 Hub + Tiquet — controlled beta GO

Owner: Neil Verdant / V79 Digital. Decision date: 22 October 2026, Saint Lucia.

## Release decision

The owner explicitly approved beta: “beta is a go”, then authorized internal
closeout to continue. This records GO for the existing controlled, invite-only
Hub + Tiquet beta. It does not send an invitation, change an account, enable
self-service signup, authorize charges or switch WiPay to live mode.
The internal AI Workforce remains owner-only; the other portfolio apps retain
their separate release gates. Paid launch remains deferred and WiPay sandbox
is mandatory. Existing 14-day beta trial terms are retained, without automatic
charges. No new trial or organization is created by this record.

Earlier scripts' CUSTOMER_BETA=NO_GO lines remain historical evidence from
before this explicit owner approval. Their technical proof is preserved;
neither their files nor the accepted production images are rewritten.

## Accepted evidence

The owner reported passing Google draft/calendar lifecycle, canonical role
chat, Hub-to-Tiquet SSO, coordinated logout, customer permissions, two-org
isolation, invitation flow, customer pricing and admin request review.

The operator's completed 22 October capture/restore transcript establishes:

- Five exact current images protected; 15 encrypted artifacts verified and
  decrypted off-server on Acer.
- Two PostgreSQL restores, ten mount/file-hash restores and three exact app
  boots passed in an isolated internal network with no default route or ports.
- Signed pricing ledger verified without mutation; private Google credential
  copies validated without mounting them in recovered applications.
- Same production application IDs resumed healthy; original timers restored;
  labelled rehearsal resource cleanup passed.

Checkpoint: `/home/firelion/V79-Portfolio-Checkpoints/s2-20261022T182118Z-4fc56843`

Restore proof: `isolated-restore-proof-s2restore-205a7d4dee45.json` inside that
checkpoint. Completed handoff: `FINAL_RELEASE_HANDOFF_ACCEPTED.md` there.

Controller receipt:
`/home/firelion/v79-final-checkpoint.tc9htuNH/FINAL_RECOVERY_PROOF.json`

Full production redeployment and whole-server disaster recovery are not
established by this isolated restore. Preserve the recovery key and the older
21 October checkpoint separately.

## Exact deployed baseline

| Service | Image SHA256 |
| --- | --- |
| Hub | d722f357206fec938eca691c92ddfe57ece62811f62124f6fbf760258b2b6940 |
| Business Agent | 1ba26d22055b53dc99278673b774e480006143f80222509a3255e75d54526f4b |
| Tiquet | 18fc67f82ec3dc33a7b281da79d6ab8e6b17f2983f419833bd008101d5711fc3 |
| Hub PostgreSQL 17 | b0f9560a2de083e2cc7382e75f808c7381a32852a7ec49117deedb300e552b24 |
| Tiquet PostgreSQL 16 | cf78e76683b9ca8c5733cbbdce6c9262b45b6767934dd0a95e671f9a0fc20685 |

Hub source: `9528f27422525ed6340c6a42e0152aa62f433fd8`.
Agent reviewed source: `cb9d39376c29812cb26d33de0c9bf54327183835`, with the
accepted runtime-only index overlay Git blob
`cf814525a44ce4b102ad699f44408ffb335c3dd5`. That overlay deliberately omits
newer development routes found in the full repository index.
Tiquet source: `775d9f6c9afae70760896f5ef5cf090272d6a2af`.

## Repository reconciliation

GitHub was checked during this closeout. PRs 185–192 remain open drafts with
unchanged heads and a continuous parent chain:

| PR | Source commit | Scope |
| --- | --- | --- |
| 185 | 3f19684300e753c639fe9aaf9864df588d55669b | R18/Google reconciliation |
| 186 | f971120cc06a0b2ee85a69cdf50ed044f5fc811b | Inline approvals |
| 187 | b77eaad0f913062f6962534926de1efb593f58e5 | Owner-session MFA |
| 188 | e06868f7154be9168307cb236400a0eb3f08b24c | Ollama output setting |
| 189 | 198bf2214836970cb1260781b70e8aa223547b82 | Evidence output guard |
| 190 | cb9d39376c29812cb26d33de0c9bf54327183835 | Eight canonical roles |
| 191 | 012a99c84e7f6ab39f065acf15887d146116ffbe | Calendar refresh |
| 192 | 9528f27422525ed6340c6a42e0152aa62f433fd8 | Customer pricing requests |

Main was `0cf77a6b65a982c5c65dd57e5c6a74070b171209`, with 1 commit outside
the accepted chain and 26 commits behind it. The six files changed in that
main-only dashboard commit were individually fetched at both immutable refs:
all six Git blob SHAs are identical. Its source content is already included.

The integration candidate preserves the complete accepted source tree and
joins both histories. Its initial commit added this record and a read-only audit
script; the follow-up also updates two obsolete R18-only test pins to the exact
accepted release hashes, retaining all comparisons and the other eight pins.
It is a draft review candidate, not a replacement production build. Preserve
the original release branches and do not generic-main redeploy. Reproducing
the Agent requires its accepted overlay; unified branch CI/rebuild validation
and a later deliberate mainline merge remain distinct from beta approval.

The accepted Hub CI/CD workflow publishes/deploys only via main-branch manual
dispatch with exact approved SHA. The ecosystem workflow is manual dispatch.
No deployment workflow was dispatched. Tiquet's main-push deployment behavior
is outside these Hub-only changes; Tiquet source is untouched.

## Operations follow-up

The accompanying read-only script checks the current pinned five-service
baseline, sandbox setting, disabled self-service signup, three timers and
morning/evening report metadata for the last three completed Saint Lucia days.
It prints no report findings, customer records, tokens or environment values.
File ownership/privacy plus schema checks establish protected provenance;
these Python report files are not claimed to carry cryptographic signatures.
The operator ran the read-only audit on 22 October 2026 at 18:50:15 UTC
(14:50:15 Saint Lucia). All six AM/PM slots for 19–21 October were verified:
no missing, invalid, incomplete, pending or unverified reports. The five pinned
services retained the same container IDs and healthy state; all three timers
were active, all three worker/briefing services had successful exit status 0,
self-service signup was disabled and WiPay was sandbox. No jobs or provider
calls were invoked and no invitations were sent.

Operations proof:
`/home/firelion/v79-beta-closeout.VKTYxRbw/beta-operations-audit-2026-10-22T185015.009349_0000.json`

This establishes the bounded three-day scheduled-report reliability check,
not indefinite future reliability, email delivery or cryptographic report
signatures. The upcoming scheduled slots remain 08:00 and 19:00 Saint Lucia.
Active timers alone were not used as the basis for PASS.

The beta GO remains the owner's decision. Operational findings are reported
separately and never converted into an automatic invitation or release action.

Pricing requests remain proposals for owner review: no automatic plan changes,
seat enforcement, app provisioning, invoices or payment collection. POS,
Finance, Marketing and other apps require their own acceptance before supply.
