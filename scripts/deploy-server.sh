#!/usr/bin/env bash
set -euo pipefail

# Run on the target server as the dedicated deploy user. Keep .env and data on the server.
sha="${1:?A commit SHA is required}"
[[ "$sha" =~ ^[0-9a-f]{40}$ ]] || { echo 'Invalid commit SHA' >&2; exit 1; }
root=/opt/v79/hub
archive="$HOME/v79-hub-release-${sha}.tar.gz"

for command in docker rsync tar; do
  command -v "$command" >/dev/null || { echo "Missing server dependency: $command" >&2; exit 1; }
done
test -f "$archive" || { echo 'Release bundle missing' >&2; exit 1; }
test -f "$root/.env" || { echo "Create $root/.env before deploying" >&2; exit 1; }
test -d "$root/data" || { echo "Create $root/data before deploying" >&2; exit 1; }
grep -Eq '^V79_HUB_DB_PASSWORD=.{32,}$' "$root/.env" || { echo "Set a unique 32+ character V79_HUB_DB_PASSWORD in $root/.env before deploying" >&2; exit 1; }
agent_token_file="$root/data/agent-runtime.token"
if [ ! -s "$agent_token_file" ]; then
  umask 077
  head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n' > "$agent_token_file"
  chmod 600 "$agent_token_file"
fi
shared_secret_dir="$HOME/.v79-secrets"
install -d -m 700 "$shared_secret_dir"
readonly_platform_token="$shared_secret_dir/owner-readonly-platform.token"
if [ ! -s "$readonly_platform_token" ]; then
  umask 077
  head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n' > "$readonly_platform_token"
  chmod 600 "$readonly_platform_token"
fi
docker network inspect proxy_network >/dev/null || { echo 'Docker network proxy_network is missing' >&2; exit 1; }
docker compose version >/dev/null

stage=$(mktemp -d "$root/.incoming.XXXXXXXX")
trap 'rm -rf -- "$stage"' EXIT
tar -xzf "$archive" -C "$stage"
test -f "$stage/docker-compose.yml" && test -f "$stage/Dockerfile"

# The deployment directory is reserved for this app. Preserve production state.
rsync -a --delete --exclude='/.env' --exclude='/.env.*' --exclude='/data/' \
  --exclude='/backups/' --exclude='/.incoming.*/' "$stage/" "$root/"
cd "$root"
# Build first so an old container can keep serving while the new images are prepared.
docker compose --project-name v79-hub build

# Clean up only name collisions that belong to an older/different Compose project.
# This handles legacy deployments created as "v79hub" while preserving containers
# already owned by the canonical "v79-hub" project.
for name in v79-hub v79-hub-postgres v79-business-agent; do
  existing_id="$(docker ps -aq --filter "name=^/${name}$" | head -n 1)"
  [ -n "$existing_id" ] || continue
  existing_project="$(docker inspect --format '{{ index .Config.Labels "com.docker.compose.project" }}' "$existing_id" 2>/dev/null || true)"
  existing_service="$(docker inspect --format '{{ index .Config.Labels "com.docker.compose.service" }}' "$existing_id" 2>/dev/null || true)"
  if [ "$existing_project" != "v79-hub" ] || [ "$existing_service" != "$name" ]; then
    echo "Removing stale conflicting container: $name (project=${existing_project:-unknown}, service=${existing_service:-unknown})"
    docker rm -f "$existing_id"
  fi
done

docker compose --project-name v79-hub up -d --wait --wait-timeout 120
container_id="$(docker compose --project-name v79-hub ps -q v79-hub)"
test -n "$container_id"
test "$(docker inspect --format '{{.State.Health.Status}}' "$container_id")" = healthy

# Verify the local Ollama model supports the OpenAI-compatible function-calling
# surface used by the Owner Assistant. This does not expose production data.
docker exec -i v79-business-agent node --input-type=module - <<'NODE'
const controller = new AbortController();
const timeout = setTimeout(() => controller.abort(), 90_000);
try {
  const model = process.env.OLLAMA_AGENT_MODEL || "qwen2.5:1.5b";
  const base = (process.env.OLLAMA_OPENAI_BASE_URL || "http://ollama:11434/v1").replace(/\/+$/, "");
  const response = await fetch(`${base}/chat/completions`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      model,
      stream: false,
      messages: [
        { role: "system", content: "You are a deployment test. When asked, call the named tool instead of answering in text." },
        { role: "user", content: "Call ping_business now." }
      ],
      tools: [{
        type: "function",
        function: {
          name: "ping_business",
          description: "Deployment capability check.",
          parameters: { type: "object", properties: {}, required: [], additionalProperties: false }
        }
      }]
    }),
    signal: controller.signal,
  });
  const body = await response.json();
  if (!response.ok) throw new Error(`Ollama HTTP ${response.status}: ${JSON.stringify(body).slice(0,500)}`);
  const message = body?.choices?.[0]?.message;
  if (!message || typeof message !== "object") {
    throw new Error(`Ollama model ${model} returned an invalid chat completion payload.`);
  }
  const calls = message.tool_calls;
  if (!Array.isArray(calls) || !calls.some(call => call?.function?.name === "ping_business")) {
    console.warn(`WARNING: Ollama model ${model} responded successfully but did not emit the ping_business tool call. Deployment remains healthy; Owner Assistant tool-call quality should be reviewed separately.`);
  } else {
    console.log(`Ollama tool-call smoke passed with ${model}`);
  }
} finally {
  clearTimeout(timeout);
}
NODE
rm -f -- "$archive"
echo "Deployed and healthy: $sha"
