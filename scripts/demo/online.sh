#!/usr/bin/env bash
# Restore the cloud link by reattaching the API container with its DNS aliases.
source "$(dirname -- "${BASH_SOURCE[0]}")/lib.sh"
cid="$(api_container)"
if is_cloud_connected "$cid"; then
  log "already connected to $CLOUD_NETWORK"
else
  name="$(docker inspect -f '{{.Name}}' "$cid")"; name="${name#/}"
  docker network connect --alias fastapi --alias "$name" "$CLOUD_NETWORK" "$cid"
  log "connected $cid to $CLOUD_NETWORK"
fi
wait_connectivity "$cid" ONLINE
log "ONLINE confirmed by API"
