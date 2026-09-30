# GRAG Edge P3 Memory Provenance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn generic stored points into revisioned robot memories with provenance and memory inspection APIs.

**Architecture:** `MemoryService` owns memory identity, hashing, revision creation, tombstones, and conversion to Qdrant payloads. API routers never manipulate EdgeShard directly.

**Tech Stack:** FastAPI, Pydantic v2, Qdrant Edge adapter, pytest/httpx.

**Spec:** `docs/superpowers/specs/2026-09-30-grag-edge-design.md`

## Global Constraints
- `memory_id` identifies an immutable revision; `logical_id` identifies the evolving memory.
- Updates create a new revision and never mutate prior history.
- Deletion is tombstone-based for revisioned/synchronized memory.
- Every result preserves device/source provenance.
- Exit gate: revision and provenance history is persisted and inspectable through the API.

## Review Focus
- Client-supplied duplicate `memory_id` must not overwrite an existing revision.
- Editing from a stale `parent_revision` must be rejected or surfaced for later conflict handling.
- Tombstoned memories must be excluded from normal search.
- Missing optional confidence/tags must serialize consistently.
- Hashing must be deterministic across process restarts.

---

### Task 1: Robot memory domain model

**Files:**
- Create: `app/edge/memory/models.py`
- Create: `app/edge/memory/service.py`
- Test: `tests/edge/memory/test_memory_service.py`

**Interfaces:**
- Produce enums: `MemoryType`, `Importance`, `Sensitivity`, `SyncPolicy`, `SyncState`.
- Produce `MemoryRecord` with the fields fixed in the spec plus `is_deleted: bool = False`.
- Produce: `MemoryService.create(command: CreateMemory) -> MemoryRecord`.
- Produce: `MemoryService.revise(logical_id: str, command: ReviseMemory) -> MemoryRecord`.
- Produce: `MemoryService.get(memory_id: str) -> MemoryRecord | None`.
- Produce: `MemoryService.history(logical_id: str) -> list[MemoryRecord]`.
- Produce: `MemoryService.tombstone(logical_id: str) -> MemoryRecord`.

- [ ] **Step 1: Write revision/provenance tests**
  Assert revision starts at 1, revise produces revision 2 with parent 1, old revision remains retrievable, deterministic content hash, and tombstone hides current memory from normal search.
- [ ] **Step 2: Run**
  Run: `uv run pytest tests/edge/memory/test_memory_service.py -v`
  Expected: FAIL.
- [ ] **Step 3: Implement domain service**
  Keep all ID/revision/hash rules in `MemoryService`, not routers.
- [ ] **Step 4: Verify**
  Expected: PASS.
- [ ] **Step 5: Commit**
  Commit: `feat: add revisioned robot memory model`

### Task 2: Memory and search API

**Files:**
- Create: `app/edge/api/__init__.py`
- Create: `app/edge/api/memories.py`
- Modify: `app/main.py`
- Test: `tests/edge/api/test_memories.py`

**Interfaces:**
- Produce endpoints: `POST /api/v1/edge/memories`, `GET /api/v1/edge/memories`, `GET /api/v1/edge/memories/{id}`, `PATCH /api/v1/edge/memories/{id}`, `POST /api/v1/edge/search`.
- Search response exposes origin, combined score, dense score, sparse score, revision, and sync state.

- [ ] **Step 1: Write API tests**
  Assert create/get/revise/list/search success, 404 for unknown ID, 422 for empty search query, and provenance fields in responses.
- [ ] **Step 2: Run**
  Run: `uv run pytest tests/edge/api/test_memories.py -v`
  Expected: FAIL.
- [ ] **Step 3: Implement router using `MemoryService` and `HybridSearchService`**
- [ ] **Step 4: Verify**
  Run memory service and API tests; expected PASS.
- [ ] **Step 5: Commit**
  Commit: `feat: expose edge memory API`

**Exit gate:** a robot memory can be created, revised, searched, and inspected with immutable history and provenance.
