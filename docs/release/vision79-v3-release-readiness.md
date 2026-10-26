# Vision79 v3 — approved visuals, guarded release preparation

Owner decision: **approved**, 26 October 2026, in the active review conversation.
Approved visual source: `114841271d4f8b9c4b63df6aedfd55bde2e82f40`.

The approved source includes the Hub, Owner Assistant and Platform Admin candidate shown in the review package. No application code has changed since that approval. `vision79-v3-approved-source.json` freezes 133 runtime files, including the frontend, backend, dependencies and build configuration. The approval is for the reviewed visuals; production operation is still subject to the following technical gates.

## Source acceptance

The historical release checks have been reconciled with the explicitly approved v3 design. Four legacy UI blob pins now identify the approved App, Sidebar, AdminConsole and HubOverview. Four additional pins cover OwnerAssistant, OwnerToday, PlatformAdminOverview and workspace.css. Prior visual-v1 pins remain recorded in the test file. Existing server, Login, trusted-metrics and security markers are unchanged.

The visual structure checks now inspect the approved semantic classes and stylesheet. Signed launch, authorization filtering, real API data, missing-data behavior, focus styles, responsive rules and reduced-motion checks remain. A new whole-runtime check rejects drift from the exact reviewed source.

This is a new approved source contract. It does not authorize reuse of the previous deployment's image, manifest, runtime settings or rollback identity.

## Verification

Full Node source suite: 664 tests — 659 passed, zero failures, five skipped. The five skips still require their integration environment and are not counted as production acceptance. The inventory helper passes five synthetic safety tests. The read-only source preflight reports owner visual approval as APPROVED and release status HOLD; all 133 pinned runtime files match. Existing browser evidence remains applicable because application bytes have not changed.

## Read-only server preflight

`scripts/vision79-v3-live-inventory.py --self-test` exercises synthetic safety cases without accessing Docker.

On `v79sl`, `--run` uses only `docker inspect` and `systemctl is-active`. It reports current container/image IDs, health, a nonsecret configuration-shape fingerprint, mount destinations, network names, Compose-stack label fingerprint and workforce timer states. It never outputs environment values, command arguments, host mount sources, raw labels or health logs. It does not build, pull, stop, start, rename, remove or modify containers, volumes, services or timers.

The inventory is not a full runtime parity check or a sealed release plan. Private full configuration must still be compared by the guarded transaction before any switch. No recovery checkpoint or MFA/SSO acceptance is claimed by the inventory.

Direct server inspection is currently blocked because the remote-control service previously returned a monthly-usage-limit rejection and instructed the assistant not to retry. An operator must run the pinned read-only preflight from the Acer and return its sanitized output. The local work environment has no Docker or Podman, so no candidate container image is claimed built here.

### Observed live inventory — 26 October 2026, 19:20:39 UTC

The Acer operator ran the pinned script from release-preparation commit `04641d47e4d8744a02c202fd0841ec47692cd936`, verified its SHA-256 `d07c0308c32538353ecc28148557dfb514a7b7c019058bd0e1d51a39c097e7c8`, and passed all five self-tests. The sanitized server output reported `production_changes: NONE` and `release_gate: HOLD_PENDING_RELEASE_EVIDENCE`.

| Service | Observed image ID | Status |
| --- | --- | --- |
| v79-hub | `sha256:d2e6f4aee332b076f1340c339e4277b39f1337d2cd02b4b3a4c849e3a6d615e4` | running, healthy, restart 0 |
| v79-hub-postgres | `sha256:b0f9560a2de083e2cc7382e75f808c7381a32852a7ec49117deedb300e552b24` | running, healthy, restart 0 |
| v79-tiquet-manager | `sha256:8a5e15b15732ced03e77f4ceebb019d8ea11381b14645653933e8e8144a13cc0` | running, healthy, restart 0 |
| tiquet-postgres | `sha256:cf78e76683b9ca8c5733cbbdce6c9262b45b6767934dd0a95e671f9a0fc20685` | running, healthy, restart 0 |
| v79-business-agent | `sha256:1ba26d22055b53dc99278673b774e480006143f80222509a3255e75d54526f4b` | running, healthy, restart 0 |

The Hub container ID was `def6bead3fed57c7a40f9a85cfb80398747a76b300500b56a6171637ab2207a3`; its image revision label was `5b8db879b60a3eeb583b40ec8bda725dcb7c8201`. Its nonsecret runtime shape fingerprint was `384aa6206afcfafc27379edc745b595b009f77c7f126789e587dbdc593152348`, with `proxy_network` and `v79-hub_hub_data_network`. It has a writable `/app/data` bind, four read-only token binds, a read-only Google volume and a read-only workforce-reports bind. These are observed destinations, not a complete runtime specification. The three workforce timers were `inactive`; preserve that state unless separately authorized to change it.

This snapshot is time-bound. Recheck the live identities immediately before any release transaction. The historical v2 cutover pins a different Hub image and is invalid for this baseline. No candidate image, checkpoint verification or real MFA/SSO acceptance is established by this receipt.

### Read-only current release contract — operator result

The Acer operator checksum-verified `scripts/p1-r1-current-release-contract.py` at `dac8162a403122d71c2dd418a07a4a1b92a4b244ffc695371ecfe897e262390d` and ran it on `v79sl` with the observed Hub and Tiquet image IDs. Result: `PASS_CURRENT_RUNTIME_CONTRACT_ONLY`; `production_mutations: NONE`. Hub, Tiquet and both Postgres containers were healthy with matching images. The Hub MFA flag was enabled, Tiquet entitlement recheck enabled and Tiquet legacy auth disabled. The live Hub Compose chain has **one** file named `hub-candidate.json`, SHA-256 `2fc119a387df933ff2fcfb8c33d07445160ba281511f05e937ef48beaa4e5083`. The Hub mount destinations matched the inventory, and Tiquet had volumes at `/app/data` and `/app/uploads`.

The check did not compare every private environment value, HostConfig bind/source or rendered Compose field against a proposed candidate. It did not verify a restorable offhost checkpoint. Treat these as open gates; `customer_release_authorized: false` in the operator result.

`scripts/vision79-v3-compose-parity.py` is the next read-only diagnostic. It pins the observed Hub image and the single Compose input hash, then compares rendered environment values, mount sources/modes, network membership and published ports privately on `v79sl`. Its output is allowlisted and redacted. Any drift fails closed. A pass covers only these selected fields; complete runtime parity still requires the candidate and rollback isolated rehearsal.

The Acer operator checksum-verified the script at `d1a7d188207632b03ba8a9808ecd93dcc8cf8387179f3b7c1d2aaf9d88d906f3`, passed three synthetic tests, and received `PASS_SELECTED_RUNTIME_PARITY` for image, health, resolved environment, mount type/source/mode, network membership and absence of published ports. The output explicitly said `full_runtime_parity_verified: false`, `production_changes: NONE`, `release_gate: HOLD`. This is a selected-fields gate only. In particular, the previous v2 deployment failed on HostConfig bind/mount drift; the replacement rehearsal must compare those exact structures and fail closed before any production mutation.

### Immutable candidate build preparation

`scripts/vision79-v3-acer-build.sh` performs a local Acer-only build. It fetches the exact approved commit into a new clean directory, verifies all 133 source file hashes against a separately pinned manifest, resolves the Node and Alpine base tags to immutable registry digests, and passes those digests to Docker. It records the resulting image ID and base digests in a private local receipt. It does not connect to `v79sl`, start a candidate container or deploy. The build remains unverified until the operator runs it and returns the receipt; local syntax validation is not a Docker build. A fresh encrypted offhost checkpoint and isolated boot/rollback rehearsal are still independent gates.

The operator ran the checksum-verified build script on the Acer at 2026-10-26 19:34:41 UTC. It reported `APPROVED_RUNTIME_FILES=PASS_133`, candidate image `sha256:960849ef917ac542674b07ccff5fa64a2c68cd0b452346f5c9fb72d1765d97d6`, Node base `node@sha256:fe4f6d74e20370acb04ad889077d14d0f64a9c8ea6a42bc60cddf1e844699914`, and Alpine base `alpine@sha256:be2656061b536c1883c4034790e21d0a09c5aaaf51968b89368a3c0371ea2c9a`. Build directory: `/home/firelion/v79-v3-approved-build.XDA1yD6v`, with private `build-receipt.json`. `production_changes: NONE`; isolated boot and rollback rehearsal remain false. This image exists on the Acer, not yet on `v79sl`.

### Fresh encrypted capture preparation

The earlier G1.2 recovery scripts pin obsolete images and Compose chains and must not run. `scripts/vision79-v3-encrypted-checkpoint.py` is a new server-only encrypted capture pinned to the observed five service images and the live Hub Compose hash. It encrypts both logical database dumps, every Hub and Tiquet app mount, the prior Hub image, live runtime inspection and Hub Compose input directly into files with the public recovery key; no plaintext dump is stored or printed. It rechecks container identities and configuration after capture. The public key fingerprint is pinned to `484CF39CE37A02884497AD9C41A17102D2842ECE`, and the private key must stay off server. A capture is only `CAPTURED_NOT_OFFHOST_VERIFIED`; copying it to the Acer, verifying all ciphertext hashes, decrypting every item and rehearsing isolated restore remain mandatory. Database exports are sequential and do not establish a cross-database atomic snapshot.

The operator ran the checksum-verified capture on `v79sl`. Two synthetic tests passed. The server reported 14 encrypted items and `production_runtime_changes: NONE`; checkpoint directory `/home/firelion/.v79-v3-encrypted-checkpoints/v3-20261026T194538Z-gnm710en`. Status is `CAPTURED_NOT_OFFHOST_VERIFIED`, release gate `HOLD`. This is the only current v3 checkpoint candidate; no offhost/decryption or restore claim yet.

`scripts/vision79-v3-acer-offhost-verify.py` is pinned to that checkpoint directory, expected Hub image and recovery-key fingerprint. It copies the checkpoint to a private new Acer directory, verifies exactly 14 ciphertext hashes, fully decrypts each item through process pipes, checks database dump headers, tar structure and the private runtime JSON shape, then writes a local verification receipt. It does not store plaintext files, alter production or claim an isolated restore. Any missing key, changed file, failed decryption or structural error stops the gate.

The operator ran the offhost verifier at 2026-10-26 19:52:00 UTC. All 14 ciphertext hashes and 14 decryption/structure checks passed. Acer copy: `/home/firelion/v79-v3-offhost-we7b0lir/v3-20261026T194538Z-gnm710en`; private proof: `/home/firelion/v79-v3-offhost-we7b0lir/offhost-verification.json`; server receipt SHA-256 `35a9b4d41b5c42a8c6653e1c1985ebdae49ce77432d57c94ff68c82172173df5`. The result explicitly says `isolated_restore_verified: false`, `production_changes: NONE`, `release_gate: HOLD`.

`scripts/vision79-v3-acer-db-restore.py` is prepared for a disconnected, rootless Podman restore of the two encrypted logical dumps. It requires the exact two Postgres image IDs already cached on the Acer, rechecks the offhost receipt and dump hashes, restores into disposable tmpfs databases with no network or published ports, verifies nonzero user-table counts, and removes the containers. It does not connect to production or claim the Hub app and mounted files can be restored. Local synthetic tests pass; actual restore evidence is pending operator execution.

The operator ran that rehearsal and received `STOP=EXACT_DB_IMAGE_NOT_CACHED` after two synthetic tests passed. No database container was started and no restore was attempted. The local Podman image prerequisite assumption was false. The recovery evidence remains offhost decryption only. `scripts/vision79-v3-acer-stage-db-images.py` now checks the live DB identities, streams exact image saves through SSH into the Acer local Docker image store, verifies the exact loaded IDs, and rechecks the server identities. The revised `vision79-v3-acer-db-restore.py` uses that local Docker daemon with the same disconnected tmpfs isolation and cleanup checks. Neither step deploys or restarts production.

The operator then staged both exact database images (`PASS_2`), but the Docker restore command returned `STOP=REDACTED_ERROR`. That result is **not** a restore pass. Code review found a defect in the table-count check: it called `isdecimal()` on a `bytes` result, which raises `AttributeError`; this could occur only after a database restore reached the count query. The diagnostic did not record a phase, so the actual cause is not established from the output. The corrected script checks byte digits, tests that path, reports a fixed phase and safe error type, and offers a read-only local residue preflight. Rerun only the corrected local restore after its preflight passes; the images are already staged.

The corrected Acer run passed its residue preflight (zero leftovers), restored both encrypted dumps to disconnected disposable Docker databases, counted 1 Hub user table and 25 Tiquet user tables, and removed both containers. Receipt time: 2026-10-26 20:00:56 UTC, tied to server receipt SHA-256 `35a9b4d41b5c42a8c6653e1c1985ebdae49ce77432d57c94ff68c82172173df5`. `database_restore: PASS_BOTH`; `app_boot_verified: false`, `full_recovery_verified: false`, `production_changes: NONE`, `release_gate: HOLD`. Mounted-file restore and application startup remain open.

`scripts/vision79-v3-acer-stage-app-images.py` stages the prior Hub image by decrypting its offhost archive directly into the Acer Docker image store and stages the current Tiquet image via a read-only SSH stream, verifying exact IDs and server Tiquet identity. `scripts/vision79-v3-acer-paired-boot.py` then attempts a disconnected local smoke: restore three app mounts to private RAM scratch, restore both DBs in tmpfs, health-check the approved candidate Hub and current Tiquet, and cold-boot the prior Hub image with the same isolated services. It uses synthetic secrets, no published ports and no production access. This is not real owner MFA/SSO, full mounted-secret recovery, or exact Compose replacement parity. Both scripts have only local synthetic tests so far; their operational result is pending.

The operator staged all app image identities (`candidate`, `prior_hub_from_offhost_checkpoint`, `current_tiquet`: exact IDs) with no production changes. The paired boot then stopped at `ACTIVE_SWAP_REFUSED_FOR_PRIVATE_RECOVERY`, before decrypting any app mounts or starting a container. Do not disable swap blindly on this memory-constrained Acer. The previous isolated DB restore used tmpfs while swap status was not checked; tmpfs can page to swap, so its no-persistent-plaintext property is **not established**. Database restore correctness evidence stands, but private-data isolation needs a verified swap configuration or a safer rehearsal host. A synthetic-data-only image boot can proceed independently.

`scripts/vision79-v3-acer-synthetic-hub-boot.py` provides that independent local smoke. It starts candidate and prior Hub images sequentially on `--network none` with synthetic credentials, empty tmpfs app data, a read-only root, no persistent logs or published ports; it checks health and removes each container. Active swap does not threaten customer data in this synthetic-only mode. Passing this smoke would establish image startup and prior-image cold boot only, not mounted-data recovery, Tiquet SSO or exact runtime parity.

The operator's checksum-verified synthetic run passed candidate and prior Hub health with `customer_data_used: false` and `production_changes: NONE`. Acer memory showed 11 GiB total, about 5.9 GiB available; `/swapfile` is a 2 GiB disk-backed file with about 1.0 GiB used. Thus the private-data paired rehearsal remains blocked until the storage encryption/swap posture or a safer host is established. No automatic `swapoff`, swapfile deletion or system memory change is authorized by this evidence. The synthetic result does not certify Tiquet or MFA/SSO.

Read-only storage inspection showed the Acer `/swapfile` resides on `/dev/sda2` ext4 without a visible dm-crypt layer. The server likewise has an active `/swap.img` (4 GiB, about 2.2 GiB used) with 4.8 GiB memory available. Neither host offers a demonstrated no-disk-swap private-data rehearsal as-is. Do not run the private-data paired boot on either host while disk-backed swap is active. A guarded, temporary Acer swap window may be considered only with sufficient available RAM, no existing rehearsal residue, verified swap disable before decryption, guaranteed cleanup before swap reenable, and explicit operator execution. The isolated DB restore correctness result remains; its disk-swap confidentiality was not proven.

`scripts/vision79-v3-acer-swap-window.py` implements that operator-controlled Acer window. It requires the exact paired-boot script hash, sole active `/swapfile`, available memory at least swap-used plus 4 GiB, no residual v3 containers/RAM scratch, and a cached sudo credential. It disables `/swapfile`, verifies no swap remains and at least 4 GiB available, runs the paired rehearsal, checks cleanup, and then re-enables swap. If cleanup is not proven, it leaves swap **off** for manual review; no timer can re-enable it while private RAM scratch might remain. This changes Acer swap state only. Local synthetic tests cover the residue hold, but the operation has not yet run. The paired boot may still fail on application/runtime differences and is not production acceptance.

## 26 October 2026 — guarded Acer paired recovery PASS

The owner-operated, SHA-256-verified paired boot at `4aef955c7b4f0503e2128b1b17e7cc331514de98` passed the complete isolated smoke and cleanup sequence. The terminal output reported:

- `MOUNTED_APP_DATA_RAM_RESTORE=PASS_3`
- `TIQUET_RAM_MOUNT_APPUSER_ACCESS=PASS`
- `PAIRED_DATABASE_RESTORE=PASS_BOTH`
- `CANDIDATE_HUB_HEALTH=PASS` and `TIQUET_HEALTH=PASS`
- `CANDIDATE_HUB_AND_TIQUET_HEALTH=PASS`
- `PRIOR_HUB_ROLLBACK_COLD_BOOT=PASS`
- `disposable_cleanup: PASS`
- `ACER_SWAP=RESTORED`
- `GUARDED_SWAP_WINDOW=PASS_REHEARSAL_AND_SWAP_RESTORED`

The prior failure was Tiquet exiting with code 1 while the approved Hub returned HTTP 200. A separate branch changed only the **disposable Acer RAM restore** by chowning its Tiquet application-data/uploads/log mounts to Tiquet's existing non-root appuser and checking access, then the paired boot succeeded. The app images and live server were not modified. The revised helper added two synthetic safety tests. The successful operator run is the current completion evidence for isolated restore, candidate/paired health and prior-image rollback boot.

**Still NOT verified:** exact production Docker/Compose/HostConfig replacement parity; live owner MFA, session expiry/renewal or genuine Hub-to-Tiquet SSO in the new image; customer-facing browser design acceptance on the deployed candidate; sealed production cutover/rollback transaction. The rehearsal used synthetic credentials and its own isolated runtime profile. The report itself explicitly sets `exact_runtime_parity_verified: false`, `real_owner_mfa_sso_verified: false`, `production_changes: NONE` and `release_gate: HOLD`.

**Next release work:** verify the complete production replacement runtime contract (including exact `HostConfig.Binds`, mounts, environment, network, labels, restart policy, storage and rollback identity) privately and fail closed on drift; arrange genuine owner MFA/SSO and browser acceptance on the candidate without interrupting production; only then seal a guarded Hub-only release. Preserve the production database and Tiquet image; do not migrate or alter customer data for this visual release.

## Next diagnostic prepared — deep live runtime audit (not executed)

Commit `c9bf54bf90a70e270331a93bb86844ad9b8d4c2d` adds `scripts/vision79-v3-deep-runtime-audit.py` on the independent `audit/v79-v3-deep-runtime-20261026` branch. Its SHA-256 is `1cd0c75a7ddaf822c211415d07688042d3aae41f64748e8221f82b3442514e34`.

The script only runs read-only commands (`docker inspect`, `docker info/context`, `docker compose config`) on `v79sl` and checks the previously observed five image IDs, health and Hub Compose file SHA. In private process memory it validates resolved Compose environment, actual mount sources/modes against Compose and `HostConfig.Binds`/`HostConfig.Mounts`, network membership, filesystem mode, privileged/host-PID boundaries, and configured restart policy. It fingerprints the live Hub runtime and rechecks for concurrent drift. It outputs only allowlisted counts, a fingerprint and stop codes, never raw settings, host paths, passwords, tokens, Compose content or health logs. Its local synthetic self-tests are **prepared but not yet operator-run**. No Docker changes or production deployments are authorized.

**Do not treat an audit PASS as full candidate runtime parity.** The candidate image is still on the Acer. Actual replacement/cold-rollback with exact private production settings, owner MFA/SSO/session checks and authenticated visual/browser acceptance remain independent HOLD gates. The successful paired restore does not satisfy these higher-risk production-replacement tests.

## Live runtime PASS; next candidate contract gate prepared

The owner executed the deep live audit on 26 October 2026. All eight safety tests passed; result `PASS_LIVE_RUNTIME_COMPOSE_AUDIT`. Verified **85 environment keys, four HostConfig binds, three HostConfig mounts, seven total mounts, two networks**, with unchanged production and `release_gate: HOLD`. Private runtime fingerprint: `2e63990c22d31d0998d90b575f7490a5fc09917c839f6a54f68e317cdfffaa57`. The candidate was not checked by that audit and is not yet on the Dell.

At `ed9b6b146f60b2bbce3648d3c99ab51412353f2a`, the separate `gate/v79-v3-acer-candidate-contract-20261026` branch prepares two Acer-only scripts:

- `scripts/vision79-v3-acer-candidate-contract.py` — SHA-256 `37af96763959519e246a172683bb1ee01a7d99cf77094af8e6f76dd5e572c75b`.
- `scripts/vision79-v3-acer-contract-window.py` — SHA-256 `73f1e32f2b7e312e1ce6560b87cb0d1b126a3e507a5532e0f5959b488b8925bb`.

The wrapper reuses the previously tested **operator-executed, single-file swapoff, headroom, cleanup and swap restoration** pattern. The checker refuses active swap, verifies the previously encrypted offhost runtime snapshot and receipt, decrypts only into private process memory, confirms that the archived Hub runtime fingerprint exactly equals the owner-supplied live audit fingerprint, and compares prior/new local Docker image metadata and default-environment key coverage. It prints only sanitized counts, flags and STOP codes. Both new scripts have synthetic unit tests **not yet executed by the operator**. They perform no production access, image transfers, container starts or deploy. On any mismatch, `release_gate: HOLD` continues.

A PASS would mean only snapshot identity and candidate **metadata** are compatible; it is **not** a substitute for exact replacement runtime/Compose rehearsal, MFA/session/Hub-to-Tiquet SSO acceptance or authenticated browser visual verification. Never reclassify it as deployment approval.

## 26 October 2026 — candidate metadata gate PASS; image-only Dell stage prepared

The Acer operator ran the checksum-pinned candidate-offhost contract at `ed9b6b146f60b2bbce3648d3c99ab51412353f2a`. It returned `PASS_CANDIDATE_METADATA_AND_LIVE_SNAPSHOT_MATCH`, with exact source and live runtime fingerprint matches, 85 live environment keys, seven mounts, zero candidate-default value conflicts, and prior/new user/entrypoint/command matches. The guarded swap window returned `ACER_SWAP=RESTORED` and `CANDIDATE_CONTRACT_WINDOW=PASS_CHECK_AND_SWAP_RESTORED`. The same receipt explicitly states `candidate_image_on_server_verified: false`, `full_production_runtime_parity_verified: false`, `real_owner_mfa_sso_verified: false`, `production_changes: NONE`, `release_gate: HOLD`.

The next stage is **only Docker image-cache transfer**, using `scripts/vision79-v3-image-stage-acer.py` and `scripts/vision79-v3-image-stage-server.py` on the independent `stage/v79-v3-image-only-20261026` branch. Operator execution is still outstanding. The sender validates the previously pinned approved Acer image/build receipt, exports by immutable ID, **rejects any archive carrying mutable repository tags**, verifies a full SSH SHA-256 and reserves disk headroom, then imports on the Dell using `docker image load`. The server checker confirms the pinned five live running service images/health, exact Hub runtime fingerprint, candidate absence before and approved candidate image ID/source label after. The sender independently checks unchanged five-container identity hashes before and after and removes the temporary transfer archives. The scripts do not stop/start/recreate any container, modify Compose or touch persistent application data. Imported image layers **will modify the Dell Docker image cache**, but this is not a production application deployment.

The new scripts must pass their synthetic tests before being run by the operator. Both fail closed; any partial import/error retains the release HOLD and must be reconciled before retry. Successful import would **not** satisfy real owner MFA/SSO, exact candidate runtime parity, visual browser acceptance or production cutover/rollback rehearsal. Do not transfer live secrets to the Acer or disable server swap for image staging.

## 26 October 2026 — image-only stage pre-transfer STOP, archive validator corrected

The operator launched the first image-only staging script. All four original Acer synthetic tests passed and the read-only Dell gate returned `SERVER_LIVE_BASELINE=PASS_BEFORE`. The Acer then returned `STOP IMAGE_ARCHIVE_CONFIG_DRIFT` during local `docker image save` archive verification, **before any SSH archive copy or `docker image load`**. The candidate was **not imported by this attempt**, and production deployment remained unchanged; no subsequent service-gate snapshot was collected by that aborted run.

Root cause in the checker: it compared Docker's `manifest.json` `Config` **filename** to `<image SHA>.json`. Newer archive layouts may use `blobs/sha256/<digest>` without a `.json` suffix. That filename assumption is unsafe for cross-version Docker images.

On branch `fix/v79-v3-docker-archive-config-20261026`, commit `e136de853595295d22436cdbf33bfea4e72446d6`, the Acer stage script now checks the actual archive config **bytes** against the pinned image's SHA-256 regardless of safe filename convention. The script also refuses tagged archive manifests, unsafe paths, symlink/nonregular config members, duplicate tar members, impossible sizes, and cryptographic digest mismatch. Three additional synthetic cases cover both valid filename styles, mismatched/tagged configs, and traversal; the total is **seven tests, pending operator execution**. Its SHA-256 is `4680daec3b9dea45b0c354e486ff258666c40f66271abd3f871ee0c0cae4d292`. The unchanged Dell read-only gate is `e2499c7879e1ecb406809c471364eeb8e33f602341d4d24c720de4907e06f9bd`.

**Next:** operator reruns only the checksum-pinned image-only stage after self-tests, not the encrypted recovery or DB boot. Successful stage will cache the image only, with live Hub/Compose/data unchanged. `release_gate: HOLD` remains until exact candidate runtime, genuine MFA/SSO, browser visual acceptance and sealed rollback/cutover have been separately verified.

## 26 October 2026 — second pre-transfer archive digest STOP; stage still pending

The owner executed the corrected image-only staging check. Its Dell live baseline read-only gate again returned `SERVER_LIVE_BASELINE=PASS_BEFORE`, but local Acer archive verification stopped at `IMAGE_ARCHIVE_CONFIG_DIGEST_DRIFT`, before `UNTAGGED_CANDIDATE_ARCHIVE=PASS`, any SSH transfer, or Docker image load. **No image import or application deployment occurred in this attempt.** The stop output deliberately shows `production_containers_changed: NOT_PROVEN` because a post-stop server audit was not run, not because a production mutation was observed.

Docker 29 containerd stores can expose image IDs as OCI index/manifest digests rather than the classic SHA-256 of config JSON; this is a **hypothesis**, not yet proven for this exact Acer image. Do not relax the image integrity check, reassign image IDs, retag live images or repeat encrypted recovery.

The standalone Acer-only diagnostic `scripts/vision79-v3-image-archive-diagnostic.py`, commit `46094ac960f382d895d84136d8474c6d197c28fd`, SHA-256 `b6cd5a3370a230833bbd4739d2ce073e0ac36e7efec1a5b9530a135c0477619c`, is prepared with four synthetic tests awaiting operator execution. It exports the already approved image into an auto-cleaned local temporary directory and prints only allowlisted digest-relationship booleans, source/command/diffID comparison booleans and STOP markers. It never reaches the Dell, changes Docker, modifies an image tag, or prints image configuration or secret data. On results, update the validator to verify the **right cryptographic identity chain** for this Docker archive format and separately verify staged Dell image ID before considering further release gates.

All prior paired-restore, runtime audit and approved candidate metadata PASS results remain valid. Candidate staging, exact replacement parity, MFA/SSO, visual browser acceptance and production cutover remain `HOLD`.

## 26 October 2026 — OCI identity proven, corrected staging pending

The Acer operator ran the safe local digest-relationship diagnostic. It returned `ACER_ONLY_DIAGNOSTIC_PREFLIGHT=PASS`, `LOCAL_EXPORT_ARCHIVE_REMOVED=PASS`, with these essential properties: OCI blob format; no mutable archive tags; config SHA-256 matches its own OCI blob filename; pinned Docker image ID **does not** equal the config SHA; OCI `index.json` contains a descriptor matching the pinned image ID; a blob under the pinned digest exists; approved Git source and inspected user/entrypoint/command match; all **six** layer DiffIDs match Docker inspect. The diagnostic touched no production system and created no permanent archive. This proves the failed comparator targeted the wrong digest type; it does not yet prove all root/manifest/config references cryptographically.

The isolated staging script on `fix/v79-v3-oci-image-index-20261026` was therefore corrected to verify the pinned image ID through the OCI index descriptor to the content-addressed root manifest/index and on to the exact Docker-save configuration digest and descriptor size. Every visited index/manifest JSON blob is hashed and checked against its OCI digest, with bounded recursion and rejection of missing/tampered blobs, unexpected tags, path traversal, invalid config names and disconnected config. It still checks source image ID and source labels against the pinned approved build on the Acer; the unchanged Dell read-only before/after gate checks the live runtime fingerprint and all five container identities. No image tags, live containers, Compose, mounted data, or application images were altered by these source changes.

Candidate Acer staging checker commit: `e45eeaa2c1f7498baec4ad459aa6249e7477b06a`; checker SHA-256 `afb47d1eea745929ea0a0b95a1985f51df1eed7331361d0919d440dd59627eec`; unchanged Dell gate SHA-256 `e2499c7879e1ecb406809c471364eeb8e33f602341d4d24c720de4907e06f9bd`. **Eleven Acer and six Dell synthetic tests are prepared but not yet operator-run.** Only after tests pass should the owner execute the one image-only staging attempt. Successful stage will cache the image on Dell without deployment; further exact production runtime and MFA/SSO/browser acceptance gates remain `HOLD`.

## 26 October 2026 — APPROVED V3 IMAGE STAGED ON DELL: PASS

The operator executed the checksum-pinned OCI-aware, image-only Acer-to-Dell transfer from source `114841271d4f8b9c4b63df6aedfd55bde2e82f40`. The terminal receipt reports:

- `SERVER_LIVE_BASELINE=PASS_BEFORE`
- `UNTAGGED_CANDIDATE_ARCHIVE=PASS`
- `candidate_image: sha256:960849ef917ac542674b07ccff5fa64a2c68cd0b452346f5c9fb72d1765d97d6`
- `candidate_image_in_dell_cache: true`
- `five_running_container_identities_unchanged: true`
- `live_runtime_fingerprint_unchanged: true`
- `production_containers_changed: false`
- `candidate_started: false`
- `release_gate: HOLD`

**Staging is COMPLETE.** The Dell Docker image cache now contains the exact approved v3 image; existing Hub, Tiquet, Postgres, agent, Docker/Compose runtime, data and user sessions were unaffected by the image-only import. No more source rebuild, archive transfer, encrypted restore, swap toggling or repeated isolated database boot is needed for this pinned candidate unless the baseline changes.

The prior safe gates now have owner-operated PASS evidence: encrypted offhost checkpoint and disconnected paired restore; prior Hub rollback cold boot; current live deep Docker/Compose audit (85 env keys, seven mounts, two networks and full recorded HostConfig bind/mount sources); approved candidate offhost metadata/source and original runtime fingerprint comparison; OCI cryptographic archive validation; five-container-preserving image-only transfer.

**Open release blockers (do not misstate as completed):**
1. Prove the *replacement* container uses precisely the sealed original HostConfig, Binds, Mounts, networks, environment, policy, identity and rollback plan with only the image changed. Static parity helps, but it is not actual replacement-runtime proof.
2. Real owner MFA/session and signed Hub-to-Tiquet SSO browser acceptance on the replacement, including failures/expiry. Previous browser mocks and synthetic isolated smoke are not sufficient.
3. Authenticated browser check that the v3 Owner Assistant/Platform Admin UI matches the owner-approved design (not the older UI), without customer-data leakage.
4. Seal the real production cutover, audit, rollback and checkpoint receipt. Stop the cutover/roll back on any failed owner authentication or browser acceptance.

Release policy: **HOLD / NOT DEPLOYED**. Do not start the candidate on the live customer mounts or change Compose while these gates are unsealed. The next step is targeted runtime/owner acceptance and release transaction preparation, not another recovery cycle.

## 26 October 2026 — static replacement preflight and owner acceptance prepared

The operator's final successful image-only staging report is accepted: `SERVER_LIVE_BASELINE=PASS_BEFORE`, `UNTAGGED_CANDIDATE_ARCHIVE=PASS`, `candidate_image_in_dell_cache=true`, unchanged five service identities and live runtime fingerprint, no containers changed, `candidate_started=false`, and `release_gate=HOLD`. Do not rebuild or restage this image.

On separate branch `release/v79-v3-final-contract-preflight-20261026` the new read-only server script `scripts/vision79-v3-final-static-release-preflight.py` was prepared. Source SHA-256: `32f0ad4e895794f6f37f0e1ff123f15fb86a513b07e92912df3f9656414bc5ab`. Six synthetic tests are **prepared, not yet owner-executed**. The script runs only local Docker inspect/context/info and Compose config on host `v79sl`; it compares current five-service running identity/health, approved candidate source/image, live runtime fingerprint, resolved 85 environment keys, exact seven mounts against Compose, two networks, pinned Compose file SHA, and operational image defaults (user, commands, workdir, stop signal, healthcheck, exposed ports and image-defined volumes). It constructs a *theoretical image-only Compose delta in memory*, emits only safe counts/identity hashes and never deploys or writes secret data. The response will explicitly maintain `exact_recreation_parity_proven=false`, `authenticated_owner_mfa_sso_proven=false`, `live_cutover_authorized=false` and `release_gate=HOLD` even on PASS.

The associated release checklist `docs/release/vision79-v3-owner-cutover-acceptance.md` defines the exact conditions under which owner MFA, signed Tiquet SSO, candidate Owner Assistant/Admin design and session verification should occur **inside a future reversible release window**, and the rollback triggers. It is not an approval or claim that live checks happened. Before any actual switch, seal a fresh encrypted checkpoint and a tested exact runtime restore/rollback transaction. No blind `docker compose up`, `docker run` with live mounts, or speculative rollback commands. Production remains on the prior Hub image.

## 26 October 2026 — static replacement gate PASS; dry-run prepared

The operator executed the SHA-256-verified static release preflight on the Dell; its six synthetic tests passed and the read-only live assessment returned `PASS_STATIC_REPLACEMENT_CONTRACT`. Exact receipt: `approved_candidate_cached=true`, `candidate_critical_image_defaults_match=true`, `current_services_healthy=5`, `live_runtime_fingerprint_matches=true`, `runtime_environment_keys=85`, `mount_destinations=7`, `host_bind_entries=4`, `host_mount_entries=3`, `network_count=2`, `rendered_compose_planned_change=IMAGE_ONLY_IN_MEMORY`, `live_docker_or_compose_modified=false`, `candidate_started=false`, and `release_gate=HOLD`. Five-container identity SHA-256: `fc96149b9d17077a6bb263835e5f043ce3465b95ad958a2fb64e08107d5535b3`.

**Next gate prepared, not yet run:** `scripts/vision79-v3-compose-image-only-dryrun.py` on branch `release/v79-v3-compose-dryrun-20261026`, source commit `9d3481039fc4ec815ca5cd20944ea06edb827d28`, SHA-256 `cd35bc6f4010cff32dfc900aa3b464eba3cfcbb2894e1bb0b518f61269622bb1`, with six local synthetic tests prepared. The server-only checker requires healthy pinned five-container identities, unchanged Hub runtime fingerprint and original Compose file SHA, approved candidate image in cache, and exact original Compose project/config label chain. It creates a mode-0600, short-lived **image-ID-only** override in `/dev/shm`; compares full original and override rendered Compose objects in private memory to prove the **only** effective change is `v79-hub.image`; then runs `docker compose --dry-run up --detach --no-deps --no-build --pull never --force-recreate v79-hub`. Its stdout/stderr, including resolved private config, are never printed; only allowlisted PASS/STOP flags and counts appear. It checks the five original services and Hub fingerprint again before returning, and removes the temporary image-only override. On any drift, STOP without approving release. **Dry-run is not actual Docker replacement runtime parity, owner MFA/SSO or visual browser acceptance.**

The next live action, if dry-run passes, must be a separately sealed reversible **Hub-only** cutover transaction with current checkpoint and deterministic rollback; owner interactive MFA, Tiquet SSO and authenticated visual acceptance remain mandatory. Never use `docker compose up` without the explicit tested transaction/rollback and owner release acceptance. Production unchanged; `release_gate=HOLD`.

## Release sequence

1. Collect and review the current server inventory. Preserve the observed Hub image as the prospective rollback identity; do not assume a historical image remains current.
2. Obtain the current private runtime/Compose contract and verify a fresh encrypted offhost recovery checkpoint against the observed image/data baseline.
3. Build an immutable Hub image from a clean, pinned Git checkout/archive. Do not build from a developer directory containing ignored review artifacts. Record resolved build-base digests and the resulting image ID.
4. Rehearse isolated boot, configuration parity and rollback. Preserve existing database and app images; no migrations belong in this UI release.
5. Complete genuine private-session MFA, session expiry/renewal and Hub-to-Tiquet SSO acceptance. The existing local synthetic tests are not production acceptance evidence.
6. Seal a guarded Hub-only cutover with the exact prior and candidate image/config identities, checkpoint and rollback command. Issue the exact deployment command only after all preceding gates pass.

Production status: **UNCHANGED / NOT DEPLOYED**. Release decision: **HOLD pending current server and recovery/runtime evidence**. Visual approval is complete and must not be requested again unless the visuals change.

## Rollback

No production rollback command is guessed from the earlier visual deployment. That script pins a different source, image, container identity and checkpoint. The final rollback command must come from the new sealed transaction and restore the newly observed prior image with its exact runtime configuration.

The approved application source is unchanged by this release-preparation commit; reverting this preparation would only remove its release records, test-pin reconciliation and read-only inventory helper.
