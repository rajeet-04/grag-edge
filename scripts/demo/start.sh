#!/usr/bin/env bash
# Bring up the fleet server and edge API, then load the deterministic dataset.
source "$(dirname -- "${BASH_SOURCE[0]}")/lib.sh"
compose up -d qdrant-server fastapi >/dev/null
cid="$(api_container)"
deadline=$((SECONDS + WAIT_SECONDS))
until [[ "$(docker inspect -f '{{.State.Health.Status}}' "$cid")" == "healthy" ]]; do
  (( SECONDS < deadline )) || die "API did not become healthy"
  sleep 2
done
is_cloud_connected "$cid" || bash scripts/demo/online.sh
wait_connectivity "$cid" ONLINE
run_in_api "$cid" seed_fleet.py
run_in_api "$cid" seed_local.py --base-url http://localhost:8000
wait_sync_idle "$cid" 4
log "started: $(api_get "$cid" /api/v1/edge/stats)"
