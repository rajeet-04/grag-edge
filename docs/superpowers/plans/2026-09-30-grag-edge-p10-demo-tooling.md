# GRAG Edge P10 Demo Tooling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the complete judging story reproducible through host-side commands that create real connectivity loss and deterministic robot/fleet state.

**Architecture:** Bash scripts wrap Docker Compose and Docker network operations. Seed scripts load a fixed industrial dataset, and verification scripts poll actual API state before reporting success. The application never receives Docker socket access.

**Tech Stack:** Bash, Docker Compose, curl, jq or Python JSON fallback, Make.

**Spec:** `docs/superpowers/specs/2026-09-30-grag-edge-design.md`

## Global Constraints
- Offline simulation is a real Docker network disconnect, not an app flag.
- Demo commands fail non-zero on ambiguous state.
- Re-running reset/start must produce the same dataset and IDs.
- App containers never mount `/var/run/docker.sock`.
- Exit gate: reset → offline → operate → reconnect → synchronize succeeds repeatedly.

## Review Focus
- Running `demo-offline` twice must remain safe.
- Running `demo-online` when already online must remain safe.
- A stale Compose container ID must be resolved fresh each invocation.
- Reset must not delete unrelated Docker resources outside this project.
- Seed commands must be idempotent and verify expected record counts.

---

### Task 1: Deterministic industrial seed data

**Files:**
- Create: `demo/seed/fleet.json`
- Create: `demo/seed/robot-local.json`
- Create: `scripts/demo/seed_fleet.py`
- Create: `scripts/demo/seed_local.py`
- Test: `tests/demo/test_seed_data.py`

**Interfaces:**
- Canonical equipment IDs: `Pump P-41`, `Compressor C-17`, `Motor M-08`, `Valve V-22`.
- Seeders are idempotent by stable logical IDs and verify resulting counts.

- [ ] **Step 1: Write seed-schema/idempotency tests**
- [ ] **Step 2: Run**
  Expected: FAIL.
- [ ] **Step 3: Add deterministic datasets and seeders**
- [ ] **Step 4: Verify**
  Expected: PASS.
- [ ] **Step 5: Commit**
  Commit: `test: add deterministic GRAG Edge demo dataset`

### Task 2: Network and reset scripts

**Files:**
- Create: `scripts/demo/reset.sh`
- Create: `scripts/demo/start.sh`
- Create: `scripts/demo/offline.sh`
- Create: `scripts/demo/online.sh`
- Create: `scripts/demo/status.sh`
- Modify: `Makefile`

**Interfaces:**
- Produce Make targets: `demo-reset`, `demo-start`, `demo-offline`, `demo-online`, `demo-status`.
- Resolve Edge API container with `docker compose ps -q fastapi`.
- Disconnect/connect exact runtime network `grag-cloud-net`.
- `demo-offline` returns only after API reports OFFLINE; `demo-online` returns only after API reports ONLINE.

- [ ] **Step 1: Add shell assertions for idempotency and real API state**
- [ ] **Step 2: Run against current Compose**
  Expected: FAIL because commands do not exist.
- [ ] **Step 3: Implement scripts and Make targets**
- [ ] **Step 4: Verify two consecutive offline/online cycles**
  Expected: both cycles succeed; local API remains healthy offline.
- [ ] **Step 5: Commit**
  Commit: `feat: add deterministic network demo controls`

### Task 3: Conflict seed and full demo acceptance script

**Files:**
- Create: `scripts/demo/seed_conflict.py`
- Create: `scripts/demo/acceptance.sh`
- Modify: `Makefile`

**Interfaces:**
- Produce `make demo-conflict`.
- Produce `make demo-acceptance`: reset/start, initial sync, offline, create P-41 observation, local search/GRAG query, reconnect, queue drain, fleet refresh, synchronized-state assertion.

- [ ] **Step 1: Define assertions in acceptance script**
  Require successful local write/search while offline and eventual synchronized state after reconnect.
- [ ] **Step 2: Run**
  Expected: FAIL until flow is wired.
- [ ] **Step 3: Implement conflict seed and acceptance orchestration**
- [ ] **Step 4: Run `make demo-acceptance` twice from reset**
  Expected: PASS both times.
- [ ] **Step 5: Commit**
  Commit: `test: automate GRAG Edge judging flow`

**Exit gate:** `make demo-acceptance` passes repeatedly and uses a real Docker network cut.
