#!/usr/bin/env bash
# Full judging flow: reset -> start/sync -> real network cut -> operate offline
# -> reconnect -> queue drain -> fleet refresh -> synchronized state.
source "$(dirname -- "${BASH_SOURCE[0]}")/lib.sh"
MEMORY_ID="10ade000-0000-0000-0006-000000000001"
CONTENT="Robot observation: Pump P-41 bearing vibration elevated during the offline inspection round."
check() { python3 -c "$1" || die "assertion failed: $2"; }

bash scripts/demo/reset.sh
bash scripts/demo/start.sh
cid="$(api_container)"
[[ "$(connectivity "$cid")" == "ONLINE" ]] || die "expected ONLINE after start"
[[ "$(api_get "$cid" /api/v1/edge/stats | json_field fleet_memory_count)" -ge 6 ]] || die "initial fleet sync did not load seed memories"

bash scripts/demo/offline.sh
cid="$(api_container)"
is_cloud_connected "$cid" && die "container is still attached to $CLOUD_NETWORK"

log "offline: writing P-41 observation"
printf '{"memory_id":"%s","memory_type":"observation","content":"%s","importance":"high","sync_policy":"auto","sensitivity":"fleet_safe","device_id":"robot-edge-001","tags":["pump","P-41"]}' \
  "$MEMORY_ID" "$CONTENT" | api_send "$cid" POST /api/v1/edge/memories >/dev/null || die "offline write failed"

log "offline: local hybrid search"
printf '{"query":"Pump P-41 bearing vibration","mode":"hybrid","limit":10}' | api_send "$cid" POST /api/v1/edge/search \
  | MEMORY_ID="$MEMORY_ID" python3 -c 'import json,os,sys; r=json.load(sys.stdin)["results"]; sys.exit(0 if any(x["memory_id"]==os.environ["MEMORY_ID"] for x in r) else 1)' \
  || die "offline search did not return the new P-41 memory"

log "offline: GRAG query"
printf '{"model":"grag-pipeline-v1","stream":false,"messages":[{"role":"user","content":"What do we know about Pump P-41?"}]}' \
  | api_send "$cid" POST /v1/chat/completions 300 \
  | python3 -c 'import json,sys; c=json.load(sys.stdin)["choices"][0]["message"]["content"]; sys.exit(0 if c.strip() else 1)' \
  || die "offline GRAG query returned no answer"

[[ "$(connectivity "$cid")" == "OFFLINE" ]] || die "expected OFFLINE while cut"
pending="$(api_get "$cid" /api/v1/edge/stats | json_field pending_sync)"
[[ "$pending" -ge 1 ]] || die "offline write was not queued for sync (pending=$pending)"

bash scripts/demo/online.sh
cid="$(api_container)"
wait_sync_idle "$cid" 7
deadline=$((SECONDS + WAIT_SECONDS)); state=""
while (( SECONDS < deadline )); do
  state="$(api_get "$cid" "/api/v1/edge/memories/$MEMORY_ID" | json_field sync_state)"
  [[ "$state" == "SYNCHRONIZED" ]] && break
  sleep 2
done
[[ "$state" == "SYNCHRONIZED" ]] || die "P-41 memory ended in state '$state', expected SYNCHRONIZED"
[[ "$(connectivity "$cid")" == "ONLINE" ]] || die "expected ONLINE after reconnect"
[[ "$(api_get "$cid" /api/v1/edge/stats | json_field pending_sync)" == "0" ]] || die "queue not drained"
log "ACCEPTANCE PASSED: $(api_get "$cid" /api/v1/edge/stats)"
