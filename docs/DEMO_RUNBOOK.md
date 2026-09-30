# GRAG Edge Demo Runbook

All commands run from the repository root. The scripts talk to Docker from the host and reach the API via
`docker exec`, so they also work in nested Docker runtimes where port 8000 is not host-reachable.
No cloud credentials are used. Set `DOCKER_HOST` first if your Docker engine is not the default.

## 0. Prepare

```bash
cp .env.example .env      # only if .env is absent
docker compose config -q  # expect no output, exit 0
```

## 1. Reset (safe to repeat, also after an interrupted recording)

```bash
make demo-reset
```

Removes only this project's edge API and fleet server containers and their `edge_data` and
`qdrant_server_data` volumes. Ollama and Neo4j are untouched. Reset when the network is left
disconnected: `make demo-start` reattaches it.

## 2. Start online with fleet knowledge

```bash
make demo-start
make demo-status
```

Expected: connectivity `ONLINE`; `fleet_memory_count >= 6`; `pending_sync 0`.
Dashboard `http://localhost:5173` Overview: ONLINE badge, fleet count 6+, queue 0.

## 3. Go offline (real network cut)

```bash
make demo-offline
```

Detaches the API from `grag-cloud-net`. Expected: Overview switches to OFFLINE within seconds while local
status stays READY; `/health` still succeeds.

## 4. Offline work

Create the Pump P-41 observation (Memory page, or):

```bash
cid=$(docker compose ps -q fastapi)
docker exec -i "$cid" curl -s -X POST localhost:8000/api/v1/edge/memories -H 'content-type: application/json' \
  -d '{"memory_type":"observation","content":"Robot observation: Pump P-41 bearing vibration elevated during the offline inspection round.","importance":"high","sync_policy":"auto","sensitivity":"fleet_safe","tags":["pump","P-41"]}'
```

Expected: 201; Sync Center shows the memory `QUEUED` (policy auto). Search page, query
"Pump P-41 bearing vibration", mode hybrid: the new memory appears with origin LOCAL. Ask GRAG:

```bash
docker exec -i "$cid" curl -s localhost:8000/v1/chat/completions -H 'content-type: application/json' \
  -d '{"model":"grag-pipeline-v1","stream":false,"messages":[{"role":"user","content":"What do we know about Pump P-41?"}]}'
```

Expected: a non-empty answer citing LOCAL evidence.

## 5. Reconnect

```bash
make demo-online
```

Expected: ONLINE; the queued memory uploads, the fleet refresh completes, state becomes `SYNCHRONIZED`,
queue returns to 0, fleet count increases by one.

## 6. Conflict (optional)

```bash
make demo-conflict
```

Publishes a divergent fleet revision of procedure V-22. Expected: Conflicts page lists one OPEN conflict
with both revisions and provenance; nothing is overwritten. Resolve with keep local, accept fleet or merge
(Conflicts page or `POST /api/v1/edge/conflicts/{id}/resolve`).

## 7. One-shot acceptance

```bash
make demo-acceptance     # steps 1-5 with assertions; exits non-zero on any failure
```

## 8. Optional Robot B fleet transfer

```bash
make demo-robot-b
```

Robot A writes while offline, syncs, and Robot B (`ROBOT-02`, port 8002) then finds the memory with
origin FLEET from `ROBOT-01`.

## 9. Browser e2e against the real stack

```bash
make demo-e2e-real
```

Resets and starts the stack, brings up `grag-edge-ui` (nginx serving the built console and proxying the real
Edge API), seeds the V-22 conflict, then drives Chromium (Playwright, in a runner container on the edge
network) through the real status rail, hybrid search with provenance, Sync and Conflicts pages and a real
offline/online transition using `scripts/demo/offline.sh` / `online.sh`. `E2E_SKIP_PREPARE=1` reuses a running
stack. The hermetic mock-API suite (`npm run e2e` in `frontend/`, includes the axe light/dark audit and keyboard
navigation checks) needs no Docker services.

## Troubleshooting

- `expected exactly one running fastapi container`: run `make demo-start`.
- Stuck OFFLINE after `demo-online`: `make demo-status`; the script re-attaches with the required DNS aliases.
- Slow first GRAG answer: local model warm-up; retrieval latency is measured separately.

## Verification record

Verified product commit `c0d8f06`: `make demo-acceptance` passed twice from reset, `make demo-robot-b` passed, backend suites, frontend tests/build and `make baseline-check` passed (see docs/superpowers/verification/p12-execution.md).
