# G3 disabled cutover

`scripts/marketing-production-cutover-disabled.py` uses the two images already
built and tested on `v79sl`, and the exact private overlays prepared by the
successful paired recovery rehearsal. Its constants intentionally bind it to
that candidate build and recovery directory. It does not generate new keys.

The owner reported all nine encrypted backups passing checksums and decryption
on the Acer at `/home/firelion/v79-g3-recovery.Uc019pSJ`. The server manifest
records that report as owner evidence, not independent machine attestation.
The rehearsal checkpoint must be less than one hour old when the script starts.

The script verifies both resolved Compose configurations and all original
configuration/environment file hashes before changing any live container. The
baseline Marketing service uses `build:` without `image:`. For that exact
service, the script checks the existing container's recorded image reference
against the rehearsed runtime digest; moved generated tags are rejected. Both
candidate and rollback overlays explicitly pin image IDs, and neither builds.
The approved changes are the two exact images, dedicated G3 keys and disabled flags,
and Marketing's 768 MiB / one CPU limit. Existing G2 action keys, token mounts
and enabled flag are preserved. It recreates Hub and then Marketing, each with
`--no-deps --no-build --pull never`, without restoring or editing live databases.

The private cutover directory holds a manifest and durable per-service attempt
and verification markers. Each rollback command in that manifest uses the
original ordered Compose files plus an overlay pinning the original image.
Rollback omits the new G3 overlays; original G2 settings remain in its original
stack. Old image retention tags are checked before creation. No rollback command
is executed by the cutover script.

If it prints `NO_LIVE_RECREATION_ATTEMPTED`, inspect the reported preflight
failure before changing the script or checkpoint. If it prints
`LIVE_CUTOVER_UNCERTAIN_INSPECT_BEFORE_ANY_RETRY`, inspect both current image IDs,
health, Compose labels, and the private attempt/verification markers. Either
application may have changed even if Compose returned an error. Do not rerun,
restore data, or blindly execute rollback commands. Determine the actual state
and review the exact recorded rollback commands first.

A success keeps G3 generation and publication disabled and verifies signed G2
acceptance, replay denial, worker separation, protected identity/billing/provider
records, private draft media and anonymous access denial. Agent, PostgreSQL and
Tiquet container identities must remain unchanged. These checks do not establish
owner browser acceptance or provider token validity.

The next acceptance stage is owner sign-in to Hub and Marketing, checking SSO,
accounts, billing and connected destinations. Generation can then be enabled
separately while publication remains disabled, followed by review of an actual
draft package and rejection/cancellation behavior. A real provider pilot needs
approval of its exact material, destination, visibility and schedule.

Run the local synthetic failure/scope checks with:

```sh
python3 -B tests/marketing-production-cutover.test.py
```

They use fake Docker responses and temporary files, never the live server.

## Generation-only activation after browser acceptance

The owner reported browser checks passed for Hub billing, Marketing SSO and the
existing business/YouTube listing. `scripts/marketing-production-activate-generation.py`
records that report as owner evidence. It verifies the accepted disabled-cutover
receipt, unchanged image IDs, backed-up keys, configuration and runtime settings,
and changes only `V79_MARKETING_PRODUCTION_ENABLED` to `1` on Hub and Marketing.
Marketing's publication flag stays `0`. Both app restarts use the same pinned
images with no dependency recreation, build or pull.

Activation requires no existing live G3 ledger. The engine initializes an empty,
paused, signed ledger with no brand, plan, job or approval. Verification uses
the actual service URLs in both directions for current-founder authorization,
signed read access, replay denial, wrong-user/cookie denial and mutation denial
without fresh MFA. It does not fabricate an owner MFA timestamp. Only G3 replay
nonces and empty worker state may be added; protected customer/provider records
and the G2 accepted work-item ledger must remain unchanged.

The private `generation-only-v1` subdirectory records per-service attempt and
verification markers. An uncertain activation is not retried or rolled back
automatically. Inspect the actual service state and markers before any new
action. Generation activation does not mean the owner approved a brand plan,
reviewed a generated package or authorized publication.

After successful activation, open Hub's owner assistant and expand **V79 marketing
· Production and approvals**. Use **Review brand and draft plan**, verify the
service facts and brand assets, and start with **Produce drafts automatically**
unchecked. Configure the desired draft channels and keep YouTube visibility
private. Saving the plan requires fresh owner MFA and authorizes draft production.
Queue one package, review the rendered PNG/MP4, copy and subtitles, and test
rejection/cancellation before deciding on a standing automatic-draft cadence.
Publication remains disabled throughout this stage.

Run the activation checks with:

```sh
python3 -B tests/marketing-production-activation.test.py
```

These also parse all embedded Node probes locally; actual cross-service checks
run only on `v79sl` after the authorized activation.

## Reviewed partial-activation reconciliation

The first activation restarted Hub, then its comparison stopped on Docker's
generated container hostname. The owner ran a read-only diagnostic confirming
Hub healthy with the exact generation-only resolved configuration, Marketing
healthy with its original disabled configuration and unchanged container ID,
and no Marketing restart attempt. Publication remained disabled on Marketing.

`scripts/marketing-production-reconcile-generation.py` handles only that exact
recorded state. It checks the original failure/attempt records, immutable images,
keys, overlays, complete resolved configurations and protected data before
recreating **only Marketing**. It preserves the already-active Hub and all other
services, then completes the live signed-founder, replay, MFA, G2 and empty paused
production-ledger checks. It preserves the original failure as history and writes
the successful completion receipt only after all checks pass. An uncertain
Marketing restart is not retried or rolled back automatically.

The runtime comparison now normalizes an implicit hostname only when the old
and new values each exactly equal that container's short ID and no Compose
hostname was configured. Explicit hostnames, command, user and other runtime
configuration must still match. Re-running the original activation script is not
the reconciliation procedure.

## Expired checkpoint in the partial state

The Marketing-only reconciliation stopped before live recreation when the
original recovery receipt became older than one hour. Do not edit that receipt's
timestamp or rerun the initial cutover/recovery scripts against the new runtime.

`scripts/marketing-production-refresh-checkpoint.py` requires the observed
Hub-active/Marketing-disabled state and the recorded Hub-only attempt. It reuses
the exact existing G3 keys and overlays, captures nine new encrypted backups,
restores copied PostgreSQL and online SQLite snapshots in isolated containers,
tests both enabled G3 signature/replay boundaries and original-image startup
rollback, and verifies live identities, configuration, mounts and protected data
remain unchanged. It never starts the pending live Marketing activation.

The script creates a new private recovery directory and an atomic metadata
reference at `generation-only-v1/fresh-checkpoint-reference.json`. Earlier
backups and receipts remain intact. The reference explicitly says off-host
decryption is unverified. All nine new ciphertext checksums and full-stream
decryption must be checked on the Acer before a reconciliation uses the fresh
checkpoint. Successful local guard/key-reuse checks can be run with:

```sh
python3 -B tests/marketing-production-refresh.test.py
```

The fresh rehearsal passed at
`/home/firelion/v79-g3-refresh-20261014T232003Z-iyexdyhg`. The owner reported all
nine ciphertext checksums and full-stream decryptions passing on the Acer at
`/home/firelion/v79-g3-refresh.Dm7MTN3b`.

`scripts/marketing-production-reconcile-fresh-generation.py` binds exactly that
directory, its private checkpoint reference and receipt, all nine ciphertext
hashes, original G3 key/overlay hashes, source-document/configuration hashes,
protected data and captured live container IDs. Freshness is checked on the new
restore receipt. Original receipt and activation dates remain unchanged and serve
as historical provenance. The existing keys and original live Compose paths are
reused; only Marketing is recreated with the generation flag enabled, and
publication remains disabled. The private `reconcile-fresh-v2` directory records
the owner-reported off-host proof separately from machine-observed checks.

```sh
python3 -B tests/marketing-production-fresh-reconciliation.test.py
python3 -B tests/marketing-production-activation.test.py
```
