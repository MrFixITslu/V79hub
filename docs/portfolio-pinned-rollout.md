# Owner-authorized Hub/Tiquet rollout — 17 October 2026

The founder authorized portfolio merges/deployment on 17 October and subsequently
approved preparing this helper. This is an explicit alternative to the generic
Hub deployment script, which correctly refuses the pinned live WiPay stack.
It does not remove that guard or weaken runtime authentication or tenant controls.

## Options reviewed

1. Generic source sync + base Compose: rejects the live pinned overlays and risks
   dropping effective settings; unsuitable.
2. Recreate the whole Compose project: risks databases, tokens and the separate
   business-agent release; unsuitable.
3. **Chosen:** freeze the exact current effective Compose models, change only the
   selected app images, recreate only the two app services with no dependencies.

## Execution and evidence

Run `scripts/portfolio-pinned-rollout.py` on non-root Acer, after verifying its Git
blob from a pinned commit. It uses the established `firelion@v79sl` SSH identity
with strict host checking. Source candidates are Hub `c2681be42ad0dd68dbabebabb206273a9ea6c817`
and Tiquet `7da53ebb71530366168bd72a7efd52b57d34a23c`.

The helper requires the exact inventoried original images, ordered 13 Hub layers
and one Tiquet effective file, matching file hashes, healthy apps, unchanged
rendered environment, MFA, entitlement recheck and shared launch secret. It
rejects ambient Compose/Docker/Git environment overrides and published app ports.
Literal dollar signs in inspected environment/command values are escaped for
Compose reload, and rendered environment is compared again before shutdown. An
actual Compose serialization test runs in GitHub CI without starting containers.
Docker Compose 5.5.0 config serialization explicitly doubles dollars:
https://github.com/docker/compose/blob/v5.5.0/cmd/compose/config.go

It records the actual candidate image IDs after sequential builds from exact Git
commits, with revision labels. It never retags or deletes original images.

Both builds and encryption of the old app images complete while apps still run.
Before shutdown, active V79 workforce/release/task user timers are paused, and
associated services must be idle; only timers originally active are resumed on
success or failure. Then both apps stop briefly; databases, agent, proxy and other apps remain running.
Each database gets a custom-format pg_dump. Every mounted app destination is
archived from its stopped container, including private files. Streams are encrypted
directly to the existing R1 public key fingerprint
`484CF39CE37A02884497AD9C41A17102D2842ECE`, with no plaintext checkpoint stream on disk.
The remote host receives only the public key. Private frozen Compose/runtime
metadata remain in the mode-0700 remote run directory and are never printed.

Only selected image IDs differ between the frozen original and candidate models.
Every original file remains unchanged. `up -d --no-deps --no-build --pull never`
targets a single service at a time. Docker health checks must pass. The post-switch
runtime comparison includes complete environment, command, entrypoint, user,
working directory, exposed ports, healthcheck, host configuration, mounts and
network membership; dynamic container IDs/IPs and Compose/image labels are excluded.
Other pre-existing containers must retain their IDs/images/status.

On failure after shutdown, restart untouched apps or recreate attempted apps with
their original images, in reverse order. Report rollback failure explicitly. This
is **image rollback**, not automatic database or application-state rollback:
startup can apply schema/state changes. Never overwrite live data automatically.
The encrypted checkpoint is retained for separately reviewed restoration if needed.

The remote worker is detached, with a single-host rollout lock, so disconnecting
the Acer does not kill recovery. The Acer prints its run directory immediately.
Reconnect using the same pinned helper:

```sh
python3 /path/to/verified-helper.py --resume /home/firelion/v79-portfolio-rollout.XXXXXXXX
```

Resume only monitors/copies; it cannot launch a second deployment. A three-hour
monitor timeout does not terminate the server worker. Do not run another deployment
while that worker is active. SIGTERM during the guarded mutation scope triggers
rollback; power loss/SIGKILL cannot be trapped and require manual reconciliation.

At completion, encrypted artifacts and manifest are copied to a new private Acer
checkpoint directory. Every ciphertext hash and full GPG decryption stream is
checked without writing plaintext to disk. Capture/decryption is not a restore
rehearsal. Neither the original R1 recovery directory nor production volumes are
deleted, replaced, imported or restored by this helper.

## Acceptance limits

Source-only synthetic tests cover lifecycle failures and runtime guard behavior;
they do not constitute a server deployment. Server execution must report genuine
results before marking either release deployed. New features remain governed by
the unchanged live feature flags. The business-agent image is deliberately not
updated by this Hub/Tiquet app release. Historical scanner findings remain separate
unresolved review items; this change does not claim scanner clearance.

This checkpoint covers Hub/Tiquet, not the complete portfolio. Full encrypted
portfolio backup, isolated new-release restoration, authenticated MFA/SSO,
revocation, two-tenant security tests and real Sentinel monitoring are outstanding.
`CUSTOMER_RELEASE=NO_GO` remains unconditional.

## Diagnosed mount-order false failure and continuation

The founder's read-only diagnostic on the failed run
`/home/firelion/v79-portfolio-rollout.W8DQrYJI` proved all five core services
healthy on original images. Hub had been recreated; only the order of
`HostConfig.Binds` and `HostConfig.Mounts` differed from baseline. Tiquet, both
PostgreSQL containers and the business agent retained their IDs and exact runtime
fingerprints. Thus the global rollback failure was a comparison false negative.
The initial candidate snapshot was not retained, so its entire prior difference
cannot be reconstructed; corrected comparison still checks the next attempt fully.

Canonicalize only these two mount lists, preserving every complete specification
and duplicate count. Reject duplicate destinations across bind/structured mounts.
All unrelated host options, list ordering, environment, command and mount content
remain compared. Regression tests cover reordered binds/structured mounts, changed
sources/targets/access/propagation, duplicate targets and unrelated list ordering.

Use the updated verified helper on Acer with `--continue-run`. This mode is fixed
to the diagnosed failed run and its already verified off-host checkpoint:
`$HOME/V79-Portfolio-Checkpoints/v79-portfolio-rollout.W8DQrYJI-6_p2qopr/checkpoint`.
It performs no build, image import, new checkpoint capture or data restore.
The checkpoint is from **before the first attempt**, not a fresh snapshot after
original apps resumed. It remains untouched and is not represented as a final
portfolio backup or a rollback of any state/schema changes.

Before launching a detached continuation, Acer verifies the small encrypted
runtime/config archive's ciphertext hash and decrypts it in memory. Derive hashes
of exactly the original runtime snapshot and two original frozen Compose models;
reject unexpected/duplicate members, symlinks and excessive sizes. Send only these
hashes, original manifest hash and candidate image IDs to the server. Server must
match its saved files/manifest, verify original source Compose input hashes,
original app image/health/configuration, cached candidate image IDs and revision
labels, frozen environment/mount/network equality, and unchanged other containers.
Generate candidate models from the authenticated original models with image-only
changes; do not trust leftover candidate files or overwrite old run artifacts.

The continuation uses the same host lock and scheduler guard. Only each selected
app is recreated. Compare genuine health and full normalized runtime after each
switch. If needed, restore only attempted apps in reverse order; report individual
rollback results instead of hiding them behind a single aggregate status. The new
run retains a checkpoint reference and release receipt. Resume monitoring detects
this reference and does not repeat copying/decrypting the previously accepted set.
Full new-release security and restore acceptance remain outstanding, NO_GO.

Continuation model filenames retain `.pinned.yml` so the installed generic Hub
deployer continues recognizing the protected stack. The source generic guard also
rejects older `v79-portfolio-rollout` frozen `.compose.json` paths; executable Bash
guard regression tests cover both formats. Frozen model content remains JSON, which
is also valid YAML; the real Compose CLI regression tests that file extension.

## Accepted Tiquet public-permission repair continuation

The next continuation uses `--continue-repaired-tiquet` instead of the earlier
`--continue-run`. The owner-run diagnostic proved that the cached Tiquet
`package.json` and `server/index.js` had root-owned mode 0600 and were unreadable
by UID 100. The permission-only derivative
`sha256:e9f093d93d12ff9793311c3d6f7d5248a3dc09ba79eb2a0a07e51d967c680c16`
passed synthetic HTTP 200 and the unchanged production health probe on port 3050;
synthetic resource cleanup and all five unchanged healthy original containers
were confirmed. This is startup acceptance, not positive MFA/SSO/tenant acceptance.

Keep the authenticated old checkpoint and its candidate map unchanged. The new
mode selects a copy of that map and replaces only Tiquet with the exact accepted
image ID. Before any switch, verify that immutable ID, the base image ID from the
authenticated old manifest, both repair labels, identical image execution Config
(except the two repair labels and non-runtime Image build metadata), and an exact
base filesystem layer prefix. Existing source revision, runtime, environment,
storage, network and rollback comparisons still apply. No build/import, database
restore or fresh checkpoint capture occurs in the continuation.

If a switch fails, project only fixed startup error categories, exit/OOM state
and log byte count to safe evidence before removing the failed container. Raw
logs are never printed or saved. Evidence collection failure never prevents image
rollback. Both original app images remain available; rollback restores images
and runtime settings only, not database or application data changes. After a
successful rollout, full new portfolio backup and recovery/security acceptance
are still required. Customer release remains NO_GO.

## Hub/Tiquet deployed; remaining portfolio preflight

Owner execution of `--continue-repaired-tiquet` succeeded in
`/home/firelion/v79-portfolio-rollout.6kvFDd5e`: both applications deployed healthy
with full normalized runtime preserved; originally active timers resumed. Retained
checkpoint is explicitly pre-first-attempt, not a fresh backup of these releases.

`scripts/portfolio-remaining-preflight.py` prepares the next Academy/POS/Games
release using the existing owner-supplied 17 October inventory rather than asking
for another metadata dump. It verifies the already accepted rollout module's Git
blob before import, serializes with the same host lock, rechecks Hub/Tiquet images
and health, checks the four remaining app/worker image pins and existing Compose
input hashes, and validates rendered effective environment/storage/network parity.
It saves private original frozen models for review. No build, pull, migration,
container switch, timer change, application data write or backup occurs.

The POS API and worker have distinct original images and their DB/Redis Compose
file differs from the app file. Do not replace the stack with base Compose or
implicitly start dependency/migration services. Read only PostgreSQL migration
metadata with enforced transaction read-only mode. Compare the public migration
name/checksum against pinned source; expose only fixed expected pending names,
counts and status, never unknown migration names or runtime credentials. An absent,
unfinished, changed or unknown migration requires reconciliation before rollout.

The worker has no Docker healthcheck; RUNNING is not worker readiness acceptance.
A passing preflight means private plans prepared only, not deployment or security
acceptance. Later deployment must checkpoint the remaining applications/data,
verify candidate execution compatibility and any required migrations, preserve
runtime and all unrelated services, and verify rollback. Full post-deployment
portfolio backup/recovery and owner MFA/SSO/tenant/security acceptance remain due.

## Remaining applications: guarded rollout after successful preflight

Owner preflight passed in `/home/firelion/v79-remaining-plan.by50q9w3`: all four
app/worker runtime models matched; POS had exactly the expected baseline migration
with no pending, unknown, unfinished or checksum-divergent entries. Hub/Tiquet
remained deployed healthy. POS worker business-job readiness was not proven.

`scripts/portfolio-remaining-rollout.py` runs on Acer, obtains two immutable
Git-blob-verified modules from commit `0cf1fad981d59ab1269ff9133472062e7587ccfb`,
transfers only the public helper/modules and recovery public key to a fresh private
server run, and starts a detached worker under the existing host lock. Resume only
monitors that run. SSH loss does not abandon rollback. No production secrets are
printed or transferred to Acer except within encrypted checkpoint artifacts.

Revalidate accepted plans, original images/container IDs/runtime, Compose inputs,
current Hub/Tiquet release and POS migration history. Reject missing/placeholder
required POS production credentials rather than introducing new defaults. Build
three exact source commits sequentially with normalized tracked public file modes;
POS API/worker share one newly built image. Before downtime, disposable rootfs-read-
only, network-none, no-mount/no-secret probes verify code readability under the
original execution user and executable entrypoint availability. Reject unreviewed
new image execution defaults or environment keys. Revalidate after long builds.

The fresh encrypted **remaining-app prechange checkpoint** includes original app
and database/Redis images, both POS and Academy PostgreSQL logical dumps, a streamed
Redis RDB snapshot, the four apps' mounted content (including original token mounts
only inside encrypted archives), full runtime metadata and original frozen models.
Plaintext dump/archive data flows through pipes into GPG. This is not a complete
post-deployment portfolio backup, a consistent snapshot of every other application,
or restore acceptance. No database migration is performed because none is pending.
Databases, Redis and unrelated containers are never recreated or reconfigured.

Stop POS worker/API and Academy/Games only after all builds and probes pass.
Capture the checkpoint, then switch API, worker, Academy and Games one service at a
time with `--no-deps --no-build --pull never`. Verify actual app health and full
normalized runtime parity. For the worker, require stable running, the actual Node
worker process and a read-only Prisma transaction executing `SELECT 1`, using its
actual in-container process environment. This does not trigger a job or establish
business-job delivery acceptance. Capture redacted failure evidence before removal.

On any failure, restore changed originals in reverse order and restart every
stopped-but-unswitched original. Verify runtime and health/process state, report
individual failures, and resume originally active user timers. Image rollback does
not restore data/schema. The original recovery set and preceding Hub/Tiquet
checkpoint are untouched. After worker completion, Acer copies the fresh encrypted
checkpoint and verifies hashes plus full GPG decryption without plaintext files;
mark restore not tested. New full-portfolio backup, isolated restore/rollback and
positive owner MFA/SSO/tenant/security acceptance remain due. Customer NO_GO stays.

## Academy probe failure before production downtime

Owner run `/home/firelion/v79-remaining-rollout.T2HHBqwg` completed the Academy
build, then stopped at its disposable probe with an unexpected redacted exception.
No checkpoint, app stop or image switch was reached. Probe cleanup was not confirmed
in that output. The exact exception/cause is not recoverable from the old helper's
redacted message; an attached-client timeout is a hypothesis, not a proven cause.

The corrected probe uses detached Docker start, bounded inspect polling for process
exit, then bounded log retrieval. It reports fixed permission/missing-file/OOM/user
categories and safe exception type/function/line, never raw messages/arguments.
Cleanup verifies ownership, no mounts/ports/privilege and network-none isolation;
cleanup failures no longer hide the primary failure's safe evidence.

Use `--continue-built-academy` only for this specifically diagnosed run. Revalidate
the old helper Git blob, module integrity, failed predeploy exit/phase, absence of
checkpoint/cutover, private plan/source/runtime reference, exact clean Git source
including no untracked context, revision label and image creation within the old
worker's build interval. Remove only its identity-labelled, network-none, no-mount
probe on that verified candidate image, then confirm absence. Reuse the Academy
image without a checkout/build and re-probe it; build POS/Games normally only after
it passes. New runs record each completed candidate ID before probes so a later
failure retains that evidence. All previous checkpoint/runtime/rollback controls
remain. Passing the image probe is not application health or security acceptance.
