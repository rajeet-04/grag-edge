# GRAG Edge P0 Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the imported GRAG baseline reproducible in containers and establish the command surface every later phase uses.

**Architecture:** Preserve the imported application behavior while adding deterministic developer commands and explicit edge-network naming. Do not introduce Qdrant Edge behavior yet.

**Tech Stack:** Python 3.12+, uv, pytest, Docker Compose, GNU Make or compatible make.

**Spec:** `docs/superpowers/specs/2026-09-30-grag-edge-design.md`

## Global Constraints
- One physical machine; Docker Compose is the judging runtime.
- Existing GRAG behavior remains intact in this phase.
- No Qdrant Edge feature code in P0.
- Do not commit secrets or generated runtime databases.
- Exit gate: baseline tests/build understood and Docker baseline reproducible.

## Review Focus
- Missing `.env` must fail with an actionable setup message, not an opaque Compose error.
- Systems without an NVIDIA runtime must have a documented CPU-compatible verification path.
- Re-running baseline setup must be idempotent.
- Generated Qdrant/SQLite/Chroma runtime files must remain ignored.
- Existing GRAG unit tests must not be silently skipped.

---

### Task 1: Reproducible project command surface

**Files:**
- Create: `Makefile`
- Create: `scripts/dev/verify_baseline.sh`
- Modify: `.gitignore`
- Modify: `.env.example`

**Interfaces:**
- Produces: `make test`, `make compose-config`, `make baseline-check`.
- Produces: `scripts/dev/verify_baseline.sh` returning non-zero on invalid Compose/topology checks or on any pytest regression relative to the recorded imported baseline. The exact imported-baseline failing node IDs are stored in `docs/superpowers/verification/2026-09-30-grag-edge-p00-known-failures.txt`.

- [ ] **Step 1: Write the verification expectations**
  Add shell-level checks in `scripts/dev/verify_baseline.sh` for `uv run pytest -q` and `docker compose config -q`. Capture pytest failing node IDs and compare them against `docs/superpowers/verification/2026-09-30-grag-edge-p00-known-failures.txt`: exact match is an accepted imported baseline; any new, missing, or changed failing node ID is a regression and must return non-zero.
- [ ] **Step 2: Run the script before Make targets exist**
  Run: `bash scripts/dev/verify_baseline.sh`
  Expected: FAIL at the missing/unfinished command surface.
- [ ] **Step 3: Implement the command surface**
  Add exact Make targets `test`, `compose-config`, and `baseline-check`. Extend `.gitignore` for `data/qdrant-edge/`, `data/edge-state.db*`, `frontend/node_modules/`, and built frontend output. Keep `.env.example` secret-free. Record the exact imported-baseline failing pytest node IDs in `docs/superpowers/verification/2026-09-30-grag-edge-p00-known-failures.txt` and keep the human-readable verification report alongside it.
- [ ] **Step 4: Verify**
  Run: `make baseline-check`
  Expected: Compose config validates and pytest is either fully green or has exactly the recorded imported-baseline failure set with no regression.
- [ ] **Step 5: Commit**
  Commit: `chore: establish reproducible GRAG Edge baseline`

### Task 2: Explicit edge network without behavior change

**Files:**
- Modify: `docker-compose.yml`
- Test: `scripts/dev/verify_baseline.sh`

**Interfaces:**
- Produces: Docker network name `grag-edge-net`.
- Consumes: existing `fastapi`, `ollama`, `neo4j`, and `open-webui` services.

- [ ] **Step 1: Add a failing topology assertion**
  Verify rendered Compose contains `grag-edge-net` and the existing services remain attached to it.
- [ ] **Step 2: Run assertion**
  Run: `make baseline-check`
  Expected: FAIL because the named network does not exist yet.
- [ ] **Step 3: Declare and attach `grag-edge-net`**
  Do not add `grag-cloud-net` or Qdrant Server yet.
- [ ] **Step 4: Verify**
  Run: `make baseline-check`
  Expected: PASS when Compose/topology checks succeed and pytest is either green or exactly matches the recorded imported-baseline failure set.
- [ ] **Step 5: Commit**
  Commit: `chore: name GRAG Edge local network`

**Exit gate:** `make baseline-check` passes from a clean checkout with documented prerequisites.