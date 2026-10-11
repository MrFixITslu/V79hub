# Owner-approved database-only recovery verification

Owner said “proceed” on 2026-10-11 at 16:36 Saint Lucia in response to the
database-only encrypted backup/isolated restore proposal recorded in issue #128
comment 6113426034. This approval covers that bounded phase subject to mapping,
resource and encryption checks. It does not authorize merges, deployments, live
restarts/settings/data changes, payment activation, app starts or Sentinel work.
Production remains NO-GO. Do not request the same approval again.

## First owner preflight result: 2026-10-11 16:44 Saint Lucia

Collector at `c74906d457ebf8af6b6b36d770d88c56f8ff62b4` passed image/health
identity checks for both app/database pairs. Host reported 4644 MiB available
memory, 240 GiB free disk and existing gpg. No backups/restores/resources created.
Both mapping booleans were false, but that collector did not distinguish missing
probe metadata from a real address/database/port/version mismatch. No inference
of database misconfiguration or credential defect is justified yet.

Added strictly redacted per-field probe-availability/mapping checks and a complete
DB-size-requirement indicator, with regression tests. No database query, connection
method, credentials, production source or settings changed. Only diagnostic
booleans are emitted; names/addresses/raw errors remain private. The reported
5 GiB requirement is only a floor until both DB sizes are known; disk headroom
must be re-evaluated before backup/restore. Stop remains in effect pending focused
mapping diagnostics. No password rotation, PostgreSQL authentication change,
app restart, live restore or automatic workaround is authorized.

## First command: read-only preflight

### Second result and collector correction: 16:51 Saint Lucia

Owner ran exact collector `1b439a87b642e267a2a5b5a873847149e3819349`.
Both app and named-DB probes succeeded. Database names, ports, versions and
READ ONLY transactions matched for both pairs; only server-address equality
failed. Images/health and host resources remained as previously reported.
No backups, restores or test resources were created. Effective running pools
remain unverified and size-based disk requirements remain incomplete.

Found a collector defect: `inet_server_addr()::text` includes the netmask while
Docker IP metadata uses bare host addresses. PostgreSQL documents this at
https://www.postgresql.org/docs/17/functions-net.html. Use
`host(inet_server_addr())` and exact parsed IPv4/IPv6 host equality instead.
This does not relax address equality to subnet membership or change connections,
database targets, authentication, production code/settings or Sentinel modules.
Added address mismatch/malformed/CIDR/IPv6 regression cases and a real disposable
PostgreSQL CI test reproducing the old false mismatch. The old address failures
are not evidence that the apps connect to a different database container; fresh
corrected host evidence is still required. Approval from 16:36 remains in force.

Run the exact checksum-verified in-memory `scripts/recovery-preflight.py` command
provided in #128. It performs Docker inspect/exec only and prints redacted decision
metadata. No dump, restore, file/directory creation, installation, network/volume
creation or container start/stop/removal occurs. A missing prerequisite stays false;
there is no auto-repair. Database connection diagnostics stay private.

- Bind expected current app/DB image IDs and healthy status to earlier evidence.
- From each existing app container, use only pg/dotenv in a short-lived process,
  never import app initialization/migration modules. Read PostgreSQL database,
  server address/port/version and size with BEGIN READ ONLY and timeouts.
- From the named existing DB container, run psql READ ONLY against its configured
  database using its local environment. No secret value is put in an external
  command argument or printed. Compare address to named container IP, database,
  port/version and read-only status privately; emit only matching booleans/size.
- Require at least 2 GiB MemAvailable and free space of at least 5 GiB or eight
  times the combined observed DB size, whichever is larger. Test DBs are planned
  sequentially with a 512 MiB/one-CPU cap. Recheck headroom before each operation.
- Detect already-installed gpg/age only; no package installation or encryption
  key creation. Owner encryption mechanism/key/passphrase remains local and must
  be ready before a backup stream starts.

An audit connection match is not certification of the already-running process's
effective pool: compare the exact current runtime connection construction/config
semantics privately before choosing the authoritative dump target. Hub source
uses DATABASE_URL with PostgreSQL backend; Tiquet uses DATABASE_URL or discrete
DB settings. Do not substitute defaults on mismatch. A preflight true result is
not recovery verification or permission to deploy.

## Remaining approved phase, not yet executed

1. Confirm authoritative targets, private owner-only encryption destination and
   owner key handling. Capture current image/config/mount/container baseline.
2. Create fresh logical dumps without plaintext intermediate files or stopping
   live writers. Such dumps prove an individual DB snapshot, not whole-app/files
   consistency. Existing backups, accounts and volumes remain untouched.
3. Actual restore sequentially into NEW temporary test DB containers/volumes
   whose names start `v79-release-128-`, using existing exact PostgreSQL image IDs.
   Dedicated internal network, no published ports/proxy network/live mounts or
   live credentials. Do not start an application or import startup migration code.
4. Verify restore exits/catalog/constraints and privately retained count evidence;
   emit only redacted status. Abort on identity/health/resource drift. No auto
   retry, repair, live restore, broad prune or removal.
5. Retain encrypted backup/evidence and exact created-resource manifest. Cleanup
   requires manifest review and is limited to those resources. This database-only
   test does not establish combined DB/files/keys backup consistency, candidate
   app/old-image rollback, SSO/MFA acceptance or independent launch certification.

Direct host execution is quota-blocked; do not retry the rejected connector or
reconnect. Owner executes pinned reviewed commands and returns redacted output.
Unavailable prerequisites require evidence/action within the existing approved
scope, not invented success or repeated authorization requests.
