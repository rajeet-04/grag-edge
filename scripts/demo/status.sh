#!/usr/bin/env bash
source "$(dirname -- "${BASH_SOURCE[0]}")/lib.sh"
cid="$(api_container)"
if is_cloud_connected "$cid"; then net=connected; else net=disconnected; fi
log "container=$cid network=$net"
log "status: $(api_get "$cid" /api/v1/edge/status)"
log "stats: $(api_get "$cid" /api/v1/edge/stats)"
log "sync: $(api_get "$cid" /api/v1/edge/sync/status)"
