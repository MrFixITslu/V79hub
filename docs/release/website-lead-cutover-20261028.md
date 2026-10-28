# Website → Hub lead integration: guarded cutover

Current operator gate: all four stopped configuration profiles passed; both
candidate images and their new tests passed in the actual runtime images.
Do not rebuild, repeat those profiles or regenerate the prepared credential.

The release uses the already sealed transaction at
`/home/firelion/v79-lead-release-2pvsb2mo` with external manifest SHA256
`44c0625680f1dfb306aaa49d51f936a08eb76d67ba1e9c2fcddfd9b6be4f368e`.
The installed compatibility adapter is pinned by SHA256
`a1d4842cb0625e1207fb454b5510c05bd2443a245fe7f3143d7be20c660d84e7`.

| Target | Candidate source | Candidate image |
| --- | --- | --- |
| Hub | `2e5f872914bb85f98651ce00a4a90b1880e44076` | `sha256:29d9b40cfd489f65c430b9bc7fbc6f57bc4db35d02508ce95dd002babd642eec` |
| Website | `43de17780357e776c86a7f8898168a50fa5e2820` | `sha256:a5ef48c1b1a4dfd29fe33b19f689adae4ca1d1ed344e2bef8b6a16c1684a848c` |

## Command behaviour

Install `scripts/lead-release-supervisor.py` as private file
`lead-release-supervisor.py` in that existing private release directory, using
the externally supplied checksum. Do not execute it from a temporary path or
overwrite an installed version with different bytes after release begins.

`python3 -B lead-release-supervisor.py --deploy --accept-matching-lead` is a
real production cutover, not a preparation command. It explicitly authorizes
objective acceptance of this one integration after the matching existing
operator test lead is observed. It does not attest to any new human MFA/SSO/
visual checks, which were accepted separately, or approve commercial launch.

The controller verifies the current baseline, protected services/timers, exact
cached image manifests, original engine source, selected models and completed
profile receipt. Before arming anything it reads the existing encrypted SQLite
lead document read-only, requires exactly lead 2 with company marker
`V79-TEST-20261028-A`, Tiquet `sent`, Hub `disabled`, and existing UUID event IDs.
If that datastore/key/document check fails it stops before a switch or timer.

It records durable release state, arms a persistent 20-minute user-systemd
expiry attempt (Linger=yes required, Restart=no), and delegates switches to
the unchanged original `paired-compose-transaction.py`. Explicit order is Hub
first, website second. Their normal health checks and full runtime contracts
must pass. All 41 other containers, four protected cores and three workforce
timer states remain guarded. No application data restore, migration command,
image rebuild, provider-mode change, price change, new submission or Tiquet
resend is part of this command.

The website's existing five-minute sweep is restricted to lead 2. The controller
waits at most six minutes for `hubEventStatus=sent`, retaining original Hub and
Tiquet event IDs and Tiquet acknowledgement. It reads the Hub receipt read-only
and requires the same event/correlation IDs, subject/payload lead ID 2, correct
existing platform organisation, lead.created v1 and received state. No contact
details, tenant IDs, credentials, label values or decrypted data are printed.

Only a genuine match plus both healthy candidate runtime contracts and protected
state permit ACCEPTED. The timer is disabled and verified inactive. Expected
success is `PASS_LEAD_INTEGRATION_ACCEPTED`, scoped to this integration only.
Paid launch and customer/pilot acceptance gates remain separate.

## Rollback and failure behaviour

Every original-engine switch persists its previous container ID before Compose
mutation and verified created ID before Docker start. A fresh process reloads
these identities. Each verification loads its selected candidate OR rollback
model, preventing candidate environment values from breaking rollback checks.
An exact healthy original/previously verified rollback is not recreated.

On connection loss, expiry uses the same persisted state and original engine
rollback. On failed receipt/runtime validation the controller restores the
prior images through that engine. If the engine already completed rollback,
the controller verifies restored runtime rather than running it again. A known
failed rollback is never automatically retried; it requires operator review.
The expiry service has no restart loop, and ACCEPTED/ROLLED_BACK states prevent
an expiry from mutating a completed release. Drift in protected state can refuse
rollback; a scheduled attempt is not a guarantee or evidence of restoration.

`--status` reports actual current image IDs/health and stored phase. `--rollback`
is available only before acceptance and does not override a known failed rollback
or a changed safety prerequisite. Do not repeat `--deploy` after state exists.
No source engine or old accepted release manifest is rewritten.

## Verification evidence and limits

18 focused controller tests passed across targeted runs. They cover real original
runtime validation with selected rollback environment, durable intent before an
ambiguous CLI failure, fresh-process candidate identity validation and original-
engine rollback, idempotent original preservation, accepted-release refusal,
strict command scope, persistent/no-restart unit text, deployment order, actual
encrypted SQLite read-only access, exact Hub receipt tenant/correlation checks,
matching-receipt acceptance and non-repetition of completed/failed rollback.
These are synthetic controller/reader tests, not an executed live cutover or
live expiry rehearsal. Existing application/profile/recovery evidence is retained.
