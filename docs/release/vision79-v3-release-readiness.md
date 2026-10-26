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
