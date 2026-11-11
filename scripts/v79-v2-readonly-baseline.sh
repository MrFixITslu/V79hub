#!/usr/bin/env bash
# V79 V2: read-only release provenance. Run on the V79 host once source
# reconciliation is ready. Does not print Docker env, secrets, logs, token
# values, database rows, mounts, container network settings or customer data.
set -euo pipefail
umask 077

for cmd in docker date; do
  command -v "$cmd" >/dev/null || { echo "MISSING_COMMAND=$cmd"; exit 2; }
done
docker info --format '{{.ServerVersion}}' >/dev/null || {
  echo "DOCKER_ACCESS=UNAVAILABLE"; exit 3;
}
printf 'BASELINE_COLLECTED_UTC=%s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
printf 'DOCKER_SERVER_VERSION=%s\n' "$(docker info --format '{{.ServerVersion}}')"
printf 'RELEASE_IDENTITY=READ_ONLY_NOT_A_BACKUP\n'
printf '%s\n' 'CONTAINER_NAME|IMAGE_REFERENCE|IMMUTABLE_IMAGE_ID|STATUS|HEALTH|COMPOSE_PROJECT|COMPOSE_SERVICE'

docker ps -a --no-trunc --format '{{.ID}}' | while IFS= read -r container; do
  [[ -n "$container" ]] || continue
  docker inspect --type=container --format \
    '{{.Name}}|{{.Config.Image}}|{{.Image}}|{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}unknown{{end}}|{{if .Config.Labels}}{{index .Config.Labels "com.docker.compose.project"}}{{else}}unknown{{end}}|{{if .Config.Labels}}{{index .Config.Labels "com.docker.compose.service"}}{{else}}unknown{{end}}' \
    "$container" | sed 's#^/##'
done
printf 'CHECKPOINT=COMPLETE_READ_ONLY\n'
printf 'WARNING=No_customer_data_or_source_checksum_was_collected\n'
printf 'WARNING=Use_verified_offhost_restore_evidence_before_any_cutover\n'
