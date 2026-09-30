#!/usr/bin/env bash
# Reset, start Robot A + fleet + optional Robot B, then run the transfer scenario.
source "$(dirname -- "${BASH_SOURCE[0]}")/lib.sh"
project="${COMPOSE_PROJECT_NAME:-$(basename "$DEMO_ROOT" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9_-')}"
bash scripts/demo/reset.sh
compose --profile fleet-demo rm -sf robot-b-api >/dev/null
for id in $(docker volume ls -q --filter "label=com.docker.compose.project=$project" --filter "label=com.docker.compose.volume=robot_b_data"); do docker volume rm "$id" >/dev/null; done
compose --profile fleet-demo up -d --build qdrant-server fastapi robot-b-api >/dev/null
for svc in fastapi robot-b-api; do
  cid="$(compose --profile fleet-demo ps -q "$svc")"; deadline=$((SECONDS + WAIT_SECONDS))
  until [[ "$(docker inspect -f '{{.State.Health.Status}}' "$cid")" == "healthy" ]]; do
    (( SECONDS < deadline )) || die "$svc did not become healthy"; sleep 2
  done
done
wait_connectivity "$(api_container)" ONLINE
python3 scripts/demo/fleet_transfer.py
