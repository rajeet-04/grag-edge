# P08 execution evidence

Branch `codex/grag-edge-p00-baseline`. Commits: `8614dc2` (Task 1, edge retrieval node), `513d959` (Task 2, offline-first orchestration), `6a02061` (Task 3, ChromaDB retired).

## Gate results (actual)

- Each task had an observed RED (import error / 5 failing / 3 failing) before implementation, then GREEN.
- `uv run pytest tests/edge -q` (live env): **144 passed**.
- `EMBEDDING_MODEL=absent-embedding-model make baseline-check`: exit 0; 360 passed, 1 skipped, exactly the 10 recorded imported failures ("no regression"). The known-failures file is unchanged.
- `make compose-config`: valid. `git diff --check`: clean.
- Offline acceptance `tests/e2e/test_edge_offline_pipeline.py` (real native Qdrant Edge store, Qdrant Server unreachable, Neo4j raising, cloud keys unset, `OllamaClient` recorded): non-streaming and streaming `/v1/chat/completions` answer with `[LOCAL ...]` evidence in the LLM prompt; empty memory yields "No relevant local memory found" and no fabricated evidence; no client is created with `use_cloud=True`.

## What changed

- `edge_memory_search_node` (hybrid search, LOCAL/FLEET hits with device/revision/source/scores, `SEARCH_COMPLETED` event with mode, count, origin counts, latency). Runtime exposed to nodes via `app/edge/registry.py` set in the FastAPI lifespan.
- Graph always fans out to edge search; `kr_search` (Neo4j) is additive and degrades with a trace entry. Weak-graph vector fallback is served by edge memory (`execute_vector_fallback` now queries Qdrant Edge).
- Context builder emits an `## Edge Memory` section with provenance tags and a grounded "no relevant local memory" line.
- Local Ollama is the default for query, extractors, explanation and streaming; cloud only via explicit `LLM_USE_CLOUD=true` (new setting, default false).
- ChromaDB removed: `chroma_client.py`, the whole legacy `app/memory` package, `chromadb_path`, dependency (pyproject, requirements, uv.lock), Compose env/volume, Dockerfile dir, env examples, README. `AGENT_TOOLS` chroma tools replaced by `edge_memory_search`. `/health` reports `qdrant_edge` instead of `chromadb`.

## Rulings and deviations

- `app/memory/*` (Chroma-only short-term/episodic/semantic/firewall types) had no production callers; deleted rather than migrated to Qdrant Edge.
- `tests/test_ingestion.py::test_batch_ingestion` (a passing test) created never-awaited coroutines whose GC warning, after the Chroma import disappeared, was printed mid-output and corrupted the gate's FAILED-line parsing. The test was minimally fixed (`AsyncMock(side_effect=mock_chat)`); no baseline failure was touched and the failure set is unchanged.
- No fresh independent review was run for P08 (user-directed fast finish; the index lists one after P08).
- The worktree's untracked-by-design `.gitignore` edit (`graphify-out/`) was left uncommitted; `.env` untouched.

## Remaining issues

- Hybrid search returns even zero-relevance dense hits when memory is non-empty (no relevance threshold), so "no relevant memory" only triggers on truly empty memory.
- Query agent failure records an error that routes the graph to the error handler even if edge hits exist.
- `ranker.py` docstrings still mention Chroma distances (comment only).
