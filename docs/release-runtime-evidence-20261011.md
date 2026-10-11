# Owner-executed Hub + Tiquet runtime audit

Production: **NO-GO**. Owner supplied read-only collector output at
2026-10-11 20:06:16 UTC (16:06:16 Saint Lucia). Collector ran from Hub
`c06f4988fab5a760c76de3c32a13a34300b480ba`, whole-file SHA256
`87134281b9dec7bff700f1e041a399ddefd2b40d9cc6951529d3e1b9a713d0cf`.
Received terminal transcript SHA256:
`220fe88b20ced8f6c9b5d3d9ce2a0516413bfad3274456b49390ec8b69e8a00e`.
This records owner-reported observations, not independent host attestation.
The raw transcript stays private; no credentials/customer records are published.

## Verified observations

| Evidence | Hub | Tiquet |
| --- | --- | --- |
| Container ID | `4caaa5b21e22a86819f3652311bbd6cba7018e6c9793c473ba13178777f1014c` | `16bad8bfb744f2b6a09026b852ece8037c9fa3fb604bce5c41274726fab3ad54` |
| Image ID | `sha256:7876715a44166c1cbeb6b5070a774efb4d69fe36427bda1c4dee4fc637c67e30` | `sha256:ee3deff332977160d66e0dbb448aef1e1e6d4418eac333e1feaf8a07c044715b` |
| Image tag | `v79hub-wipay-return:585f701` | `v79tiquet-sentinel-dark:81f4659` |
| Local RepoDigest | `v79hub-wipay-return@sha256:7876715a44166c1cbeb6b5070a774efb4d69fe36427bda1c4dee4fc637c67e30` | `v79tiquet-sentinel-dark@sha256:ee3deff332977160d66e0dbb448aef1e1e6d4418eac333e1feaf8a07c044715b` |
| Health | Docker healthy, local HTTP 200 | Docker healthy, local HTTP 200 |
| Started UTC | 2026-10-10 21:13:36 | 2026-10-10 19:47:03 |
| Compose project/service | `v79-hub` / `v79-hub` | `v79tiquet` / `v79-tiquet-manager` |
| Runtime inventory | 105 source files; no reported unreadable/symlink entries | 36 packaged source files; no reported unreadable/symlink entries |
| PostgreSQL catalog query | 17.11; read-only on; state/revision/state-column present | 16.15; read-only on; accounts/users/jobs present |
| Deployment stamp | unavailable | `1edae1033d349d0dc99e7cb5fadaf84c39018a33`, older than image tag claim |
| Current local checkout HEAD | `1fae5211e187623b5a1e68eca1ac5aebb88f59e0`, zero tracked status entries | `074a1d85b539e4df8cbd80925f037b52c18e5c5d`, 12 tracked status entries |

Both image IDs and all seven Hub/six Tiquet sampled SHA256 values are unchanged
from earlier owner evidence. Five sampled Hub protected module/ledger hashes
match the earlier committed-source evidence. This is preservation evidence only;
no Sentinel source or its independent audit was modified.

Local RepoDigests are now observed, but neither image supplies reviewed revision
labels. These unqualified local image names and inspect claims do not establish
an accessible registry manifest, trusted build attestation or approved CI lineage.
Do not substitute a mutable tag or Docker config ID for a verified release record.

## Actual deployment topology and preservation

- Hub Compose loads the `/opt/v79/hub` production file plus a pinned release
  overlay. That directory is not a Git repository. Its data bind is
  `/opt/v79/hub/data`, **not** the separate home-directory checkout. Two secret
  mounts are read-only. Preserve their private values, permissions and references.
- Tiquet Compose loads an integration release file and a backup-directory pinned
  overlay, while its working directory names the older local checkout. Preserve
  both exact existing files; deploying from the checkout's default Compose file
  alone would not reproduce this configuration.
- Application volumes: `v79tiquet_tiquet_data`, `v79tiquet_tiquet_uploads`.
  Named database volumes: `v79-hub_v79_hub_postgres_data` and
  `v79tiquet_tiquet_pg_data`. Database containers are healthy. Authoritative
  application-to-database mapping remains unverified; name/network parity alone
  is insufficient. Hub has its private data network; Tiquet and its named DB
  are attached to `proxy_network`.
- Both production `.env` metadata checks report regular, nonsymlink mode 0600.
  Contents and effective application overlays were not collected. Container
  flags show Hub admin MFA ON and WiPay ON; this is an observation, not new
  authorization for any payment or activation. Tiquet ingest/legacy auth/email
  account linking OFF; entitlement recheck and Hub-managed billing ON.
- Hub configured user is empty (default image user unresolved), neither app is
  privileged, neither has a read-only root filesystem, security options were
  unset. Runtime hardening assessment remains open; no setting changed.
- Tiquet legacy `data/tiquet.db` exists, mode 0644; no `.migrated` marker.
  This does not prove PostgreSQL migration failed or succeeded. No customer rows
  read; no application module imported; no live startup/restart performed.
- Backup candidates are directory/archive metadata only. Fresh consistent DB
  dumps, required key/files snapshots, actual isolated restore and timed old-image
  rollback were not verified. Existing unrelated containers were inventoried;
  no cleanup/recreation/removal is authorized, including stopped/created helpers.

## Comparison against pinned GitHub main and reviewed candidates

| Comparison | Matches | Differences / preservation blockers |
| --- | --- | --- |
| Hub vs main `c45d305…` | 97/101 present comparisons | server.ts, WiPay provider, App.tsx, Login.tsx differ; four extra billing/grant/entitlement/operator modules; src/index.css missing |
| Hub vs #129 `40e7d4f…` | 95/101 present comparisons | Above four plus deploy script/preservation guard differ; same extras and missing CSS |
| Tiquet vs main `1edae10…` and #31 `0d74bee…` | 28/31 present comparisons each | package-lock, server/index.js, schema.sql differ; five extra dark-integration modules; no missing expected packaged paths |

Missing Hub source CSS is not proof of a broken built frontend: each image has
four dist files and a recorded fingerprint, but no trusted build attestation.
Review packaging/release source and mobile acceptance before interpreting it.
Tiquet lock differences remain the earlier 535-entry `dev` flag comparison only;
installed dependencies are still unverified.

The audit initially compares runtime to **current checkout HEAD**, not the
historical release commits. The older Hub HEAD lacks many currently running
protected/auth/approval modules; Tiquet's older HEAD lacks current Hub-managed auth,
entitlement and socket controls. A clean Hub checkout or Tiquet stamp must never
be treated as a deployable equivalent. Preserve and compare the previously
identified exact local release objects `585f70160d74c06cf745adeaee7f418e89be9cf7`
and `81f46592fa0f3d43d103bcc5202c492918c1b9b7` without checkout/fetch/reset.
The corrected collector now requests those commit objects explicitly in addition
to reporting current HEAD; unavailable objects remain unavailable, not inferred.

## Audit correction and remaining gates

The original Tiquet `hub_account_link=false` / `hub_user_link=false` results are
**invalid as evidence of absent identity links**: the probe checked
`huborganizationid` / `hubuserid`, while the published schema defines
`hub_organization_id` / `hub_user_id`. Corrected only the release collector and
added an executable catalog-fixture regression for both presence and absence.
No application/schema/migration/Sentinel changes. Recheck catalog metadata with
the corrected pinned audit before interpreting identity-link state. Applied
migration success remains UNVERIFIED even when both columns exist.

Passed owner observations: audit execution, image/sample continuity, Docker and
local HTTP health, catalog READ ONLY connection, source/config/volume inventory.
New local tests: 12/12 audit tests, including exact-column fixture execution and
pinned local-object inspection without checkout/fetch. Exact new CI is in #128.
Production deployment/publication remain skipped; actual backup/restore/rollback,
genuine owner acceptance, trusted image provenance, effective overlays and
independent security/provider/finance gates are NOT PERFORMED or unverified.
Production remains NO-GO. Immediate follow-up is corrected read-only audit;
private combined-candidate review and authorized isolated restore/acceptance follow.
