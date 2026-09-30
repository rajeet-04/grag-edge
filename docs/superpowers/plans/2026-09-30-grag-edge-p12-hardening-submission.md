# GRAG Edge P12 Hardening and Submission Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden GRAG Edge for repeated judging runs, verify privacy/recovery/performance boundaries, and finish submission-quality documentation.

**Architecture:** This phase adds no new core capability. It closes acceptance gaps, validates restart/privacy/performance behavior, removes stale GRAG AI documentation, and produces a clean operator/demo runbook while preserving provenance disclosure.

**Tech Stack:** pytest, Docker Compose, frontend tests, shell acceptance scripts, structured logging.

**Spec:** `docs/superpowers/specs/2026-09-30-grag-edge-design.md`

## Global Constraints
- No real credentials or SaaS dependency required for the local demo.
- Preserve `PREEXISTING_WORK.md`.
- Required product must pass without optional P11.
- Performance targets: local search p95 <250 ms; memory write p95 <300 ms excluding model warm-up; status API <100 ms; connectivity UI update <2 s after detection.
- Exit gate: full tests, clean setup, docs, and reproducible judge run.

## Review Focus
- Restricted/local-only memory must never appear in captured remote upload payloads.
- Restart at each sync boundary must preserve queue/checkpoint/conflict state.
- Fresh checkout instructions must not depend on undocumented host state.
- Logs/docs must not expose API keys, credentials, or sensitive payloads.
- Demo reset must be repeatable after an interrupted prior recording.

---

### Task 1: Privacy and restart recovery suites

**Files:**
- Create: `tests/e2e/test_privacy_boundary.py`
- Create: `tests/e2e/test_restart_recovery.py`

**Interfaces:**
- Privacy tests inspect server-client calls and assert RESTRICTED/LOCAL_ONLY memories have zero remote upload attempts.
- Recovery matrix: offline restart; queued-upload restart; restart after upload before fleet refresh; unresolved-conflict restart.

- [ ] **Step 1: Write the complete failure matrix**
- [ ] **Step 2: Run**
  Expected: expose any remaining gaps.
- [ ] **Step 3: Fix only the owning subsystem defects revealed by the tests**
- [ ] **Step 4: Re-run**
  Expected: PASS.
- [ ] **Step 5: Commit**
  Commit: `test: harden privacy and restart recovery`

### Task 2: Performance and observability acceptance

**Files:**
- Create: `tests/performance/test_edge_targets.py`
- Modify: `app/edge/api/operations.py`
- Modify: `app/edge/state/sqlite.py`
- Test: `tests/edge/api/test_activity.py`

**Interfaces:**
- `GET /api/v1/edge/stats` exposes local/fleet counts, pending sync, conflicts, last sync, last fleet refresh, search latency, origin counts, sync success/failure, connectivity.
- `GET /api/v1/edge/events` emits ActivityEvent records defined by the spec.

- [ ] **Step 1: Write metrics/event/performance assertions**
- [ ] **Step 2: Run**
  Expected: FAIL for missing metrics or target regressions.
- [ ] **Step 3: Fill observability gaps and optimize only measured bottlenecks**
- [ ] **Step 4: Verify targets on the deterministic demo dataset**
- [ ] **Step 5: Commit**
  Commit: `perf: verify edge operation targets`

### Task 3: Submission-quality documentation

**Files:**
- Rewrite: `README.md`
- Modify: `SETUP.md`
- Preserve/update: `PREEXISTING_WORK.md`
- Create: `docs/ARCHITECTURE.md`
- Create: `docs/DEMO_RUNBOOK.md`
- Create: `docs/PS3_REQUIREMENTS_TRACEABILITY.md`

**Interfaces:**
- README identifies GRAG Edge, offline-first robot use case, Qdrant Edge/Qdrant Server architecture, quickstart, screenshots placeholders only if actual images exist, and provenance link.
- Traceability maps every PS3 requirement to implementation path + test/demo proof.
- Demo runbook gives exact reset/start/offline/online/conflict commands and expected UI states.

- [ ] **Step 1: Draft docs from verified commands and implemented behavior only**
- [ ] **Step 2: Validate every command from a clean checkout**
- [ ] **Step 3: Remove stale claims about ChromaDB/cloud-required GRAG operation**
- [ ] **Step 4: Run link/command sanity checks and inspect for secrets**
- [ ] **Step 5: Commit**
  Commit: `docs: prepare GRAG Edge submission package`

### Task 4: Final branch verification

**Files:**
- No product files unless verification finds a blocking defect.

**Interfaces:**
- Required verification: backend full pytest; frontend unit tests/build; `docker compose config -q`; `make demo-acceptance`.
- Optional only if shipped: `make demo-robot-b`.

- [ ] **Step 1: Run backend full suite**
  Expected: PASS.
- [ ] **Step 2: Run frontend tests and production build**
  Expected: PASS.
- [ ] **Step 3: Run Compose validation and required demo acceptance twice**
  Expected: PASS twice.
- [ ] **Step 4: Run optional fleet transfer if P11 is included**
  Expected: PASS or omit P11 from submission.
- [ ] **Step 5: Record verified commit SHA in `docs/DEMO_RUNBOOK.md` and commit**
  Commit: `chore: record submission verification`

**Exit gate:** a clean checkout can reproduce the required demo and all mandatory test gates without external SaaS credentials.
