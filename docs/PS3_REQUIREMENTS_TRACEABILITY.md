# PS3 Requirements Traceability

Maps each PS3 requirement (spec sections 1, 28, 31) to implementation and proof.

| Requirement | Implementation | Test / demo proof |
|---|---|---|
| Maintain searchable semantic memory on the edge | `app/edge/memory/qdrant_store.py`, `service.py` | `tests/edge/memory/`, `tests/e2e/test_edge_offline_pipeline.py` |
| Dense, BM25 and hybrid search offline | `app/edge/memory/hybrid_search.py`, `bm25.py` | `tests/edge/memory/test_hybrid_search.py`, `test_bm25.py`; demo-acceptance offline search |
| Low-latency search (p95 < 250 ms), write p95 < 300 ms, status < 100 ms | `app/edge/api/operations.py` | `tests/performance/test_edge_targets.py` |
| Operate through intermittent connectivity | `app/edge/sync/connectivity.py`, `runtime.py` | `tests/edge/sync/test_connectivity.py`, `tests/edge/api/test_edge_status.py`; demo-acceptance real network cut |
| Decide what stays local vs syncs | `app/edge/policy/engine.py`, `rules.py`, `app/edge/sync/workflow.py` | `tests/edge/policy/`, `tests/edge/api/test_sync_policy.py` |
| Restricted/local-only never uploaded | `app/edge/sync/service.py` (`_eligible`, payload projection) | `tests/e2e/test_privacy_boundary.py`, `tests/edge/sync/test_sync_service.py` |
| Sync with Qdrant Server on reconnect | `app/edge/sync/service.py`, `server_client.py`, `snapshot.py` | `tests/edge/sync/` (incl. live Docker native full/partial), `make demo-acceptance` |
| Queued work survives restart | `app/edge/state/sqlite.py`, `sync/outbox.py`, `runtime.py` | `tests/e2e/test_restart_recovery.py`, `tests/edge/test_p04_reconcile_gap.py` |
| Preserve revisions and conflicting information | `app/edge/memory/service.py`, `app/edge/conflicts/service.py` | `tests/edge/conflicts/`, `tests/edge/api/test_conflicts.py`, `make demo-conflict` |
| Divergent revision never silently overwritten | `app/edge/conflicts/service.py`, `sync/service.py` (`_scan_conflicts`) | `tests/edge/sync/test_p07_review_regressions.py`, restart test with open conflict |
| Deduplicate LOCAL vs FLEET | `app/edge/memory/dedupe.py` | `tests/edge/memory/test_dedupe.py` |
| User-facing interface for memory, search, sync, conflicts, activity | `frontend/src/pages/`, `hooks/useEdgeEvents.ts` | `frontend` vitest (16 tests), `npm run build` |
| UI updates without manual refresh | `app/edge/api/operations.py` (`/events` SSE), `frontend/src/hooks/useEdgeEvents.ts` | `tests/edge/api/test_edge_status.py` SSE reconnect, frontend page tests |
| Observability counters and activity stream | `app/edge/api/operations.py`, `state/activity.py` | `tests/performance/test_edge_targets.py`, `tests/edge/state/test_activity.py` |
| Meaningful edge-to-cloud AI workflow (GRAG answers) | `app/agents/`, `app/api/openai.py` | `tests/test_openai_api.py`, demo-acceptance offline GRAG query |
| Runs credential-free on one machine with Docker Compose | `docker-compose.yml`, `.env.example`, `scripts/demo/` | `make compose-config`, `make demo-acceptance` |
| Cloud outage degrades, no application-wide 500 | `app/edge/runtime.py`, `sync/connectivity.py` | `tests/edge/api/test_edge_status.py`, `tests/e2e/test_edge_offline_pipeline.py` |
| Optional fleet transfer (Robot A to Robot B) | `docker-compose.yml` (`robot-b-api`), `scripts/demo/fleet_transfer.py` | `tests/demo/test_fleet_transfer.py`, `make demo-robot-b` |
| Provenance disclosure of pre-existing work | `PREEXISTING_WORK.md` | linked from README |

Proof commands: `uv run pytest tests/edge tests/demo tests/e2e tests/performance`, `make demo-acceptance`, `make baseline-check`, `make compose-config`.
