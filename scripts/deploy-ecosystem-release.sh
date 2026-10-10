#!/usr/bin/env bash
set -euo pipefail

docker network inspect proxy_network >/dev/null 2>&1 || {
  echo "Required Docker network proxy_network is missing." >&2
  exit 1
}

deploy_app() {
  local name="$1"
  local root="$2"
  local default_project="$3"
  local service="$4"
  local container="$5"
  local archive="$6"
  local port="$7"
  local health_path="$8"

  echo "==> Deploying $name"
  test -d "$root" || { echo "Missing deployment directory: $root" >&2; exit 1; }
  test -f "$root/.env" || { echo "Missing production .env: $root/.env" >&2; exit 1; }
  test -f "$archive" || { echo "Missing release bundle: $archive" >&2; exit 1; }

  # The normal Hub release binds /opt/v79/hub/data. Refuse a coordinated
  # deployment before copying or recreating anything if that mount differs.
  if [ "$name" = "V79 Hub" ]; then
    test -d "$root/data" || { echo "Hub production data directory is missing." >&2; exit 1; }
    local live_data
    live_data="$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "/app/data"}}{{.Source}}{{end}}{{end}}' "$container" 2>/dev/null || true)"
    if [ -z "$live_data" ] || [ "$(realpath "$live_data")" != "$(realpath "$root/data")" ]; then
      echo "Hub release target does not match the live production data mount." >&2
      exit 1
    fi
  fi

  local project
  project="$(docker inspect --format '{{ index .Config.Labels "com.docker.compose.project" }}' "$container" 2>/dev/null || true)"
  project="${project:-$default_project}"
  [[ "$project" =~ ^[a-z0-9][a-z0-9_-]*$ ]] || {
    echo "Invalid Compose project discovered for $container: $project" >&2
    exit 1
  }

  local stage
  stage="$(mktemp -d "$root/.incoming.XXXXXXXX")"
  tar -xzf "$archive" -C "$stage" --no-same-owner
  test -f "$stage/docker-compose.yml" || { echo "$name bundle has no docker-compose.yml" >&2; exit 1; }
  test -f "$stage/Dockerfile" || { echo "$name bundle has no Dockerfile" >&2; exit 1; }

  # Protect currently running Hub security modules before any app is touched.
  if [ "$name" = "V79 Hub" ]; then
    bash "$stage/scripts/verify-sentinel-preservation.sh" "$stage" "$container"
  fi

  rsync -a \
    --exclude='/.env' --exclude='/.env.*' \
    --exclude='/data/' --exclude='/uploads/' --exclude='/backups/' \
    --exclude='/.git/' --exclude='/node_modules/' --exclude='/dist/' \
    "$stage/" "$root/"

  cd "$root"
  docker compose --project-name "$project" config >/dev/null

  if docker inspect "$container" >/dev/null 2>&1; then
    local owner
    owner="$(docker inspect --format '{{ index .Config.Labels "com.docker.compose.project" }}' "$container" 2>/dev/null || true)"
    if [ -z "$owner" ]; then
      echo "Removing orphan container $container"
      docker rm -f "$container" >/dev/null
    fi
  fi

  docker compose --project-name "$project" up -d --build --force-recreate "$service"

  local ok=0
  for _ in $(seq 1 30); do
    if docker exec "$container" node -e \
      "fetch('http://127.0.0.1:${port}${health_path}',{signal:AbortSignal.timeout(4000)}).then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))" \
      >/dev/null 2>&1; then
      ok=1
      break
    fi
    sleep 4
  done
  if [ "$ok" -ne 1 ]; then
    echo "$name failed health check." >&2
    docker logs --tail=120 "$container" >&2 || true
    exit 1
  fi

  local networks
  networks="$(docker inspect --format '{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}' "$container")"
  echo "$name networks: $networks"
  echo "$networks" | grep -qw proxy_network || {
    echo "$name is not attached to proxy_network." >&2
    exit 1
  }

  rm -f -- "$archive"
  rm -rf -- "$stage"
  echo "==> $name deployed successfully"
}

deploy_app "V79 Hub"       "/opt/v79/hub"       "v79-hub"       "v79-hub"            "v79-hub"            "$HOME/v79-ecosystem-hub.tar.gz"       "3040" "/api/health"
deploy_app "V79 Tiquet"    "$HOME/V79Tiquet"    "v79tiquet"    "v79-tiquet-manager" "v79-tiquet-manager" "$HOME/v79-ecosystem-tiquet.tar.gz"    "3050" "/health"
deploy_app "V79 Marketing" "$HOME/V79Marketing" "v79marketing" "v79-marketing"       "v79marketing-app"    "$HOME/v79-ecosystem-marketing.tar.gz" "3070" "/api/health"
deploy_app "FFPRO"         "$HOME/FFPRO2"        "ffpro2"       "fire-finance"        "fire-finance-app"    "$HOME/v79-ecosystem-ffpro.tar.gz"     "3010" "/api/health"

echo "All V79 ecosystem applications deployed successfully."
