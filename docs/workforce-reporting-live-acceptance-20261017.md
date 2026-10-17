# Workforce reporting live acceptance

Accepted by owner 16 October 2026, approximately 20:41 America/St_Lucia (17 October UTC).

## Live result
Hub runs exact image `sha256:4a9f5868b8c5b7df818225478fc56836e9e6acf9e19c2a8c6faeebe58cec1698`, built from application source commit `5c13dc9612752f896ef5cb2e8c1da63c0cfd8e04` atop the exact prior live image. GitHub runs 38983532531 and 38983532546 passed for that application source. Later commits add operator/recovery scripts; they are not falsely attributed to the running image.

Owner confirmed normal live login/MFA after disabled cutover, then confirmed opening both briefing reports after explicit report activation. Runtime reader returned two reports; unauthenticated route access was denied; Hub healthy; Agent/Tiquet retained their existing container identities and healthy images. No new scheduler, worker activation or autonomous execution was enabled.

Host systemd retains 08:00 and 19:00 Saint Lucia reporting. Evening generation was observed; next-morning execution, report email delivery, six specialist integrations and full CEO/COO workflow are not certified by this release.

## Release and recovery evidence
Original 97 tracked Hub runtime/build inputs matched G3 baseline `ffae1c104d6ded918a0028f92c76624bc0501d8b`. Effective environment/mount parity and all nine original ordered Compose files passed. Candidate added only image, report flag and narrow read-only report mount. Disabled-image cutover preceded the separate one-flag activation.

Private release plan: `/home/firelion/v79-workforce-release-plan.dhc2pyxi`. Original-image rollback command: `rollback-command.txt`; same-image report-disable command: `disable-reports-command.txt`. Current stack includes all nine originals, disabled overlay and enable-flag overlay. Do not use a bare Compose invocation.

Acer encrypted checkpoint: `/home/firelion/v79-workforce-recovery.S8V7f4nD`. Five encrypted archives passed checksums and decrypt/archive checks. Disposable PostgreSQL restoration succeeded (one user table); data and configuration extraction restored 10 and 14 files respectively. Temporary resources were removed and live image/health rechecked. Corrected OCI checker then verified all 16 archived blobs and the reachable index/manifest/config/layer graph against original live image `sha256:33a357c6c73f45ef05edcef57c6c0abf9234022cbec1c30041c463b2f3ff8d06`. Full Docker image reload and complete app restoration from the backup were not performed. Earlier image-config-only checker failed because this Docker image identity refers to an OCI index, not its config blob.

## Next bounded step
COO GitHub workboard code is present but disabled and has no credential/mount established in this session. Use a separate fine-grained token restricted to the six fixed repositories and read-only issues/pull requests. Never reuse platform, payment, administrator, or broad GitHub write credentials. Only owner-MFA requests may read it. GitHub state cannot certify runtime health, actual deployment or Sentinel monitoring. Task preparation remains a local owner draft; the existing G2 queue still requires its own explicit approval.

Canonical integration remains PR #156. PR #155 is an unmerged source predecessor/alternative: do not merge both independently. Customer launch and Sentinel security holds remain separate.
