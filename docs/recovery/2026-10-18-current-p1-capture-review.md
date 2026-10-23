# Fresh current P1 encrypted capture — approval review

Draft only. No live pause/capture is authorized or executed by this change.
Default execution requests a read-only plan and prints a digest plus the exact
active workforce/release/task timer names that a capture would pause. The old
frozen rollout plan is never consumed. Previously accepted backups stay intact.

## Alternatives and selection

1. Reuse the old release snapshot as current: rejected; image coverage differs.
2. Capture live-changing files and independently dumped databases as if atomic:
   rejected; cross-store consistency is unproven.
3. New P1-only checkpoint with reviewed identities, short quiesce and same-ID
   app resume: selected, subject to explicit owner approval after read-only plan.

## Reviewable action

- Verify current Hub/Tiquet app images against accepted release receipt, PG17/16
  image IDs, health, actual ordered Compose files, rendered storage/network/env
  parity, MFA exact flag1, legacy login disabled and matching SSO keys.
- Reject unreviewed app mount destinations and other running writable container
  overlaps. Check PG dump versions/readiness and idle original active timers.
- Bind approval to SHA256 of current container IDs/full runtime fingerprints,
  configuration hashes and timer list. Resource availability is checked again.
- Export current app and database images to encrypted storage BEFORE pausing.
- On a separately approved capture command, pause only the listed originally
  active workforce/release/task timers and the two app containers. DB containers
  remain running. No deployment, recreate, image switch or database restore.
- Stream two custom-format logical dumps and all reviewed app mounts, including
  secret-file mounts and reports, directly into public-recipient GPG ciphertext.
  Store original runtime, frozen current Compose, source Compose/env inputs and
  input map inside an encrypted archive assembled in RAM. No plaintext files.
- Data-capture budget600seconds; each stream uses remaining budget capped300s.
  Image export is outside downtime. Same-ID app resume/health may need additional
  time (up to180seconds per app), so this is NOT a guaranteed ten-minute outage.
- Always attempt reverse-order same-ID resume after handled pause/capture failure.
  Resume original timers only when app restoration is proven. Never restore data
  automatically. SIGKILL, power or host failure requires manual recovery.
- Before pause, write a private public-identity/runtime-digest journal with no
  environment values/customer data. Approval-gated resume-apps mode validates
  same helper, receipt image, immutable IDs and fingerprint digests before start.
- Emit manifest only after apps are same IDs/healthy, original runtime/config
  unchanged and unrelated containers unchanged. Copy ciphertext to a new private
  Acer directory; verify hashes and full decrypt to a sink using reviewed utility.
- Capture/decrypt success remains NOT_RESTORE_TESTED and commercial NO_GO.

## Security and operational limits

The helper reuses only pinned utility functions (fingerprints, current Compose
reconciliation, crypto/monitoring), never old rollout/continue functions or plans.
The private decryption key remains on Acer. Existing production OS/swap settings
are unchanged; the guarantee is no plaintext archive files, not no memory paging.
The owner must avoid concurrent manual data/config/key changes during the window.
Non-container host writers beyond the reviewed timers are not universally
discoverable. Refuse capture if an unexpected writer is identified.

Read-only plan is the next operator step. Review its exact digest, mount counts
and timer names before authorizing any pause. A plan failure changes nothing.
Restore-to-boot, original identity/MFA, SSO and rollback acceptance require separate
isolated RAM-only exercises; no production restore is implied.
