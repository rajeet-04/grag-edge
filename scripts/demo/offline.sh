#!/usr/bin/env bash
# Real connectivity loss: detach the API container from the cloud network.
source "$(dirname -- "${BASH_SOURCE[0]}")/lib.sh"
cid="$(api_container)"
if is_cloud_connected "$cid"; then
  docker network disconnect "$CLOUD_NETWORK" "$cid"
  log "disconnected $cid from $CLOUD_NETWORK"
else
  log "already disconnected from $CLOUD_NETWORK"
fi
wait_connectivity "$cid" OFFLINE
api_get "$cid" /health >/dev/null || die "local API is not healthy while offline"
log "OFFLINE confirmed by API; local API healthy"
