# P04 policy and durable outbox execution

Branch: `codex/grag-edge-p00-baseline`

## Task 1: deterministic policy

- RED: `UV_CACHE_DIR=/private/tmp/grag-edge-uv-cache uv run pytest tests/edge/policy/test_policy_engine.py -v`
  failed during collection with `ModuleNotFoundError: No module named 'app.edge.policy'`.
- GREEN: the same command passed, 10 tests.
- Commit: `89cd809 feat: add deterministic sync policy`.

## Task 2: SQLite control plane and outbox

- RED: `UV_CACHE_DIR=/private/tmp/grag-edge-uv-cache uv run pytest tests/edge/sync/test_outbox.py tests/edge/state/test_activity.py -v`
  failed collection because `app.edge.state` did not exist.
- GREEN: focused outbox and activity tests passed, 4 tests; Task 1 and Task 2 policy/outbox/activity suite passed, 47 tests.
- Commit: `2777ad6 feat: add durable sync outbox`.

## Task 3: policy workflow, approvals, and runtime

- RED: `UV_CACHE_DIR=/private/tmp/grag-edge-uv-cache uv run pytest tests/edge/api/test_sync_policy.py -q` failed all five workflow tests before the API/runtime wiring: the records remained `LOCAL_DIRTY`, policy decisions were absent, and approval/reject routes returned 404.
- GREEN: the final command passed, 8 tests. Coverage exercises the real `EdgeRuntime` through FastAPI lifespan, policy precedence, explicit versus inferred policy, one-time approval/rejection events, stale approval rejection, GET queue, SQLite failure after the durable Qdrant write, reopened-database startup reconciliation, and concurrent approval idempotency.
- The SQLite failure test verifies the request returns 503, the persisted Qdrant record remains `LOCAL_DIRTY`, and no outbox row is exposed until `EdgeRuntime.start()` reconciles the record. Repeating startup reconciliation does not duplicate queue rows or events.
- SQLite stores only policy metadata and operational state; the test checks the policy table has no content or vector columns. Policy, outbox, and activity writes share one transaction.
- Commit: `1b8b74a feat: connect sync policy to durable outbox`.

## Final phase gate

- `UV_CACHE_DIR=/private/tmp/grag-edge-uv-cache uv run pytest tests/edge -q`: **55 passed**.
- `UV_CACHE_DIR=/private/tmp/grag-edge-uv-cache make baseline-check`: **passed**. Compose configuration and edge network topology validated. Full repository pytest reported the same 10 recorded imported baseline failures, 255 passed, 1 skipped; wrapper concluded `Pytest matches the recorded imported baseline (10 known failures); no regression`.
- `git diff --check`: passed.

## Runtime interfaces

- `EdgeRuntime.start() -> None` is async and reconciles persisted local Qdrant memories at application startup; `EdgeRuntime.close() -> None` closes store, SQLite, and embedding service.
- `MemoryService.approve(memory_id)` and `.reject(memory_id)` are async; `.reconcile()` is async and idempotent.
- `runtime.outbox.pending(limit)` returns pending/retry work; `GET /api/v1/edge/sync/queue` exposes it. No remote upload is started in P04.
