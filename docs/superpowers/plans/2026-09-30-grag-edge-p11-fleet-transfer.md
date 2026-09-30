# GRAG Edge P11 Fleet Transfer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the optional Robot A → Fleet → Robot B knowledge-transfer demonstration without destabilizing the required single-robot product.

**Architecture:** A second Edge API instance uses the same application image and fleet Qdrant Server but separate Edge shard and SQLite volumes. It starts only under the `fleet-demo` Compose profile.

**Tech Stack:** Docker Compose profiles, existing Edge API image, Qdrant Server, pytest/demo scripts.

**Spec:** `docs/superpowers/specs/2026-09-30-grag-edge-design.md`

## Global Constraints
- P11 is optional; P10 remains fully functional without it.
- Robot B uses `DEVICE_ID=ROBOT-02`.
- Robot B must never share mutable shard or SQLite files with Robot A.
- Knowledge reaches B only through fleet/server synchronization.
- Exit gate: a memory created offline on A becomes a FLEET result on B after A upload and B refresh.

## Review Focus
- Starting Robot B must not alter Robot A local state.
- Robot B must not see A’s unsynchronized memory.
- After sync, B must identify provenance as FLEET and originating device as ROBOT-01.
- Restarting B must preserve its own fleet checkpoint independently.
- `docker compose up` without profiles must not start Robot B.

---

### Task 1: Optional Robot B runtime

**Files:**
- Modify: `docker-compose.yml`
- Modify: `env.example`
- Test: `tests/demo/test_fleet_profile.py`

**Interfaces:**
- Add service `robot-b-api` under profile `fleet-demo`.
- Separate volumes/paths: Robot B Qdrant Edge data and Robot B SQLite state.
- Optional host port `8002:8000` for demonstration/debug.

- [ ] **Step 1: Write Compose topology assertions**
- [ ] **Step 2: Run**
  Expected: FAIL.
- [ ] **Step 3: Add profile service and isolated storage**
- [ ] **Step 4: Verify**
  Default Compose excludes Robot B; profile includes it.
- [ ] **Step 5: Commit**
  Commit: `feat: add optional second edge robot`

### Task 2: Fleet-transfer scenario

**Files:**
- Create: `scripts/demo/fleet_transfer.py`
- Modify: `Makefile`
- Test: `tests/demo/test_fleet_transfer.py`

**Interfaces:**
- Produce `make demo-robot-b`.
- Scenario: seed A offline memory → assert B cannot retrieve → reconnect/sync A → refresh B → assert B retrieves same logical memory with origin FLEET and source device ROBOT-01.

- [ ] **Step 1: Write transfer acceptance test**
- [ ] **Step 2: Run**
  Expected: FAIL.
- [ ] **Step 3: Implement scenario using public APIs only**
- [ ] **Step 4: Verify**
  Run twice from reset; expected PASS.
- [ ] **Step 5: Commit**
  Commit: `feat: demonstrate robot-to-fleet knowledge transfer`

**Exit gate:** `make demo-robot-b` proves A’s synchronized lesson reaches B through Qdrant Server and not through shared local storage.
