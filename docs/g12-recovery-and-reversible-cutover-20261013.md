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

## Final current status

- **Source/isolated functional CI:** PASS for exact reviewed candidate.
- **Live metadata parity/pinned overlay health:** PASS.
- **Current complete encrypted backup:** NOT VERIFIED.
- **Decrypt + full isolated restore + rollback:** NOT VERIFIED.
- **Live upgraded Hub + Agent browser acceptance:** NOT PERFORMED.
- **Internal test-server cutover:** NO GO.
- **Commercial launch/live WiPay/real customer onboarding:** SEPARATE NO GO.

The user's only permitted *functional* exception is WiPay processing. Data loss, MFA, SSO, tenant separation, manual billing, and app functionality are NOT exceptions.
