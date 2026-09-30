# GRAG Edge P4 Policy and Durable Outbox Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Classify local memories for synchronization and persist synchronization work across restarts.

**Architecture:** A deterministic `SyncPolicyEngine` evaluates privacy and operational metadata. Accepted work is inserted into a SQLite outbox in the same application workflow as the policy decision; SQLite stores control-plane state only.

**Tech Stack:** Python sqlite3, Pydantic, FastAPI, pytest.

**Spec:** `docs/superpowers/specs/2026-09-30-grag-edge-design.md`

## Global Constraints
- `restricted` and explicit `local_only` can never produce an upload item.
- Privacy rules outrank optional AI recommendations.
- Outbox state survives process/container restarts.
- No remote upload is attempted in this phase.
- Exit gate: deterministic policy + restart-safe queue pass tests.

## Review Focus
- CRITICAL + RESTRICTED must still remain local.
- Re-evaluating one memory must not create duplicate active outbox rows.
- Approval-required memory must not enter QUEUED before approval.
- SQLite transaction failure must not leave memory marked queued without an outbox row.
- Restart must preserve retry count and existing pending work.

---

### Task 1: Deterministic sync policy

**Files:**
- Create: `app/edge/policy/__init__.py`
- Create: `app/edge/policy/rules.py`
- Create: `app/edge/policy/engine.py`
- Test: `tests/edge/policy/test_policy_engine.py`

**Interfaces:**
- Produce: `SyncDecision(action: SyncPolicy, reason_codes: tuple[str, ...])`.
- Produce: `SyncPolicyEngine.evaluate(memory: MemoryRecord) -> SyncDecision`.
- Rule precedence: restricted → local_only; explicit local_only → local_only; approval-required operator note → approval_required; high/critical fleet-safe incident with sufficient confidence → auto; low-importance routine observation → local_only; fleet-safe learned maintenance fact → auto.

- [ ] **Step 1: Write table-driven policy tests**
  Include CRITICAL+RESTRICTED and all rule examples from the spec.
- [ ] **Step 2: Run**
  Run: `uv run pytest tests/edge/policy/test_policy_engine.py -v`
  Expected: FAIL.
- [ ] **Step 3: Implement ordered deterministic rules**
- [ ] **Step 4: Verify**
  Expected: PASS.
- [ ] **Step 5: Commit**
  Commit: `feat: add deterministic sync policy`

### Task 2: SQLite control plane and outbox

**Files:**
- Create: `app/edge/state/__init__.py`
- Create: `app/edge/state/sqlite.py`
- Create: `app/edge/sync/__init__.py`
- Create: `app/edge/sync/outbox.py`
- Modify: `app/config.py`
- Test: `tests/edge/sync/test_outbox.py`

**Interfaces:**
- Produce: `EdgeStateDB(path: Path)` migrations for `sync_outbox`, `sync_attempts`, `sync_checkpoints`, `activity_events`, `device_state`, `conflicts`.
- Produce: `SyncOutbox.enqueue(memory_id: str, logical_id: str, revision: int) -> OutboxItem`.
- Produce: `pending(limit: int) -> list[OutboxItem]`, `mark_uploading(id)`, `mark_retry(id, error)`, `mark_uploaded(id)`.
- Enforce one active outbox item per `(logical_id, revision)`.

- [ ] **Step 1: Write persistence/idempotency tests**
  Close and reopen SQLite between enqueue and read; assert row survives and duplicate enqueue returns the existing active item.
- [ ] **Step 2: Run**
  Run: `uv run pytest tests/edge/sync/test_outbox.py -v`
  Expected: FAIL.
- [ ] **Step 3: Implement schema and repository**
  Use explicit transactions; no ORM required.
- [ ] **Step 4: Verify**
  Expected: PASS.
- [ ] **Step 5: Commit**
  Commit: `feat: add durable sync outbox`

### Task 3: Policy-to-outbox workflow and approvals

**Files:**
- Modify: `app/edge/memory/service.py`
- Create: `app/edge/api/sync.py`
- Test: `tests/edge/api/test_sync_policy.py`

**Interfaces:**
- Produce: `POST /api/v1/edge/sync/{memory_id}/approve`.
- Produce: `POST /api/v1/edge/sync/{memory_id}/reject`.
- Produce: `GET /api/v1/edge/sync/queue`.
- Creating/revising a memory stores the final policy reason and creates outbox work only for AUTO or approved records.

- [ ] **Step 1: Write workflow tests**
  Assert restricted memory never enters queue, approval-required memory queues only after approval, reject sets local-only outcome, and duplicate approval is idempotent.
- [ ] **Step 2: Run**
  Expected: FAIL.
- [ ] **Step 3: Implement workflow**
- [ ] **Step 4: Verify**
  Run policy, outbox, and API tests; expected PASS.
- [ ] **Step 5: Commit**
  Commit: `feat: connect sync policy to durable outbox`

**Exit gate:** policy decisions are inspectable and queued work survives a process restart without privacy-rule violations.
