#!/usr/bin/env bash
# Publish a divergent fleet revision and wait for the edge to open a conflict.
source "$(dirname -- "${BASH_SOURCE[0]}")/lib.sh"
cid="$(api_container)"
wait_connectivity "$cid" ONLINE
run_in_api "$cid" seed_conflict.py
deadline=$((SECONDS + WAIT_SECONDS))
while (( SECONDS < deadline )); do
  api_send "$cid" POST /api/v1/edge/sync/run </dev/null >/dev/null 2>&1 || true
  count="$(api_get "$cid" /api/v1/edge/stats | json_field open_conflict_count)"
  [[ "$count" -ge 1 ]] && { log "conflict opened (open_conflict_count=$count)"; exit 0; }
  sleep 2
done
die "no conflict detected within ${WAIT_SECONDS}s"
