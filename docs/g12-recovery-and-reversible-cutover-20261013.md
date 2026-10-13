# G1.2 Internal Hub release — exact live recovery and reversible cutover plan
Date: 2026-10-13. **DRAFT / NO GO**. This is a reviewed-operator runbook, not authorization or proof of completion.

## What is proven

- Owner browser report says the *current live* Hub works, including MFA, admin, assigned app launches, and Owner Assistant.
- Four key live containers are healthy, and their image digests have been recorded in Issue #138.
- Hub Compose actually runs with BOTH `/opt/v79/hub/docker-compose.yml` and `/opt/v79/hub/releases/wipay-return-585f701.pinned.yml`; exact pinned override SHA-256 is `8aa57bba2c6955ab5affe5394ed7bec2b9b2693bc05556db3bef0420bcc04b74`.
- Hub is `v79-hub`, image `sha256:7876715a44166c1cbeb6b5070a774efb4d69fe36427bda1c4dee4fc637c67e30`.
- Hub database is `v79-hub-postgres`, image `sha256:b0f9560a2de083e2cc7382e75f808c7381a32852a7ec49117deedb300e552b24`.
- Live Business Agent is `v79-business-agent`, image `sha256:ff64a76651a2b784474f5d7430d0d78515bc7b46b2d0d1f81c51c79958ef417b`. Live Agent source differs from G1.2 pilot and lacks new executive modules: account for an intentionally coupled application update.
- Tiquet is `v79-tiquet-manager`, image `sha256:ee3deff332977160d66e0dbb448aef1e1e6d4418eac333e1feaf8a07c044715b`, under a SEPARATE `v79tiquet` Compose project with Tiquet-specific overrides; must not be reconstructed from the Hub checkout.
- Historical Oct 10 focused checkpoint includes database-only isolated restore evidence recorded in Issue #113, but the CURRENT available archives are not verified as complete encrypted recoveries. Oct 12 issue-128 archives have encrypted-looking extensions, not proven decryption or full applicability.
- G1.2 draft PR #143 SHA `f5ab6c20b2b8bf024c410d57df8cb560ddcef73c` passed full Hub CI, 345 root tests, 69 agent tests, isolated real Hub↔real Business Agent MFA/CEO/COO, PostgreSQL concurrency, and real five-app synthetic SSO staging. Any later SHA must obtain fresh all-green evidence.

## Phase 0: non-mutating prerequisite discovery (owner action needed)

- Run `scripts/g12-encrypted-recovery-prerequisites-readonly.py` from this exact Git commit on `v79sl` through an authenticated, strict-host-key SSH session. The script does not back up, restore, or disclose env values.
- Verify the exact four running image IDs and pinned override hash are unchanged, every service healthy, and discover the SINGLE Tiquet PostgreSQL container by *actual Compose project + service*, not guessed container name.
- Inspect mount *destinations* and named volumes for Hub/Tiquet, and check `pg_dump`+`pg_restore` readiness without exporting credentials. Check `age` or `gpg` presence and free disk space.
- HOLD if the database, volume or cryptography tool cannot be unambiguously established. The command deliberately returns exit 3 even when prerequisite checks are true; zero is not an approval signal.
- Preserve original `/opt/v79/hub/.env`, Hub data bind mount and runtime tokens; do not print or paste their contents.

## Phase 1: owner-authorized encrypted immutable recovery point

**No actions in Phase 1 may start until the operator selects an externally recoverable public encryption recipient, confirms key custody OFF the Dell (for example on the Acer), and approves source-specific scope.** Encryption is NOT satisfied by a `.gpg` filename. Do NOT download plaintext secrets or copies of live databases to GitHub, chat, CI, Acer Downloads or any public ingress.

Under a separately reviewed narrowly scoped script, with `umask 077`, validated exact runtime mounts and enough free space:

1. Record SHA-256 and absolute immutable image IDs for current Hub, DB, Agent, Tiquet; preserve a locally usable rollback image archive for EACH application being replaced. Include Tiquet's separate pinned Compose and Hub's exact WiPay override.
2. Capture a transaction-consistent logical PostgreSQL `pg_dump --format=custom` of EACH exact relevant Hub/Tiquet DB while live, encrypted **as it streams** to owner-held public recipient. Different database snapshots are NOT cross-app atomic: identify a quiet/frozen mutation window or track an acceptable recovery point.
3. Encrypt and capture the **allowlisted** runtime bind-mount contents, app code/config, secret-file dependencies, token metadata and actual Compose configurations; NEVER put raw `docker inspect` JSON or `docker compose config` plaintext in logs/artifacts, since both can expose credentials.
4. Write a signed/hashed metadata manifest and backup provenance (UTC timestamp, db engine versions, encrypted archive hashes, exact image IDs, source file digests, environment boundaries) without logging secrets. Verify every expected artifact exists, is nonzero and checksum-valid. Do NOT tag old images for overwrite or delete stale backups.
5. Retain the full recovery point outside the application write paths. Note that a backup retained only on the Dell is vulnerable to whole-host failure; offsite backup remains a separate decision.

**RPO note:** Logical dumps and files captured at different instants are not a single multi-service transaction. Final cutover should occur during an operator-approved quiet/maintenance window and record the bounded timestamp gap.

## Phase 2: independently isolated encrypted restore and exact rollback rehearsal

- Decrypt the NEW complete backup using the owner-controlled private key (do not disclose the key), into a fresh disposable restricted workspace. Verify signature/hash before restoring.
- Start only independent temporary database containers, with NEW names, project ID, private volumes and a Docker network with no published ports and no connection to `proxy_network` or live `v79-hub_hub_data_network`. Never mount live paths, live databases or live app tokens read-write.
- Restore both PostgreSQL dumps into isolated DBs. Verify schema/object counts, integrity/foreign keys, aggregate audit/organization/plan/grant counts, historical trial and billing state, plus an allowlisted SHA-256 of authenticated data obtained without exposing individual user records.
- Reconstruct recovered static config, secrets (restricted test-only copies), preserved app images, and both Compose stacks in isolated mode; probe strict owner authentication/MFA, existing accounts, SSO, full non-WiPay billing functionality and CEO/COO, with test egress prevented. Do NOT send real email, charge money or touch a real tenant.
- Rehearse **exact pinned** rollback for Hub and original live Agent while the current live production/test Hub continues serving. Record expected rollback downtime/recovery time. DO NOT restore backup into the currently running Hub as a rehearsal.
- Tear down only positively identified ephemeral resources after proof is saved and exact-owner approval; no generic `docker system prune`, no wildcard rm, no persistent data deletion.

## Phase 3: separate internal test-server cutover decision

Required **all**: owner reviews exact new SHA, independent source/runtime diff and relevant security review, current and recoverable backups, isolated restore report, immutable old image archives, pinned override and secrets continuity, rollback rehearsal PASS, all-green CI and five-app smoke, and a written scoped cutover decision.

Then ONLY within a maintenance window, with rollback immediately available, apply the approved exact Hub/Agent delta without touching Tiquet's independent Compose stack or the WiPay overlay. Keep Sentinel machine permissions OFF and manual monetary settlement NON-LIVE. Verify owner login/MFA, Hub management, Tiquet/POS/FFPRO/Marketing/Academy launch UX, billing/manual screens, trials, Reset/Resend mail, CEO/COO against REAL source provenance, mobile view, and tenant denial. A failure in ANY non-WiPay feature means stop and restore the exact prior runtime.

**Never run generic `scripts/deploy-server.sh`, generic ecosystem deployment or a plain `docker compose up -d --build` on the pinned release.** These paths are not certified to preserve the active WiPay override, release images and Tiquet overlays.


## Actual checkpoint progress — 2026-10-13 (supersedes older planned-status bullets)

**Evidence from founder/operator transcripts, not an independent end-to-end application restore.** The original "Final current status" section below is historical at the time of the initial design; this section records subsequent evidence.

- Encrypted GPG public/private key flow: Acer-generated key `484CF39CE37A02884497AD9C41A17102D2842ECE`; Acer private key preserved and independently AES-256 backup-encrypted to hardware-identified Kingston USB; server-side public-key ciphertext decrypted on Acer, `KEY_RECIPIENT_ROUNDTRIP_VERIFIED`.
- Narrowly owner-approved 14-artifact encrypted Hub/Tiquet checkpoint created on server at `/home/firelion/.v79-g12-encrypted-recovery/g12-20261013T144536Z-3589644` using audited draft SHA `d42010aada290817be07353979343f29415e9da7`. Contains both PostgreSQL custom dumps, three app data/upload tar snapshots, runtime configs and relevant secrets, resolved Hub Compose, live runtime inspect, and exactly five saved Docker image archives.
- 14/14 archive SHA-256 hashes and recorded manifest checked; checkpoint ~743MiB. Both PostgreSQL archives stream-decrypted with Acer-only private GPG key; PGDMP magic and full stream consumption verified.
- Isolated restored DBs using original cached PostgreSQL images, `--network none`, read-only root, tmpfs data and no persistent binds/volumes. **Hub: 1 business table, 2 app constraints; Tiquet: 24 business tables, 51 app constraints.** Scratch containers auto-removed and confirmed. Hub PG single state-JSONB table is expected by source; running `V79_HUB_STORE_BACKEND=postgres`, not JSON.
- Decrypted application archive listings: Hub 10 entries including auxiliary JSON, POS signing key, Agent runtime token; Tiquet app data 21 entries, uploads 9, combined configuration 6 including exact live Tiquet `/home/firelion/V79Tiquet/.env`.
- All five encrypted rollback-image tar streams decrypted on Acer and passed Docker-save structural listing: Hub 21 entries, Hub PG 22, Business Agent 21, Tiquet 23, Tiquet PG 23. **Tar listing does not prove image import/operational startup.**
- No live service restart, application deployment, secret leak, `main` merge, or data restore into live resources reported. Live WiPay overlay unchanged during earlier preflight; fresh parity required before cutover.

### Verified operator recovery evidence — updated 2026-10-13

The evidence below **supersedes the older TAR-listing-only and "NOT VERIFIED" statements** in this draft. All observed outputs were supplied by the founder from an independent Zorin OS Acer; they are not a full Docker-engine rollback or authorization to deploy.

| Gate | Observed result | Boundary |
|---|---|---|
| Encrypted checkpoint integrity | 14/14 ciphertext SHA-256 checks PASS | Does not establish atomic multi-app capture or off-host backup of full checkpoint |
| Exact saved-image import | All five encrypted images IMPORTED using Acer rootless Podman and LUKS2-backed storage; 0 failures | Importer is **Podman**, not a recovery rehearsal using the Dell's Docker Engine 29 |
| Image filesystem equivalence | All five imported `linux/amd64` images' RootFS layer fingerprints MATCH the running Docker images | Metadata/OCI manifest IDs and run configuration not necessarily identical |
| DB and application data recovery | Both encrypted PostgreSQL dumps and Hub/Tiquet application-file snapshots restored into temporary offline containers | No live accounts/databases touched; original owner key/session identity not validated |
| Recovered application execution | Hub and Tiquet started, both local health checks PASS; two DB schema-shape checks PASS; five protected anonymous API requests correctly returned 401 | Hub Business Agent not started from recovery in this run; no current-owner MFA, live billing, real SSO or UI browser acceptance |
| Network isolation | Podman network-disabled namespace; no published ports, no real external calls | Egress control reported by the executed recovery script |
| Recovery cleanup | Exact-scoped temporary recovery containers removed; original Acer `/swapfile` restored | Hub/Tiquet required SIGKILL after the 10-second SIGTERM timeout; this did not prevent removal |
| Release | All prior production images, Hub/Tiquet services, accounts, and pinned WiPay overlay preserved | No candidate G1.2 image deployed; **NO-GO** |

Observed final console evidence: `IMPORTS_PASSED=5`, `IMPORTS_FAILED=0`, `IMPORTED_IMAGES_MATCH_LIVE_ROOTFS=5/5`, `IMPORTED_IMAGES_AND_CHECKPOINT_CORE_APPLICATION_OFFLINE_RECOVERY_PASS`, `ISOLATED_RECOVERY_CONTAINERS_REMOVED` and `ACER_SWAP_RESTORED=YES`. Source-of-truth incident notes and operator transcripts are maintained in issue #138.

Independent off-Acer GPG private-key escrow is described elsewhere in this draft as an AES-256-wrapped Kingston USB copy; **do not treat possession as sufficient disaster-recovery proof without independently testing the secondary copy and recovery procedure**. The full encrypted 14-artifact checkpoint itself remains on the V79 Dell: whole-host disaster recovery would also need a protected off-server checkpoint copy. Do not copy decryption keys, raw secrets or plaintext backup data into GitHub or issue comments.

### Remaining gates — still NO GO

1. **Business Agent and candidate integration**: Verify the backed-up Business Agent actually starts with safe isolated dependencies; then run the exact reconciled G1.2 candidate against disposable Hub/Tiquet and agent test instances. The archived old Hub/Tiquet startup PASS must not be mistaken for candidate G1.2 acceptance.
2. **Data fidelity and authenticated function**: Verify sensitive restored owner MFA decryptability without displaying secrets, tenant authorization, trials, SSO, synthetic manual billing and agent capability boundaries. Preserve live accounts and block real payments/email during tests. Synthetic positive MFA and signed SSO were previously proven only in disposable scratch tests.
3. **Exact Docker-native reversible cutover**: Separately validate the old pinned Docker image references and full runtime/Compose environment including the immutable WiPay override; rehearse safe return to old Hub and Business Agent from a separate environment. Matching root filesystem layers in Acer Podman is not exact Docker rollback proof.
4. **Independent source/security review, F01–F16 browser acceptance and founder exact-SHA sign-off**: GitHub CI passed for draft head `bb88d7cfff3df218916d180db14154342cac31e9` (root CI, isolated smoke, five-app disposable staging), but no upgrade or live browser acceptance has occurred. Keep PR #143 draft, `main` unchanged and the live system untouched until approval.


**Caveat:** These backups were captured at different times; database and file snapshots are not cross-app atomic. The full 743MiB encrypted application checkpoint is on the Dell, not on the Kingston USB (the USB has only private-key escrow); whole-server disaster recovery requires a separate off-host encrypted copy.

---

## Latest gate status (supersedes original pre-checkpoint status)

- **G1.2 draft PR #143 at `bb88d7c`**: Three GitHub workflows passed; PR remains DRAFT/UNMERGED.
- **Encrypted checkpoint integrity**: 14/14 ciphertext hashes PASS; five saved image archives independently imported on Acer.
- **Recovered running-image filesystem parity**: 5/5 PASS by `RootFS.Layers` and platform; not byte-identical metadata nor a Docker-native rollback claim.
- **Hub + Tiquet core restore and offline startup**: PASS with restored PostgreSQL and application data, health, schema checks and anonymous authorization denial; exact-scoped cleanup and Acer swap restoration PASS.
- **Business Agent recovery, current-owner MFA and full billing/SSO against original identities**: OPEN.
- **Exact Docker/Compose/WiPay rollback, candidate G1.2 integration + full desktop/mobile acceptance**: OPEN.
- **Off-host recovery readiness**: Claimed independent key escrow must be recovery-tested; full encrypted checkpoint copy exists on Dell only.
- **Internal test-server cutover**: **NO GO**.
- **Commercial customer activation / live WiPay**: **SEPARATE NO GO**.

The founder's only permitted **functional** internal-test exception is WiPay processing; backups, MFA, tenancy, manual billing and non-WiPay capabilities are not waived.
