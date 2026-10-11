# Hub + Tiquet executable read-only release runbook

**NO-GO / audit mode only.** The legacy apply entry points are blocked in this
draft. There is no apply, restart, migration, backup creation or restore option
in the executable collector. This runbook is release preparation, not permission
to operate production. Main and running containers are untouched by this draft.

## 1. Execute the audit safely

Use the exact draft commit and SHA-256 command recorded in issue #128. It reads a
pinned public script into memory, verifies its whole-file hash before execution,
and runs `audit`. No installer, git fetch/checkout, on-disk script/cache, app
import, service start, raw config dump or network/payment request is performed by
the audit. Alternatively review/download the script and run:

```bash
python3 -B /path/to/release-readiness.py audit
```

Requirements: Python 3, Git, Docker inspection/exec permission. Node and `pg`
come from the existing application containers. No sudo/escalation is attempted.
Database metadata uses `default_transaction_read_only=on` and `BEGIN READ ONLY`,
with short timeouts. It reads catalog columns/indexes, not customer rows. It does
not import `server/db.js`, `server/index.js`, `server.ts` or migration tools.

The collector prints a redacted JSON report. `audit` exit 0 means collection
completed, **not release approval**. Unavailable sections remain UNAVAILABLE;
`production` always says NO-GO. `apply` is rejected before any command. Review
the report for unrelated/private path names before sharing it. Never paste a
raw Docker inspect, environment, Compose config, .env, database dump or logs.

Expected output includes:

- Container ID, startup time/status/health; image ID/available RepoDigests and
  reviewed revision labels; configured user/restart policy/security context.
- Exact volume/bind destinations, read-only bits and network membership;
  Compose project/service, configuration file names and working directory.
- Config file metadata and whole-Compose-source fingerprints, not interpolation
  values; .env/secret files are not hashed or displayed. Startup command content
  is hashed, not displayed. `.deployed_sha` is reported only if valid full hex.
- Runtime server/src/scripts/workflow/package Git-blob/SHA-256 inventory,
  symlink/unreadable indicators, derived frontend fingerprint; comparison with
  pinned GitHub main and PR #129/#31 inventories embedded in the script.
- Local Git commit/tree/dirty tracked-entry count; runtime vs local committed
  source and GitHub vs local committed source. Tiquet comparisons respect its
  server/scripts/packages-only runtime packaging; frontend must be build-attested.
- PostgreSQL version/read-only status/schema fingerprint/link column checks and
  migration-ledger presence. **Applied migration success stays UNVERIFIED.**
  Legacy SQLite and persisted JWT-secret presence/mode only; no secret contents.
- Existing service identities and possible backup-file metadata; listing a
  backup does not establish freshness, integrity, decryption or recoverability.

Container-creation flag classifications are not certification of effective app
configuration: application overlays and additional startup code remain to be
reviewed. Source/blob parity is not image build provenance or installed-package
integrity. Missing registry digests are unresolved, not guessed from a tag.

## 2. Reconcile without writing to production

1. Confirm the report is fresh and both running image IDs match the owner
   observations, or record a new baseline. Treat any changed ID/config/mount as
   a stop. No source overwrite to make evidence appear consistent.
2. Review every differing/missing/extra runtime source path, including all Hub
   auth/SSO/billing/tenant and Sentinel safeguard modules, and Tiquet auth,
   provisioning, entitlement/revalidation, schema and secrets persistence.
   Preserve the complete local commits and private local diff in an approved
   workspace; never publish unreviewed source or original Sentinel material.
3. Verify local committed hashes against runtime plus the working tree. A clean
   commit stamp does not prove local overrides/frontend/build parity. Runtime
   package-lock `dev` differences can be explained separately; never treat them
   as installed dependency/audit clearance.
4. Match the existing Compose owner/service, bind/volume identities, overrides,
   env files, permission modes, secret files and external proxy network. A
   different project, missing owner label, orphan container, symlink or missing
   path aborts; no automatic collision removal or data-directory recreation.
5. Review catalog fingerprints against the exact restored candidate schema;
   identify whether startup will run DDL, migrate old SQLite or seed accounts.
   No live startup/import to discover behavior. Preserve legacy SQLite archives.
6. Record actual workflow/build provenance. Existing `.deployed_sha`, short
   image tags and a Git label are claims, not attestations. Bind source tree,
   approved exact commit, CI run, built platform, registry manifest digest and
   locally verified image config ID. Review unsigned/missing claims explicitly.

## 3. Required release record (not yet satisfied)

Create a privately protected, owner-reviewed record **outside customer volumes**
in the approved release workspace. No approval secret or private key belongs in
GitHub. The record must include all of the following; a boolean `verified=true`
or operator screenshot alone is insufficient evidence.

| Gate | Required binding / evidence | Abort condition |
| --- | --- | --- |
| Exact approval | Full 40-character main commit + immutable tree + approved candidate/functionality list + fresh final CI run + independent review identity/date | Changed SHA/tree, unpublished functionality omitted, stale/missing CI or separate review |
| Image identity | `registry/repo@sha256:...`, registry manifest verification, platform image ID, build provenance/revision tied to that exact source | Mutable tag only, missing digest/provenance, platform mismatch, unapproved local build |
| Configuration | Private exact .env/override/secret references, ownership/modes, network/mount inventory and private before/after fingerprints | Secret rotation, permission drift, wrong volume/project/service, missing files |
| Consistent backups | Fresh logical Hub/Tiquet PostgreSQL dumps, required uploads/files, Hub JSON if applicable, legacy SQLite, encrypted persistent JWT/MFA/encryption keys/config, database engine/version and backup digest | Inconsistent app/files/DB point, absent keys, unencrypted exposure, no quiet-window plan |
| Isolated restore | Actual restore into fresh isolated PostgreSQL/storage with outbound traffic blocked; exit/log evidence, catalog/data-count checks privately recorded, exact restored image smoke/auth/tenant verification | Only `pg_restore --list`, file exists/hash or dump success; errors/unknown restored state |
| Rollback compatibility | Preserved current image by digest/ID plus old schema/config/data; actual isolated old-image restore test and timed recovery record; agreed RPO/RTO | Old image cannot read migrated schema, no pre-migration snapshot, unknown write-loss/reconciliation |
| Single-service plan | Exact existing Hub or Tiquet service; reviewed fixed image override; no source rsync, build, dependency start, prune/remove/down/whole-project recreate | Unrelated service/collision changes, compose owner mismatch, automatic DB/agent recreation |
| Health and acceptance | Docker healthy, HTTP health check/status-only, reverse proxy path, real approved MFA/SSO/tenant acceptance and secure payment boundaries | Generic health only, any second-login/tenant access defect, unexpected writes/flags |

## 4. Backup / restore preparation sequence

This sequence is **planned, not executed**. Operations beyond read-only metadata
need a separately approved workspace/scope and must not be mistaken for approval
to create or replace production resources.

1. Owner identifies the authoritative Hub backend and each PostgreSQL service,
   database, exact volume and required uploads/config/secret storage. Secrets
   stay local; no command-line password or plaintext export is shared.
2. Establish a controlled quiet window for a DB/files consistency point, with
   existing writers/outbound workers addressed by a separately approved plan.
   No automatic worker stop or write fence flag changes in this lane.
3. The authorized operator creates permission-restricted PostgreSQL custom dumps
   with the installed compatible `pg_dump`, preserving roles/privileges as
   reviewed, and consistent uploaded/required file snapshots. Encrypt sensitive
   archives; record full-file checksums, exact engine/version/image/volume map.
   Never substitute a live filesystem copy of PostgreSQL's data directory.
4. `pg_restore --list` and file hashes are structural checks only. In the approved
   isolated workspace, perform actual restore to new empty databases and fresh
   volumes; block Resend/payment/webhook calls and provisioning/AI activation.
   Do not mount live volumes, use live passwords, expose public ports or reuse
   live container names/networks. The application's migration/seed paths must be
   observed there against the restored copy, never probed by restarting live.
5. Verify privately retained row-count/schema/reference evidence and restored
   auth/SSO/tenant isolation with approved synthetic fixtures; no real customer
   records in shared evidence. Preserve audit/financial history and encryption
   recoverability. Test both candidate and old pinned rollback image/schema pair.
6. Record elapsed restore/rollback time, log hashes, reviewer/operator identity,
   isolated volume/DB identities, successful checks and exact teardown manifest.
   Clean only the explicitly created isolated resources after review.
7. Offsite redundancy remains a separately deferred improvement; local restore
   and rollback proof is mandatory before any internal/customer release.

## 5. Future apply and rollback contract — currently unavailable

No command here applies a release. The draft entry points and first production
workflow step return 78 before copying source, downloading an artifact to the
server, using deployment secrets, creating a credential or touching Docker.
They cannot be enabled by an approval environment variable, `--force` or `--apply`.
The underlying approved-SHA workflow guards remain intact for future review.

Only after reconciliation/restore/security/owner gates pass may a separate reviewed
apply implementation use a pinned existing local image and exact current Compose
configuration, with service-targeted `--no-deps --no-build` semantics. It must
verify non-target container/image/start/mount identities before and after, preserve
all local env/overrides/secrets, reject owner-label collisions and perform no
whole-project build/recreate, cleanup/prune, automatic schema restore or container
removal. Require an approved exact single-service rollback procedure before apply.

Health failure is an abort requiring the authorized operator's rollback decision;
do not blindly auto-restore a database or discard new writes. If the candidate
performs a schema migration, an old image restart alone may be invalid. Restore
the independently tested compatible DB/files/config point only after assessing
writes since the backup and owner-approved RPO/reconciliation. Leave diagnostics
private and return status codes/hashes, not health logs or tokens. Unrelated
services and existing accounts must remain unchanged.

## 6. Owner decision points

1. Return the read-only audit output; no new production authorization is needed
   for that approved inspection. Review private unpublished diffs before deciding
   what combined candidate may preserve/replace current behavior.
2. Choose #31 over duplicate #30 as the Tiquet approval-gate baseline; decide later
   whether to consolidate/close overlapping drafts. No closure/merge performed.
3. Identify and approve an isolated restore/acceptance workspace and exact
   synthetic fixtures/outbound test inboxes. Production fixture changes, login,
   account reset, emails or payment writes need separate explicit scope.
4. Supply current production environment/branch-protection evidence read-only;
   settings changes are a later authorization, not this review's recommendation
   to change them now.
5. Complete independent security review, finance/legal acceptance, merchant/KYC
   and cleared-funds/receipts procedures. Founder release approval is separate.
6. No merge, production dispatch, setting change or activation until every
   blocker is verified closed and the owner approves the exact final candidate.
