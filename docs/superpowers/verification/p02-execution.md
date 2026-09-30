# P02 Execution Record

Base: P01 commits `7ef0217` and `213b766` on `codex/grag-edge-p00-baseline`.

## Task 1: BM25 indexing and shard query primitives

- RED: `UV_CACHE_DIR=/private/tmp/grag-edge-uv-cache uv run pytest tests/edge/memory/test_bm25.py -v` failed collection with `ModuleNotFoundError: app.edge.memory.bm25` before implementation.
- Implementation uses installed `qdrant-edge-py==0.8.0`: `Bm25(Bm25Config(language="english"))`, `embed_document`, `embed_query`, and `EdgeShard.search` on named `text` sparse vectors. The `EdgeBm25Indexer` delegates through `QdrantEdgeStore`; only `qdrant_store.py` imports `qdrant_edge`.
- GREEN: same test command passed, 1 test; query for `Pump P-41` ranked its pump record first over unrelated conveyor equipment.
- Regression after Task 1: `UV_CACHE_DIR=/private/tmp/grag-edge-uv-cache uv run pytest tests/edge/memory -v` passed, 7 tests.
- Commit: `f5e10a4 feat: add offline BM25 retrieval`.

## Task 2: hybrid retrieval coordinator

- RED: `UV_CACHE_DIR=/private/tmp/grag-edge-uv-cache uv run pytest tests/edge/memory/test_hybrid_search.py -v` failed collection with `ModuleNotFoundError: app.edge.memory.hybrid_search` before implementation.
- GREEN: same command passed, 6 tests for semantic paraphrase retrieval, exact-identifier keyword retrieval, dense/sparse result deduplication, RRF scores, deterministic equal-score ordering, empty-query rejection, missing/empty fleet behavior, and fleet provenance.
- Planned retrieval verification: `UV_CACHE_DIR=/private/tmp/grag-edge-uv-cache uv run pytest tests/edge/memory/test_bm25.py tests/edge/memory/test_hybrid_search.py -v` passed, 7 tests.
- Full memory verification: `UV_CACHE_DIR=/private/tmp/grag-edge-uv-cache uv run pytest tests/edge/memory -q` passed, 13 tests.
- `git diff --check` passed.

## Regression gate

- `UV_CACHE_DIR=/private/tmp/grag-edge-uv-cache make baseline-check`: Compose configuration and edge topology checks passed. Pytest completed with 213 passed, 1 skipped, and the same 10 recorded imported baseline failures; gate reported `no regression`.

## Interfaces and rulings

- `EdgeBm25Indexer(adapter).embed_document(text)` and `.embed_query(text)` return local Qdrant sparse-vector values by delegation through the adapter.
- `QdrantEdgeStore.query_dense(vector, limit, origin)` and `.query_sparse(vector, limit, origin)` return backend-neutral `RawSearchHit` values. `MemoryOrigin` and `SearchableEdgeMemoryStore` live in `store.py`; Qdrant Edge types remain in `qdrant_store.py`.
- `HybridSearchService(store, embedding_service=None).search(query, mode, limit=10)` is async and returns `MemoryHit`; modes are semantic, keyword, and hybrid.
- Hybrid ranking combines both shards per modality, orders equal native scores by point ID, deduplicates point IDs, then applies equal-weight reciprocal-rank fusion with `k=60`; final equal fused scores also sort by point ID.
- Ruling: `search` is async — reason: the existing GRAG embedding service exposes async `embed_text` — cost if wrong: synchronous consumers must await the coordinator or use an async integration point.
- Ruling: sparse embedding delegates through the Qdrant adapter — reason: only the adapter may import qdrant-edge — cost if wrong: a future non-Qdrant backend will need to supply the same backend-neutral embedding operations.
- Ruling: an existing empty fleet directory disables fleet search while preserving local search — reason: the plan explicitly requires local-only retrieval to survive missing/empty fleet data — cost if wrong: fleet retrieval remains unavailable until its shard is repaired.
