# Off-host PostgreSQL restore rehearsal — verified 9 Oct 2026

**Status: PASS for backup archive recoverability, not a complete production rollback/UAT.**

## Scope and provenance
Source file was the existing protected `hub-postgres-before.dump` archive in the Phase 2B pre-release rollback directory. All work was performed on the authorised `firelion-Aspire-A315-51` laptop, using a fresh, 0700-permission temporary directory, and **never connected to or wrote to any running production PostgreSQL service**.

The Ubuntu V79 host remained live. Its initial local-network checks showed Hub, the AI business agent, and Hub PostgreSQL healthy; the failed earlier test container was not present. An archive-list attempt through a new ephemeral Docker helper on the production host stalled and left an unrelated dead test-only helper `distracted_banach`, so the server-hosted Docker approach was abandoned. No server container deletion, forced stop, global daemon restart or prune was performed. A later GitHub issue #104 comment records this safety stop.

## Independently observed restoration evidence
| Check | Evidence |
|---|---|
| Archive | PostgreSQL custom archive `PGDMP`, v1.16, 10,149 bytes |
| SHA256 | `c163759bdc7cebafb3e423d0e0cda28f0dfe20ae3b0ff660bd9bfd7f094f939a`, matched server preflight and copied archive |
| Compatible restore version | PostgreSQL **17.11** from the official PostgreSQL PGDG Noble repository |
| Package verification | PGDG-signed `InRelease` verified; index SHA256 matched signed release; `postgresql-17` and `postgresql-client-17` package SHA256 matched signed package index |
| Installation method | Packages **extracted only** under temporary laptop directory using `dpkg-deb -x`; no laptop system package installation |
| Connection isolation | Ephemeral local PostgreSQL 17 server: `listen_addresses=''`, private Unix socket `0700`, no TCP listener, dedicated throwaway DB/data directory |
| Archive contents | 3 listed archive objects |
| `pg_restore --exit-on-error --no-owner --no-acl` | **Exit code 0** |
| Restored public tables | **1** |
| `public.v79_hub_state` present | **Yes** |
| Hub state rows | **1** |
| Hub rows with positive revision and JSON object state | **1** |
| Final restoration validation | `FULL_OFFHOST_RESTORE_AND_STRUCTURAL_VERIFICATION=PASS` |
| Cleanup | `LAB_CLEANUP=completed EXIT_CODE=0`: shut down temporary server, deleted temporary downloaded packages, archived copy, socket and database files |

A first local attempt used PostgreSQL 16 against archive version 1.16 and failed before restoration because that version is too old. An intermediate PostgreSQL 17 run completed `pg_restore` but used an extracted PG17 `psql` linked to the laptop's PG16 libpq and could not complete SQL checks. The final successful test used PostgreSQL 17 server/restore tooling and the compatible existing PostgreSQL 16 SQL client to verify table state.

## What this proves and does not prove
**Proven:** The restricted backup bytes, unchanged from the server snapshot, can populate a brand-new, private PostgreSQL 17 database and yield a structurally valid Hub state row.

**Not proven:** A complete application bootstrap from the restored snapshot, live production cutover/rollback, restored sessions, connected-app SSO, multi-container behaviour, on-host Docker resource reliability, alternate backup ages, or offsite recovery time. The earlier server Docker exit-137 cause and test-helper cleanup still require a separate safe maintenance review.

Keep issue #104 **open** for full application recovery and image rollback confirmation. Keep Phase 3A PR #103 **draft/unmerged** until its other security and release gates have passed. Do not print or commit backup contents, expose credentials, use production volumes, or enable autonomous writes.
