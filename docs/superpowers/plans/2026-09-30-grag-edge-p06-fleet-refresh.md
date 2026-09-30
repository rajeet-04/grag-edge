# GRAG Edge P6 Fleet Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bootstrap and incrementally refresh the immutable fleet Edge shard from Qdrant Server snapshots without blocking local writes.

**Architecture:** A snapshot client downloads the server shard snapshot for first bootstrap, then posts the current `snapshot_manifest()` to Qdrant’s partial snapshot endpoint and applies it with `update_from_snapshot()`. Only the fleet shard is locked during apply; robot writes continue to the mutable local shard.

**Tech Stack:** qdrant-edge-py snapshot API, httpx, Qdrant Server, asyncio locks, pytest.

**Spec:** `docs/superpowers/specs/2026-09-30-grag-edge-design.md`

## Global Constraints
- Full bootstrap endpoint: `GET /collections/{collection}/shards/0/snapshot`.
- Partial refresh endpoint: `POST /collections/{collection}/shards/0/snapshot/partial/create` with the current manifest.
- Python applies partial snapshots via `EdgeShard.update_from_snapshot(snapshot_path)`.
- Failed refresh preserves the previous valid fleet shard.
- Local mutable writes remain available during fleet refresh.
- Exit gate: initial full bootstrap and later partial refresh are both verified.

## Review Focus
- Interrupted snapshot download must never replace the active fleet shard.
- Invalid snapshot payload must leave the previous fleet shard queryable.
- Refresh with no remote changes must be harmless and idempotent.
- Local writes during fleet refresh must still succeed.
- A process restart after download but before apply must recover without a half-installed fleet shard.

---

### Task 1: Full fleet bootstrap

**Files:**
- Create: `app/edge/sync/snapshot.py`
- Modify: `app/edge/memory/qdrant_store.py`
- Test: `tests/edge/sync/test_snapshot_bootstrap.py`

**Interfaces:**
- Produce: `FleetSnapshotService.bootstrap_if_missing() -> FleetRefreshResult`.
- Produce: `QdrantEdgeStore.replace_fleet_from_snapshot(snapshot_path: Path) -> None`.
- Bootstrap downloads to a sibling temporary directory/file, unpacks there, validates load, then atomically swaps the fleet directory reference/path.

- [ ] **Step 1: Write bootstrap safety tests**
  Assert successful bootstrap makes server data searchable, invalid download leaves previous/empty valid fleet state untouched, and restart ignores orphaned temp artifacts.
- [ ] **Step 2: Run**
  Run: `uv run pytest tests/edge/sync/test_snapshot_bootstrap.py -v`
  Expected: FAIL.
- [ ] **Step 3: Implement full bootstrap**
  Use `EdgeShard.unpack_snapshot` followed by `EdgeShard.load` validation before activating the downloaded shard.
- [ ] **Step 4: Verify**
  Expected: PASS.
- [ ] **Step 5: Commit**
  Commit: `feat: bootstrap fleet memory from Qdrant snapshot`

### Task 2: Partial snapshot refresh

**Files:**
- Modify: `app/edge/sync/snapshot.py`
- Modify: `app/edge/memory/qdrant_store.py`
- Test: `tests/edge/sync/test_partial_refresh.py`

**Interfaces:**
- Produce: `FleetSnapshotService.refresh() -> FleetRefreshResult`.
- Produce: `QdrantEdgeStore.fleet_manifest() -> dict[str, Any]`.
- Produce: `QdrantEdgeStore.apply_fleet_snapshot(snapshot_path: Path) -> None`.
- Store a successful refresh checkpoint in `sync_checkpoints`.

- [ ] **Step 1: Write partial-refresh tests**
  Seed fleet revision A, capture manifest, change server to revision B, request partial snapshot, apply it, and assert B is searchable. Assert failed apply keeps A.
- [ ] **Step 2: Run**
  Expected: FAIL.
- [ ] **Step 3: Implement partial refresh**
  Hold a fleet-only `asyncio.Lock` around apply; do not lock mutable-local writes.
- [ ] **Step 4: Verify**
  Run bootstrap + partial-refresh tests; expected PASS.
- [ ] **Step 5: Commit**
  Commit: `feat: refresh fleet memory with partial snapshots`

### Task 3: Sync lifecycle integration

**Files:**
- Modify: `app/edge/sync/service.py`
- Modify: `app/edge/api/sync.py`
- Test: `tests/edge/sync/test_sync_refresh_flow.py`

**Interfaces:**
- After all current uploads are acknowledged, sync run may transition UPLOADED → SNAPSHOT_PENDING → SYNCHRONIZED only after a successful fleet refresh.
- Produce history endpoint: `GET /api/v1/edge/sync/history`.

- [ ] **Step 1: Write lifecycle test**
  Assert an uploaded memory is not SYNCHRONIZED until the refreshed fleet shard contains the acknowledged revision.
- [ ] **Step 2: Run**
  Expected: FAIL.
- [ ] **Step 3: Integrate refresh into sync service**
- [ ] **Step 4: Verify**
  Run all `tests/edge/sync`; expected PASS.
- [ ] **Step 5: Commit**
  Commit: `feat: complete bidirectional sync lifecycle`

**Exit gate:** server-seeded fleet data bootstraps locally; later server changes arrive via partial refresh; failed refresh preserves the last valid fleet shard.
