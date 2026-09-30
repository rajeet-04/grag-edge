# GRAG Edge P7 Conflicts and Deduplication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent duplicate synchronized results and preserve divergent offline edits through explicit conflict resolution.

**Architecture:** The retrieval merge layer selects a canonical revision by logical identity, revision, content hash, and synchronization boundary. Conflict detection compares local and fleet ancestry for conflict-sensitive memory types; conflicts are persisted in SQLite and resolved by creating a new revision.

**Tech Stack:** Python, SQLite, Qdrant Edge payload filters, FastAPI, pytest.

**Spec:** `docs/superpowers/specs/2026-09-30-grag-edge-design.md`

## Global Constraints
- Never use universal last-write-wins.
- Observations/incidents/sensor events are append-oriented, not conflict-oriented.
- Procedure/configuration and same-logical-id learned facts require divergent-edit detection.
- Resolution never rewrites historical revisions.
- Exit gate: dedupe and all three conflict resolution paths pass.

## Review Focus
- Same content/revision in both shards appears once.
- Higher revision must win over an older equivalent logical record.
- Same revision with different content hash becomes conflict for sensitive types.
- Resolving an already-resolved conflict is idempotent and does not create extra revisions.
- Local cleanup must not delete a revision until fleet confirmation crosses its sync boundary.

---

### Task 1: Canonical deduplication and safe local cleanup

**Files:**
- Modify: `app/edge/memory/hybrid_search.py`
- Create: `app/edge/memory/dedupe.py`
- Modify: `app/edge/sync/service.py`
- Test: `tests/edge/memory/test_dedupe.py`

**Interfaces:**
- Produce: `dedupe_hits(hits: Sequence[MemoryHit]) -> list[MemoryHit]`.
- Canonical key is `logical_id`; prefer highest revision; same revision prefers FLEET only when content hash is equal and fleet confirmation exists.
- Produce: `SyncService.cleanup_confirmed_local(sync_timestamp: float) -> int`.

- [ ] **Step 1: Write canonicalization/cleanup tests**
- [ ] **Step 2: Run**
  Expected: FAIL.
- [ ] **Step 3: Implement deterministic dedupe and confirmed-only cleanup**
- [ ] **Step 4: Verify**
  Expected: PASS.
- [ ] **Step 5: Commit**
  Commit: `feat: deduplicate synchronized edge memory`

### Task 2: Conflict detector and persistence

**Files:**
- Create: `app/edge/conflicts/__init__.py`
- Create: `app/edge/conflicts/service.py`
- Test: `tests/edge/conflicts/test_conflict_detection.py`

**Interfaces:**
- Produce: `ConflictService.detect(local: MemoryRecord, fleet: MemoryRecord) -> ConflictRecord | None`.
- Conflict when both descend from the same base, content differs, and type is conflict-sensitive.
- Produce: `list_open() -> list[ConflictRecord]`, `get(conflict_id: str) -> ConflictRecord | None`.

- [ ] **Step 1: Write detection matrix**
  Cover procedure divergence, learned-fact divergence, append-only observation, identical revisions, and differing logical IDs.
- [ ] **Step 2: Run**
  Expected: FAIL.
- [ ] **Step 3: Implement detector and SQLite repository**
- [ ] **Step 4: Verify**
  Expected: PASS.
- [ ] **Step 5: Commit**
  Commit: `feat: detect divergent edge memory revisions`

### Task 3: Conflict API and resolution

**Files:**
- Create: `app/edge/api/conflicts.py`
- Modify: `app/main.py`
- Test: `tests/edge/api/test_conflicts.py`

**Interfaces:**
- Produce endpoints: `GET /api/v1/edge/conflicts`, `GET /api/v1/edge/conflicts/{id}`, `POST /api/v1/edge/conflicts/{id}/resolve`.
- Resolution enum: `KEEP_LOCAL`, `ACCEPT_FLEET`, `MERGE`.
- `MERGE` requires merged content and creates the next revision through `MemoryService.revise`.

- [ ] **Step 1: Write API tests for all resolutions**
  Assert history preservation and idempotent second resolution request.
- [ ] **Step 2: Run**
  Expected: FAIL.
- [ ] **Step 3: Implement API/service resolution flow**
- [ ] **Step 4: Verify**
  Run conflict, dedupe, and API tests; expected PASS.
- [ ] **Step 5: Commit**
  Commit: `feat: add explicit memory conflict resolution`

**Exit gate:** divergent procedure revisions become CONFLICTED, every resolution preserves history, and synchronized duplicates collapse to one result.
