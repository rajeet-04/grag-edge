# GRAG Edge P1 Qdrant Edge Storage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a persistent embedded Qdrant Edge storage adapter behind an application-owned interface.

**Architecture:** The Edge API owns two shard directories, `mutable-local` and `immutable-fleet`. Only `app/edge/memory/qdrant_store.py` imports `qdrant_edge`; later phases consume the adapter protocol.

**Tech Stack:** Python 3.12+, qdrant-edge-py, Pydantic, pytest, uv.

**Spec:** `docs/superpowers/specs/2026-09-30-grag-edge-design.md`

## Global Constraints
- Qdrant Edge runs in-process inside FastAPI.
- Pin the resolved `qdrant-edge-py` version in `uv.lock` after smoke verification.
- Shard data persists under configurable local directories.
- Dense vector dimension is explicitly configured as `EDGE_EMBEDDING_DIMENSION=768` for the default `nomic-embed-text` model; changing the model/dimension requires a shard migration.
- Cloud availability is irrelevant to this phase.
- Exit gate: local points survive process/store reopen through the application adapter.

## Review Focus
- Reopening an existing shard must load rather than attempt `EdgeShard.create`.
- An empty/corrupt shard directory must produce an actionable storage error.
- Dense vector dimensionality mismatch must be rejected before corrupting state.
- Closing and reopening the store must preserve payload and vectors.
- Qdrant Edge beta API calls must not leak outside the adapter module.

---

### Task 1: Edge storage configuration and protocol

**Files:**
- Create: `app/edge/__init__.py`
- Create: `app/edge/memory/__init__.py`
- Create: `app/edge/memory/store.py`
- Modify: `app/config.py`
- Modify: `pyproject.toml`
- Modify: `env.example`
- Test: `tests/edge/memory/test_store_contract.py`

**Interfaces:**
- Produce: `StoredPoint(id: str, dense: list[float], sparse: Any | None, payload: dict[str, Any])`.
- Produce protocol: `EdgeMemoryStore.upsert(point: StoredPoint) -> None`, `retrieve(point_id: str) -> StoredPoint | None`, `close() -> None`.
- Produce settings: `qdrant_edge_path: Path`, `embedding_dimension: int` with environment alias `EDGE_EMBEDDING_DIMENSION` and default `768`.

- [ ] **Step 1: Write contract tests**
  Tests assert protocol implementations can upsert/retrieve a payload and reject a dense vector whose length differs from `embedding_dimension`.
- [ ] **Step 2: Run**
  Run: `uv run pytest tests/edge/memory/test_store_contract.py -v`
  Expected: FAIL because edge storage types do not exist.
- [ ] **Step 3: Add types, settings, dependency**
  Add `qdrant-edge-py` through uv so the lockfile records the exact resolved beta version.
- [ ] **Step 4: Re-run contract tests**
  Expected: tests collect; concrete-store tests remain pending/failing until Task 2.
- [ ] **Step 5: Commit**
  Commit: `feat: define edge memory storage contract`

### Task 2: Persistent Qdrant Edge adapter

**Files:**
- Create: `app/edge/memory/qdrant_store.py`
- Test: `tests/edge/memory/test_qdrant_store.py`

**Interfaces:**
- Produce: `QdrantEdgeStore(local_path: Path, fleet_path: Path, embedding_dimension: int)`.
- Produce: `open() -> None`, `upsert_local(point: StoredPoint) -> None`, `retrieve_local(point_id: str) -> StoredPoint | None`, `retrieve_fleet(point_id: str) -> StoredPoint | None`, `close() -> None`.
- Named vectors: dense `"dense"`; sparse `"text"` with `Modifier.Idf`.

- [ ] **Step 1: Write persistence tests**
  Create a temporary store, upsert one point, close, instantiate a new store against the same directory, and assert the point payload and dense vector are retrievable.
- [ ] **Step 2: Run**
  Run: `uv run pytest tests/edge/memory/test_qdrant_store.py -v`
  Expected: FAIL because `QdrantEdgeStore` is absent.
- [ ] **Step 3: Implement adapter**
  Use `EdgeShard.create` only for new directories and `EdgeShard.load` for existing shard data; configure dense cosine vectors and sparse `text` with IDF.
- [ ] **Step 4: Verify**
  Run: `uv run pytest tests/edge/memory -v`
  Expected: PASS.
- [ ] **Step 5: Commit**
  Commit: `feat: add persistent Qdrant Edge store`

**Exit gate:** a persisted local point is retrievable after closing and reopening `QdrantEdgeStore`.