# P1-R1 encrypted Hub + Tiquet capture — owner runbook

Status: DRAFT SOURCE. Not executed against the server. No customer GO or production deployment permission.

## Boundaries
* Live server: read-only Docker inspect, PostgreSQL pg_dump, read-only tar of current files, Docker image save. Never restart, mutate database, remove images, copy unencrypted files to disk or expose secrets in output.
* Acer: each captured stream encrypted immediately under GPG recipient fingerprint 484CF39CE37A02884497AD9C41A17102D2842ECE, in a unique 0700 private folder with 0600 files. All prior backups left untouched.
* Current pinned image identities: Hub d0dfba26..., Tiquet 5e69de60..., Hub PostgreSQL b0f9560a..., Tiquet PostgreSQL cf78e766..., and prior Hub 4a9f5868.... Full IDs are embedded.
* Latest live Acer check: old revision bc1d5908 SELF_TEST=PASS, but --plan failed with REMOTE_UNREVIEWED_APP_MOUNT. Hub base Compose declares token-file mounts outside /app under /run/secrets. The updated allowlist covers only explicitly reviewed Hub token and workforce-report mount destinations, with bind type and RW=false. No wildcard /run/secrets access, no unknown mounts, and no Tiquet secret allowlisting.
* A reviewed secret mount is captured through Docker exec only if it is a regular non-symlink file; a /dev/null placeholder or unreadable token is a controlled STOP, not ignored. The resulting stream is encrypted on Acer, with no plaintext token logged or stored.
* If the updated --plan still reports REMOTE_UNREVIEWED_APP_MOUNT, inspect only each container's Docker mount destination, kind, and RW status; never print the mount Source, container Env, Docker inspect JSON or token contents. Do not change the script allowlist until the actual destination is reviewed.
* Latest Acer diagnostic confirmed exactly six Hub mounts and two Tiquet mounts, with no host source paths or secret values exposed. Hub data: /app/data (bind, RW=true). Hub workforce reports: /run/v79-workforce-reports (bind, RW=false). Hub secret files: /run/secrets/v79-agent-token, /run/secrets/v79-coo-github-token, /run/secrets/v79-readonly-platform-token and /run/secrets/v79-workforce-token (all bind, RW=false). Tiquet data: /app/data and /app/uploads (both volumes, RW=true).
* The second strict allowlist update now permits only those exact four read-only Hub secret-file destinations plus the exact read-only Hub workforce reports directory. The report destination is checked as a real non-symlink directory; tokens are checked as regular non-symlink files. Files and reports are encrypted directly through GPG as separate archive streams, with no token contents printed. Extra/changed mounts still block the preflight.
* Current corrected preflight now runs read-only `docker exec` file-type checks on Hub before authorizing a capture: four allowed /run/secrets token destinations must be regular, readable non-symlink files, and /run/v79-workforce-reports must be a readable non-symlink directory. Failures report only REVIEWED_TOKEN_FILE_UNAVAILABLE or REVIEWED_REPORT_DIRECTORY_UNAVAILABLE; no contents, Source paths or environment values are emitted.
* Source-only test evidence for the exact allowlist and file-type checks: CI run 39000143463 (PASS). It does not prove that the Acer's next live --plan succeeds.
* Hub Compose currently has thirteen layers. The old audit printed only **63 hex characters** for the sixth layer (g3-hub-disabled.yml): not a valid SHA-256. The other twelve are pinned. The operator must obtain a new full 64-character sixth-layer hash via --plan, then explicitly accept exactly that hash when authorizing capture.

## Read-only smoke and exact pin
1. Retrieve the immutable reviewed branch via GitHub draft PR #158: https://github.com/MrFixITslu/V79hub/pull/158
2. Confirm the exact reviewed commit with git rev-parse HEAD. Do not execute a moving branch head without reviewing it.
3. Run syntax/self-test:
   python3 -B scripts/p1-r1-offhost-capture.py --self-test
   python3 -B tests/p1-r1-offhost-capture.test.py -v
4. From Acer run:
   python3 -B scripts/p1-r1-offhost-capture.py --plan
5. The plan performs no database dumps, container changes or archive writes; it uses metadata-only checks inside the existing Hub container for the five scoped read-only mounts. Expect LIVE_PIN_AND_SECURITY=PASS, HUB_COMPOSE_LAYERS=12_PINNED_1_NEEDS_REPIN, a newly computed full HUB_COMPOSE_LAYER_6_SHA256, app mount count, stream count, MODE=READ_ONLY_PLAN_NO_BACKUPS_CREATED. This does not create backups.

STOP for any drift, missing .env, unreviewed mount, missing image, unhealthy service or config error. Do not bypass the checks. Inspect the new SHA-256 (64 hex characters).

## Owner-approved capture on Acer
Once the new layer-six hash is reviewed, use the exact value in:

    python3 -B scripts/p1-r1-offhost-capture.py \
      --capture --approve-live-reads \
      --accept-layer-6-sha FULL_64_HEX_FROM_PLAN

This streams both PostgreSQL logical dumps, both Compose/environment config sets, each /app-mounted data destination, four strictly recognized Hub token files and its read-only workforce reports directory, credential-bearing Docker inspect metadata encrypted, and a Docker image archive of four current images plus the previous Hub rollback image. It does not touch customer APIs or change production.

On success the operator sees:
- ACER_RECOVERY_SET=/home/firelion/V79-P1-R1-Offhost/p1-r1-current-release-...
- ENCRYPTED_OFFHOST_CAPTURE=PASS_STREAMS_ONLY
- DECRYPT_STRUCTURE_VALIDATION=NOT_YET_RUN
- ISOLATED_RESTORE=NOT_PERFORMED
- RELEASE_GATE=NO_GO

If anything fails, CAPTURE_INCOMPLETE remains in the newly created off-host directory; all ciphertext is preserved but the set is NOT accepted.

## Offline ciphertext checksum and decrypt-structure validation
Once complete, provide the exact recovery directory:

    python3 -B scripts/p1-r1-offhost-capture.py --verify \
      /home/firelion/V79-P1-R1-Offhost/p1-r1-current-release-EXACT_ID

The --verify action compares encrypted SHA256 and byte sizes against the manifest, and streams GPG-decrypted bytes only through validators (pg_restore --list / tar list / JSON parser), not to disk. This is NOT a full restore, not an OCI image graph verification and not an app-boot verification.

## Verification repair after successful 14-stream capture (2026-10-16)

Founder Acer capture completed all 14 encrypted streams under `/home/firelion/V79-P1-R1-Offhost/p1-r1-current-release-rmtdrog_`, reporting `ENCRYPTED_OFFHOST_CAPTURE=PASS_STREAMS_ONLY` with the post-capture image/Compose recheck PASS. The initial `--verify` returned `STOP=ENCRYPTED_ARCHIVE_VALIDATION_FAILED`, without naming the archive. **Preserve the directory; do not recapture, overwrite, reset keys or alter the manifest.**

The previous verifier piped GPG output directly into `pg_restore --list`. Because a table-of-contents inspection can stop reading early, GPG can receive SIGPIPE; it also called whichever `pg_restore` was in PATH, even though Hub now uses PostgreSQL **17** and the last known Acer binary was **16**. These are plausible verifier failures, not demonstrated archive corruption. The corrected `--verify` (source-only, same draft branch) now:

- Verifies the SHA-256, file size and manifest component identity of all 14 existing ciphertext files before reporting each known safe component name.
- Drains every byte of GPG output even when a metadata validator exits early, without writing decrypted data to disk.
- Requires a local PostgreSQL client **17 or later** to structurally inspect the Hub database archive, and **16 or later** for Tiquet. It checks `/usr/lib/postgresql/17/bin/pg_restore`, `/usr/lib/postgresql/18/bin/pg_restore`, and `pg_restore` from PATH. No packages are installed and no server connection is made.
- If the needed client is missing, **still fully decrypts and verifies GPG integrity** for that archive but reports `PG_STRUCTURE=DEFERRED_CLIENT_17`. It continues verifying the remaining encrypted files, then deliberately returns nonzero with `POSTGRES_CLIENT_REQUIRED=hub-pg.dump.gpg` and `RELEASE_GATE=NO_GO`.
- On full successful structural validation prints `OFFHOST_CIPHERTEXT_SHA_AND_DECRYPT_STRUCTURE=PASS` and `VERIFIED_STREAMS=14`, but **not** full app restoration or production GO.

To rerun after pinning the corrected Git commit, use `python3 -B scripts/p1-r1-offhost-capture.py --verify /home/firelion/V79-P1-R1-Offhost/p1-r1-current-release-rmtdrog_`. **Never** rerun `--capture` just because `--verify` failed.

## Known limitations and next gate
- Data copied from actively written application-mounted files is not an atomic filesystem snapshot. Actual logical DB dumps are individually consistent, but Hub/Tiquet are not a cross-database atomic point-in-time backup. Isolated restore plus targeted application smoke remains mandatory.
- Capture assumes project .env and Compose files plus all /app mounts cover the app config; independently review unusual bind secrets, supplemental env_file sources and external token files before declaring completeness.
- Historical Tiquet rollback image identity is not verified; the saved current Tiquet image is not a Tiquet downgrade/rollback rehearsal.
- Actual isolated full restore, Hub MFA, Hub-to-Tiquet SSO, synthetic tenant separation and rollback boot require separately scoped tests without production networking or mounts.
- Independent security assessment and founder customer GO are separate hard gates.
- Do not run the old workforce-offhost-backup.sh or workforce-recovery-rehearsal.py: they pin obsolete Hub image 33a357... and nine Compose layers.
- Capturing large images can impose live CPU, disk, and LAN load. Use an operationally appropriate supervised window.

All instructions refer to source-only draft PR #158 and carry NO automatic merge/deploy authorization.


## 17 October 2026 — independent synthetic PostgreSQL 17 + GPG streaming rehearsal

A new **nondeploying GitHub-hosted** test checks the actual unchanged `drain_and_validate` function against a real disposable PostgreSQL **17** `pg_dump -Fc` archive symmetrically encrypted with a **synthetic CI-only GPG key phrase**. Its test DB contains only one synthetic integer row. A PostgreSQL 17 `pg_restore --list` reads and validates the decrypted TOC over stdin. It additionally verifies that a validator which reads only the first five bytes cannot SIGPIPE-short-circuit the GPG stream, and detects tampered/truncated ciphertext.

**[GitHub CI run #39024998586](https://github.com/MrFixITslu/V79hub/actions/runs/39024998586) — PASS, all 4 tests.** Existing independent [offhost-capture synthetic CI #39024998593](https://github.com/MrFixITslu/V79hub/actions/runs/39024998593) also PASS. Code is on draft PR #158 only, with no server/Acer access, production restore, GPG owner key or captured archive read.

The initial CI-only test run failed because `pg_isready` saw PostgreSQL's bootstrap process before its named synthetic database existed. It was fixed to wait for a successful `SELECT 1` against the exact fixture DB; the recovery capture/verifier implementation itself **was not changed**. This is a **CI fixture timing correction**, not evidence of backup integrity failure.

**Unchanged blocked live gate:** the 14 original encrypted Acer streams under `/home/firelion/V79-P1-R1-Offhost/p1-r1-current-release-rmtdrog_` still require an actual `--verify` with a compatible **local PostgreSQL 17+ pg_restore**, followed by independent isolated full-app restore/boot and rollback. Existing captures must not be overwritten or re-created based solely on the former verification failure. Synthetic CI validation cannot certify those bytes or any customer-launch recovery promise.
