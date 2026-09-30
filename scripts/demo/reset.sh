#!/usr/bin/env bash
# Remove only this Compose project's edge API, fleet server and their data volumes.
source "$(dirname -- "${BASH_SOURCE[0]}")/lib.sh"
project="${COMPOSE_PROJECT_NAME:-$(basename "$DEMO_ROOT" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9_-')}"
compose rm -sf fastapi qdrant-server >/dev/null
for volume in edge_data qdrant_server_data; do
  ids="$(docker volume ls -q --filter "label=com.docker.compose.project=$project" --filter "label=com.docker.compose.volume=$volume")"
  for id in $ids; do docker volume rm "$id" >/dev/null; log "removed volume $id"; done
done
log "reset complete"
