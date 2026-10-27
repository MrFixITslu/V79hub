# Vision79 full-server backup and drive-failure recovery

27 October 2026 · DRAFT / capture script prepared; execution pending · Do not claim a completed whole-server backup or restore.

## Decision and /REDTEAM

1. **Offline disk image only:** fastest like-for-like drive replacement, but needs downtime and a disk/image destination at least as large as the used source; it ages between images and does not prove app consistency while mounted.
2. **Application-aware backup only:** efficient daily offhost recovery of databases, files, configuration and images, but needs a fresh OS/Docker installation and an exact dependency/order map after disk failure.
3. **Combined (chosen):** encrypted, verified application-aware copies every day plus a periodic offline disk image to a separate physical device. The disk image is an accelerator, not a substitute for current database dumps.

Risk controls: do not archive live PostgreSQL data directories as the primary restore source; use consistent logical dumps (roles plus every database) with server/client version recorded. Coordinate write-heavy file stores and Redis with an app-consistency window or supported snapshot. Copy all bind mounts, named volumes, secrets, Compose inputs, Nginx Proxy Manager data/certificates, host configuration and exact non-rebuildable images. Use an offhost destination and encryption key stored separately. Avoid printing config/env values. Prevent restored sandbox callbacks, scheduled jobs or emails from running twice. Preserve payment/audit ledgers; never restore old state over a server that continued taking real payments. Do not put the only backup on the Dell's failing drive.

## Current evidence and open preflight

- 27 Oct live inventory: 44 Docker container objects; accepted Hub and Tiquet plus their PostgreSQL services healthy. It is not a complete backup manifest. A historical Dell checkpoint has 16 sampled encrypted items; earlier Hub/Tiquet offhost 14/14 decryption and isolated two-DB restore passed on Acer.
- The first checked Dell path `/home/firelion/ServerBackups/v79sl` was absent; the Sep 14 daily-backup location/schedule is historical and may be on another device or no longer active. No automatic whole-server backup schedule was established.
- Run `scripts/v79-full-recovery-preflight-20261027.py` read-only to enumerate **all** current containers, bind sources by hash, named volumes, database candidates and free Dell space. Check Acer/external target free bytes, filesystem and encryption key separately before capture.
- Record a private manifest mapping every actual bind source and volume to service, backup method, consistency protocol and restore destination. The sanitized preflight alone intentionally omits source paths.
- Establish current physical disk/partition/boot mode, `/etc/fstab`, network settings, package versions, Docker/Compose versions, firewall and Tailscale onboarding in an encrypted configuration stream. Treat SSH host keys and Tailscale machine state as sensitive; on a replacement machine, decide whether to re-enrol rather than blindly cloning identity.

## First full backup transaction (not executed)

1. Choose an **offhost** destination with enough free space for all database dumps, bind mounts, volumes, configuration and selected immutable image archives, with headroom. Prefer an encrypted external drive attached to Acer or the spare PowerEdge R430, not a directory on the Dell. Record destination device ID and free bytes without publishing serials.
2. Validate the dedicated GPG recovery public key on Dell and the corresponding private key on the recovery machine. Confirm a second, owner-controlled copy of the private key/passphrase exists. Never include the private key in the backup.
3. Pin the current image IDs, container IDs, Compose file hashes, mount identities and destination; stop if they change during the capture. Capture a nonsecret manifest and capture time. Inventory *all* Docker volumes, including stopped historical containers, but distinguish active production from obsolete stages.
4. Stream database roles/globals and every PostgreSQL database as format-custom logical dumps to encryption without plaintext files. For POS Redis, determine persistence mode and take a supported consistent snapshot. Quiesce or snapshot file-backed services during a bounded window if their files can change while copied; do not infer consistency from a successful `tar`.
5. Stream each unique non-database bind source and Docker volume once, preserving ownership, modes and symlinks. Include Academy `/app/data`, website/marketing/FFPRO/POS/Hub/Tiquet/Sentinel/Portainer/proxy state as applicable from the live manifest. Capture configuration, env/secrets, certificates, host service definitions, backup scripts, image digests and required image archives. Exclude recreatable Docker overlay layers and runtime caches unless the manifest shows unique data there.
6. Write ciphertext to the offhost destination with restrictive permissions. Hash every ciphertext item and retain the manifest on trusted storage. Recheck live identities and service health. Mark the capture **INCOMPLETE** on any failed source, changed identity, missing item or encryption/hash error.
7. Offhost: verify every hash; decrypt every item in a controlled environment and validate archive structure and database dump listing. This proves readable archives, **not** restored apps. Keep two independent copies on different devices/locations, with retention and an owner-held key recovery process.

### Acer capture command (owner runs, no production restart)

Use the Acer terminal in a persistent `tmux` session if available. The command pins the exact draft revision and SHA-256 for both scripts, runs the two local safety tests, and writes encrypted streams to `~/V79-Full-Recovery/full-<UTC>-<random>/`. It requires at least 140 GiB free at start and stops new items below a 100 GiB reserve. It will fail closed if the five database clusters or the source inventory change, an SSH stream fails, a key cannot decrypt, or an archive cannot be read. Capture may take hours; keep the Acer powered and connected.

```bash
set -euo pipefail
mkdir -p "$HOME/V79-Recovery-Tools"
chmod 700 "$HOME/V79-Recovery-Tools"
cd "$HOME/V79-Recovery-Tools"
curl --fail --location --proto '=https' 'https://raw.githubusercontent.com/MrFixITslu/V79hub/e7c12ac33e6aecab3a24765f3c2514d656b20100/scripts/v79-full-backup-source-20261027.py' -o source.py
curl --fail --location --proto '=https' 'https://raw.githubusercontent.com/MrFixITslu/V79hub/e7c12ac33e6aecab3a24765f3c2514d656b20100/scripts/v79-full-backup-acer-20261027.py' -o acer.py
printf '%s  %s\\n' '74e2709c52f26f8be9afa551b5f2a61a00992c08c3e4e33c48990ac66a4af724' source.py '8f3cc3891e2a955af8a3f4769edad157042546802fb24c0e011ff9a6a636efdc' acer.py | sha256sum -c -
python3 acer.py --source-script source.py --self-test
python3 acer.py --source-script source.py --backup | tee capture.log
```

The Acer destination is a first offhost copy, not two independent copies. Never copy its recovery private key into a backup directory. A receipt marked `OFFHOST_CIPHERTEXT_VERIFIED_RESTORE_NOT_PROVEN` proves encrypted transfer, decryption and basic structure checks, not a working whole-server restore. `INCOMPLETE_DO_NOT_RESTORE` means the run failed; preserve its log/receipt for diagnosis and start a new run. The runtime inventory and live file/Redis consistency still need a private review. Old Hub/Tiquet scripts have stale image pins and must not be reused.

The current source helper captures all local named volumes except active PostgreSQL raw data, the five clusters' roles and databases, active bind sources, selected host configuration paths, all container image IDs and encrypted Docker inspect metadata. It does not create a bare-metal disk image, capture unmounted filesystems or prove consistency for file-backed services, Redis, uploads changing during capture, or a second storage copy. An offline physical image and isolated whole-server restore remain separate steps.

## Isolated restore rehearsal

Use a spare disk/host (the R430 may be suitable after hardware, RAM and storage checks) or a sufficiently resourced offline VM. Keep it disconnected from public DNS, payment gateways, email providers, customer ingress and production Tailscale identity. Restore into fresh volumes, not live Docker volumes.

1. Install a compatible OS and pinned Docker/Compose versions; create the service user and restrictive directories.
2. Decrypt the backup, validate hashes/manifest, load or rebuild exact images, restore secrets/config only inside this isolated host.
3. Start PostgreSQL/Redis without public ports. Restore roles and logical databases to matching major versions; validate schema, table counts and application-level reads. Restore file-backed data, uploads, proxy state and other volumes with recorded UID/GID/modes.
4. Start applications in dependency order: databases/Redis → Hub/agent → Tiquet → website and remaining apps → reverse proxy. Keep background workers, scheduled messages and live WiPay **disabled** in the rehearsal.
5. Check each app's health and a small authorised read-only journey; verify tenant boundaries and Hub MFA/SSO without using customer accounts. Compare manifest counts and safe fingerprints. Restore a representative file from every backed-up dataset, not just Hub/Tiquet.
6. Record a per-service PASS/FAIL and recovery time. Any untested service remains **RESTORE UNVERIFIED**. Destroy the isolated test environment only after preserving the redacted receipt.

## If the Dell drive fails

1. **Contain:** stop public DNS/router forwarding to the failed host if it is partially serving; preserve the failed drive read-only for diagnosis. Do not keep taking orders on an uncertain database.
2. **Choose recovery point:** take the latest COMPLETE offhost manifest whose hashes, decryption and restore evidence passed. Note its timestamp as the data-loss boundary. Reconcile any orders, payments, tickets or email jobs after that point from provider ledgers before reopening.
3. **Replace drive and boot:** install the new drive. If a compatible recent offline disk image exists, restore it to a same-size-or-larger disk and boot with networking isolated. Otherwise install a supported Ubuntu Server, Docker and Compose from pinned installation media/packages, then follow the isolated restore order above. A disk image alone must still be rolled forward with the latest app-aware backup.
4. **Restore privately:** create volumes/mounts, load images/config/secrets, restore databases and files, then start services in dependency order with public ingress, live payments, email and workers off. Do not overwrite a database that contains newer post-backup financial events.
5. **Accept:** confirm disk/SMART, filesystem, service health, Hub MFA and permissions, Hub→Tiquet SSO, real record counts, website lead route, certificates and monitoring. Check Portainer/proxy management access through trusted networks. Reconcile WiPay dashboard and bank records manually before any paid entitlement grant.
6. **Cut over once:** update the router/DNS to the replacement only after acceptance; enable one scheduler/worker instance at a time, verify no duplicate jobs, monitor logs/alerts. Preserve rollback and the failed disk until the new host is stable.

## Owner decisions and measurable targets

- Select offhost media and usable capacity; confirm whether the R430 is available for a restore rehearsal. Do not size a backup from the Dell's 215 GB free space; that is *source* headroom, not destination capacity.
- Decide daily recovery point target (RPO) and acceptable outage (RTO). A once-daily complete backup can lose up to approximately one day of changes; no RTO is promised before a full rehearsal.
- Decide whether to schedule a brief consistency window for file-backed apps and Redis, and where the second encrypted copy and private-key recovery copy will live.

**Status:** plan, read-only preflight and checksum-pinned capture scripts prepared; offhost capture **NOT YET RUN**, whole-server restore and disk-failure rehearsal **NOT YET VERIFIED**.
