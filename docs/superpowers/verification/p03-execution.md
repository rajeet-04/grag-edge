# P03 Execution Record

Base: `964e306` (`feat: add hybrid edge retrieval`). Worktree branch: `codex/grag-edge-p00-baseline`.

## Task 1: revisioned memory domain and persistence

- RED: `UV_CACHE_DIR=/private/tmp/grag-edge-uv-cache uv run pytest tests/edge/memory/test_memory_service.py -v` failed collection with `ModuleNotFoundError: app.edge.memory.models`.
- Implementation: immutable per-revision records with stable logical identity, SHA-256 content hashes, optimistic parent revision checks, duplicate point-ID rejection, dense document embeddings, sparse BM25 vectors, persistent history via adapter `list_points()` backed by Qdrant Edge scroll.
- GREEN: same command passed, 3 tests, including real Qdrant Edge reopen after two revisions and tombstone; history and deleted current-state remained correct.
- Commit: `0cc767c feat: add revisioned robot memory model`.

## Task 2: API and runtime

- Process deviation: router/runtime wiring was initially drafted before the task-specific RED. The implementation files and `app/main.py` patch were saved under `/private/tmp/grag-edge-p03-task2-backup`, removed from the worktree, and restored only after observing the test failure below. The API implementation therefore has a recorded pre-implementation test state, though the first draft preceded that observation.
- RED: `UV_CACHE_DIR=/private/tmp/grag-edge-uv-cache uv run pytest tests/edge/api/test_memories.py tests/edge/test_runtime.py -v` failed collection with `ModuleNotFoundError: app.edge.runtime` for both modules.
- GREEN: `UV_CACHE_DIR=/private/tmp/grag-edge-uv-cache uv run pytest tests/edge/memory/test_memory_service.py tests/edge/api/test_memories.py tests/edge/test_runtime.py -v` passed, 7 tests. API tests run through `app.main`'s actual lifespan with stubbed Neo4j and an injected single `EdgeRuntime`, verifying startup state and clean store close/reset. They cover create/get/revise/search, all eight list filters, 404/422 behavior, score and provenance response fields, and hiding stale and tombstoned revisions.
- Memory regressions: `UV_CACHE_DIR=/private/tmp/grag-edge-uv-cache uv run pytest tests/edge/memory -q` passed, 16 tests.
- `git diff --check` passed.
- `UV_CACHE_DIR=/private/tmp/grag-edge-uv-cache make baseline-check` exited 0: compose and edge topology checks passed; pytest reported 220 passed, 1 skipped, 10 known imported failures, then `no regression`. Failure list matched P02: `tests/agents/test_explanation_agent.py::TestReasoningStepsWithConfidence::test_more_steps_than_paths`; `...::test_empty_paths`; `tests/integration/test_ollama_client.py::TestOllamaClient::test_client_initialization_cloud`; `tests/services/test_entity_resolution.py::TestValidationService::test_validation_accuracy_calculation`; `...::test_validation_precision_recall_f1`; `...::test_threshold_analysis`; `tests/services/test_entity_resolution.py::TestEdgeCases::test_paris_city_vs_company`; `tests/services/test_similarity_service.py::TestSimilarityService::test_compute_similarity_weights`; `...::test_compute_similarity_fallback_to_names`; `...::test_handle_entity_pair`.
- `app/edge/memory/hybrid_search.py` exposes async `HybridSearchService.search(query, mode, limit=10) -> list[MemoryHit]`; API awaits it. Memory writes are also async because `EmbeddingService.embed_with_context` is async.
- P02's boundary remains intact: only `app/edge/memory/qdrant_store.py` imports `qdrant_edge` types; memory/API/runtime use the application interfaces.

## Rulings

- Ruling: list/history obtains persisted points through an adapter `list_points()` extension implemented with Qdrant Edge `scroll` — reason: restart-safe history and current-revision suppression cannot rely on process memory — cost if wrong: scanning the mutable shard may become expensive as the local corpus grows.
- Ruling: API search filters hits against the persisted latest logical revision — reason: immutable old vectors remain indexed, and tombstones must not make an older revision visible — cost if wrong: retrieving the latest-state map per search adds a full local-point scan to API requests.
- Ruling: the API write/search interfaces are async — reason: local dense embeddings use the existing asynchronous embedding service — cost if wrong: synchronous callers must adapt to async service use.
