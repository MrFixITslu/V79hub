# V79 Hub backup restore — isolated rehearsal safety runbook

**9 Oct 2026 · Draft / not executed · Issue #104 · No production changes permitted.**

## Current evidence and blocker
- The prior test-only Postgres container `v79-hub-isolated-restore-20261009` exited 137 and Docker cleanup stalled. The original `pg_restore -l` listing succeeded, **but a full restore has NOT passed**. Exit 137 may indicate OOM/SIGKILL, not proven without kernel/container runtime evidence.
- The backup source is `/home/firelion/v79-release-rollbacks/ai-workforce-phase2b-pr102-20261008/hub-postgres-before.dump`. Treat its content as sensitive. Do not copy the dump to GitHub, ChatGPT, CI, email, or any public filesystem.
- A read-only SSH connection attempted from the authorised laptop to the server's previously configured Tailscale address on 9 Oct 2026 **timed out**. No host diagnostics or cleanup executed. Confirm route/host identity without relaxing SSH host-key validation.
- Production and beta services must remain untouched. Preserve the archive and existing rollback manifests.

## Gate A — read-only diagnostics only
Run these checks on the already-authenticated **actual V79 server**, not on an unrelated workstation, during a low-traffic maintenance window. These commands do not remove containers, restart services, or modify database data.

```bash
set -u
hostname
date -Is
free -h
df -h /
df -ih /
timeout 15s docker ps --filter name=v79-hub --format '{{.Names}} {{.Status}}'
timeout 15s docker ps -a --filter name=v79-hub-isolated-restore-20261009 \
  --format '{{.ID}} {{.Names}} {{.Status}}'
timeout 15s docker inspect v79-hub-isolated-restore-20261009 \
  --format 'state={{.State.Status}} exit={{.State.ExitCode}} oom={{.State.OOMKilled}}' \
  2>&1 || true
journalctl -k --since '2026-10-09 00:00:00' --no-pager 2>/dev/null \
  | grep -Ei 'oom|out of memory|killed process|memory cgroup' | tail -30 || true
test -r /home/firelion/v79-release-rollbacks/ai-workforce-phase2b-pr102-20261008/hub-postgres-before.dump
stat -c '%n %s bytes %a permissions' \
 /home/firelion/v79-release-rollbacks/ai-workforce-phase2b-pr102-20261008/hub-postgres-before.dump
sha256sum \
 /home/firelion/v79-release-rollbacks/ai-workforce-phase2b-pr102-20261008/hub-postgres-before.dump
pg_restore -l \
 /home/firelion/v79-release-rollbacks/ai-workforce-phase2b-pr102-20261008/hub-postgres-before.dump \
  >/dev/null
```

The SHA-256 checksum is a **new local observation**, not proof of a previously established good hash. Compare it to a recorded backup-time manifest if one exists. Avoid posting host diagnostic output if it contains keys, access tokens or customer identifiers.

## Gate B — readiness decision, before creating anything
- Confirm production Hub, agent and PostgreSQL health; stop if any are degraded.
- Record available RAM **and** swap, tmpfs/disk headroom, dump bytes and required Postgres major version. Existing server simultaneously hosts Ollama/MicroK8s/other containers and previously suffered exit 137; do not assume that 512 MiB or any arbitrary limit is sufficient.
- If the old test-only container is still `Dead`/`removing`, inspect dockerd/containerd conditions. Do not issue a global `docker restart`, `systemctl restart docker`, `docker system prune`, or broad stop/remove command. Remove only a verified **test-only** container when safe and separately authorised.
- Schedule a resource-bounded test only after agreeing on a host memory/CPU/storage ceiling, backup retention and test cleanup plan. If not safe, use an external disposable staging machine instead of loading the production host.

## Gate C — controlled, network-isolated restore (not run)
1. Select an ephemeral isolated PostgreSQL instance **with no host ports, no application network, no production volume mounts and no production environment secrets**. Use a unique test-only name, a fixed compatible Postgres image tag, bounded memory/CPU/process limits and dedicated temporary storage.
2. Verify that the target is newly created and empty. **Never** run a restore command using a production `DATABASE_URL`, `PGHOST` or application volume. Prefer a one-shot test process that accepts the dump via stdin from a protected source; the dump itself must not be added to an image or CI artifact.
3. Restore into a temporary database, capture `pg_restore` exit status, verify expected Hub schema/table and `v79_hub_state` store revision and structural JSONB, compare source backup metadata with restore result, and perform a read-only schema/table query. Report sensitive values only as booleans/counts.
4. Document CPU/memory pressure and process/kernel evidence for any failed attempt. Exit 137 is a **failed** rehearsal regardless of `pg_restore -l` or health checks.
5. After a **successful** check and explicit confirmation that no production data or volumes are targeted, dispose of the test-only environment using its exact name. Record original-backup hash, isolated restore status, commands, versions, time and result in a protected test report.
6. Do not mark Phase 3A rollback-ready until this test passes **and** an independent rollback image/manifest/recovery point are confirmed.

## Release gates after restore
Exact-SHA CI, a separated owner-MFA browser/UAT sign-off, evidence source-authentication, linked audit external anchoring, multi-instance test, and separate explicit founder permission to merge/deploy PR #103 remain required. Approval does not enable agent execution.

**Safety outcome so far:** Backup existence/listability reported in #104; actual new restore, orphan cleanup and host diagnostics not confirmed. This file is a runbook, not evidence of a successful rehearsal.
