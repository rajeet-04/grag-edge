# P10 Execution Evidence

Commits: `83cab2d` seed data, `402e9aa` network controls, `8a0ce30` acceptance flow.

## Results
- `make demo-acceptance` run twice from reset on the live Compose stack (image rebuilt): PASS both times (reset, start, seed, initial sync fleet=6, real `docker network disconnect grag-cloud-net`, API reports OFFLINE, offline write/hybrid search/GRAG query succeed, reconnect, ONLINE, queue drained, P-41 memory SYNCHRONIZED, fleet=7).
- `make demo-conflict`: divergent V-22 procedure opens conflict (open_conflict_count=1).
- Live offline/online cycles executed twice; idempotency (double offline, online-when-online, fresh container ID, ambiguous container) covered by fake-docker tests.
- tests/demo 20 passed; tests/edge 144 passed; baseline-check exit 0 (380 passed, 1 skipped, exact 10 imported failures); `make compose-config` valid; `git diff --check` clean. Frontend untouched.

## Rulings / deviations
- Compose plugin absent: scripts use `docker compose` when available, else `docker-compose`; container resolved fresh via `compose ps -q fastapi` (fails on 0 or >1).
- Host cannot reach published port 8000 in this runtime; API calls go through `docker exec <cid> curl`, and seeders run inside the API container via `docker cp`. API key stays inside the container.
- Fleet seed points carry dense vectors only (no BM25 sparse, since the edge store owns the sparse encoder); fleet search there relies on dense scores.
- Reset removes only this project's fastapi/qdrant-server containers and edge_data/qdrant_server_data volumes (label-scoped); Ollama/Neo4j untouched. `start` uses `up -d --build` because a stale image lacked conflict routes.
- RED discipline: seed data files and scripts were written before their tests were first run for tasks 2-3 in part; RED was observed by temporarily removing scripts/Make targets. No independent review.
