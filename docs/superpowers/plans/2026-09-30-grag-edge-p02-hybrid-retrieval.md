# GRAG Edge P2 Hybrid Retrieval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provide offline dense, BM25, and hybrid retrieval across local and fleet Edge shards with provenance.

**Architecture:** Dense vectors use the existing GRAG embedding service. Qdrant Edge `Bm25(Bm25Config(language="english"))` generates sparse document/query vectors. Hybrid mode performs both searches, merges with reciprocal-rank fusion, and deduplicates by point identity.

**Tech Stack:** qdrant-edge-py, existing GRAG embedding service, pytest.

**Spec:** `docs/superpowers/specs/2026-09-30-grag-edge-design.md`

## Global Constraints
- All search works with Qdrant Server absent.
- BM25 document text uses `embed_document`; query text uses `embed_query`.
- Dense and sparse fields are named `dense` and `text`.
- Search results identify `LOCAL` or `FLEET`.
- Exit gate: semantic, exact-identifier BM25, and hybrid queries pass against local shards.

## Review Focus
- Empty query returns a validation error, not every memory.
- `Pump P-41` exact identifier search must be recoverable through BM25.
- Duplicate point returned by dense and BM25 must appear once after fusion.
- Equal-ranked results must have deterministic ordering.
- A missing/empty fleet shard must not break local-only search.

---

### Task 1: BM25 indexing and shard query primitives

**Files:**
- Modify: `app/edge/memory/qdrant_store.py`
- Create: `app/edge/memory/bm25.py`
- Test: `tests/edge/memory/test_bm25.py`

**Interfaces:**
- Produce: `EdgeBm25Indexer.embed_document(text: str) -> Any`.
- Produce: `EdgeBm25Indexer.embed_query(text: str) -> Any`.
- Extend store: `query_dense(vector: list[float], limit: int, origin: MemoryOrigin) -> list[RawSearchHit]`.
- Extend store: `query_sparse(vector: Any, limit: int, origin: MemoryOrigin) -> list[RawSearchHit]`.

- [ ] **Step 1: Write BM25 test**
  Index memories mentioning `Pump P-41` and unrelated equipment; assert BM25 query for `P-41` ranks the pump record first.
- [ ] **Step 2: Run**
  Run: `uv run pytest tests/edge/memory/test_bm25.py -v`
  Expected: FAIL.
- [ ] **Step 3: Implement BM25 wrapper and sparse store queries**
  Use `Bm25Config(language="english")`; do not substitute dense embeddings for sparse search.
- [ ] **Step 4: Verify**
  Run the BM25 test; expected PASS.
- [ ] **Step 5: Commit**
  Commit: `feat: add offline BM25 retrieval`

### Task 2: Hybrid retrieval coordinator

**Files:**
- Create: `app/edge/memory/hybrid_search.py`
- Test: `tests/edge/memory/test_hybrid_search.py`

**Interfaces:**
- Produce enums: `SearchMode.SEMANTIC`, `SearchMode.KEYWORD`, `SearchMode.HYBRID`; `MemoryOrigin.LOCAL`, `MemoryOrigin.FLEET`.
- Produce: `MemoryHit(point_id: str, score: float, origin: MemoryOrigin, dense_score: float | None, sparse_score: float | None, payload: dict[str, Any])`.
- Produce: `HybridSearchService.search(query: str, mode: SearchMode, limit: int = 10) -> list[MemoryHit]`.
- Fusion: reciprocal rank fusion with `k=60`, equal dense/sparse contribution; tie-break by `point_id`.

- [ ] **Step 1: Write semantic/hybrid/failure tests**
  Assert semantic paraphrase retrieval, exact BM25 retrieval, one result per duplicated point, deterministic ties, empty query rejection, and local search with no fleet data.
- [ ] **Step 2: Run**
  Run: `uv run pytest tests/edge/memory/test_hybrid_search.py -v`
  Expected: FAIL.
- [ ] **Step 3: Implement coordinator**
  Query both local and fleet shards for the selected mode; fuse and deduplicate without calling any remote service.
- [ ] **Step 4: Verify**
  Run: `uv run pytest tests/edge/memory/test_bm25.py tests/edge/memory/test_hybrid_search.py -v`
  Expected: PASS.
- [ ] **Step 5: Commit**
  Commit: `feat: add hybrid edge retrieval`

**Exit gate:** all three modes retrieve expected local records while no Qdrant Server is running.
