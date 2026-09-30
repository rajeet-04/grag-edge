#!/usr/bin/env bash
# Shared helpers for host-side demo commands. Only the host talks to Docker;
# the application containers never receive the Docker socket.
set -Eeuo pipefail

DEMO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$DEMO_ROOT"
CLOUD_NETWORK="${CLOUD_NETWORK:-grag-cloud-net}"
WAIT_SECONDS="${DEMO_WAIT_SECONDS:-120}"

die() { printf 'demo: %s\n' "$*" >&2; exit 1; }
log() { printf 'demo: %s\n' "$*"; }

compose() {
  if docker compose version >/dev/null 2>&1; then docker compose "$@"
  elif command -v docker-compose >/dev/null 2>&1; then docker-compose "$@"
  else die "Docker Compose is required"; fi
}

# Container IDs change on every recreate: always resolve fresh, never cache.
api_container() {
  local ids count
  ids="$(compose ps -q fastapi 2>/dev/null | sed '/^$/d')"
  count="$(printf '%s\n' "$ids" | sed '/^$/d' | wc -l | tr -d ' ')"
  [[ "$count" == "1" ]] || die "expected exactly one running fastapi container, found $count"
  [[ "$(docker inspect -f '{{.State.Running}}' "$ids")" == "true" ]] || die "fastapi container is not running"
  printf '%s\n' "$ids"
}

is_cloud_connected() {
  [[ "$(docker inspect -f '{{if index .NetworkSettings.Networks "'"$CLOUD_NETWORK"'"}}yes{{else}}no{{end}}' "$1")" == "yes" ]]
}

api_get() { docker exec "$1" curl -fsS -m 10 "http://localhost:8000$2"; }
api_send() { docker exec -i "$1" curl -fsS -m "${4:-120}" -X "$2" -H 'Content-Type: application/json' ${API_HEADER:+-H "$API_HEADER"} --data-binary @- "http://localhost:8000$3"; }

json_field() { python3 -c 'import json,sys; d=json.load(sys.stdin)
for k in sys.argv[1].split("."): d=d[k]
print(d)' "$1"; }

connectivity() { api_get "$1" /api/v1/edge/status | json_field connectivity; }

wait_connectivity() {
  local cid="$1" want="$2" deadline state=""
  deadline=$((SECONDS + WAIT_SECONDS))
  while (( SECONDS < deadline )); do
    state="$(connectivity "$cid" 2>/dev/null || true)"
    [[ "$state" == "$want" ]] && return 0
    sleep 1
  done
  die "API did not report $want within ${WAIT_SECONDS}s (last: ${state:-unreachable})"
}

# Run a demo script inside the API container (has app code and cloud-net access).
run_in_api() {
  local cid="$1" script="$2"; shift 2
  docker exec "$cid" rm -rf /tmp/demo >/dev/null
  docker cp scripts/demo "$cid:/tmp/demo" >/dev/null
  docker cp demo/seed "$cid:/tmp/demo/seed" >/dev/null
  docker exec -w /app "$cid" /app/.venv/bin/python "/tmp/demo/$script" --seed-dir /tmp/demo/seed "$@"
}

wait_sync_idle() {
  local cid="$1" min_fleet="$2" deadline pending fleet
  deadline=$((SECONDS + WAIT_SECONDS))
  while (( SECONDS < deadline )); do
    api_send "$cid" POST /api/v1/edge/sync/run </dev/null >/dev/null 2>&1 || true
    pending="$(api_get "$cid" /api/v1/edge/stats | json_field pending_sync 2>/dev/null || echo x)"
    fleet="$(api_get "$cid" /api/v1/edge/stats | json_field fleet_memory_count 2>/dev/null || echo 0)"
    if [[ "$pending" == "0" && "$fleet" -ge "$min_fleet" ]]; then return 0; fi
    sleep 2
  done
  die "sync did not settle (pending=$pending fleet=$fleet, wanted fleet>=$min_fleet)"
}
