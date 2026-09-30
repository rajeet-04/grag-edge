# P04 restart reconciliation fix

Base: `b22e755` (`docs: record verified P04 gate and runtime preparation`)

## Native reproductions

Command: `UV_CACHE_DIR=/private/tmp/grag-edge-uv-cache uv run pytest tests/edge/test_p04_reconcile_gap.py -q`

Before the fix, both real Qdrant/SQLite restart cases failed:

- A failed root policy transaction followed by a successful revision made startup reconciliation raise `logical_id already has a persisted root revision` while backfilling the root.
- A failed intermediate revision followed by a later successful Qdrant revision could not commit because the control database reported `stale persisted parent revision`.

## Fix

Reconciliation scans Qdrant histories in logical ID and revision order. Missing older revisions are restored as `SUPERSEDED`, so an old auto-policy revision cannot be queued after a newer revision committed. A later write can advance past a missing control-plane revision when its parent is the current Qdrant record; reconciliation then backfills that missing revision. Current revisions still receive their deterministic policy. Reconciliation leaves existing policy rows and terminal outbox entries intact.

Native tests cover both crash gaps, privacy-restricted history, terminal `UPLOADED` outbox preservation, and repeat-start idempotency.

## Verification

- RED: native gap tests failed 2/2 with the errors above.
- GREEN: `UV_CACHE_DIR=/private/tmp/grag-edge-uv-cache uv run pytest tests/edge/test_p04_reconcile_gap.py -q` — **3 passed**.
- Regression: `UV_CACHE_DIR=/private/tmp/grag-edge-uv-cache uv run pytest tests/edge -q` — **58 passed**.
- `UV_CACHE_DIR=/private/tmp/grag-edge-uv-cache make baseline-check` — passed compose and network validation. Full repository pytest retained the same 10 imported baseline failures, 258 passed, 1 skipped; wrapper reported no regression.
- `git diff --check` — passed.

In this isolated worktree, the first baseline-check invocation stopped because the local `.env` file was absent. Copying the tracked example to ignored `.env` allowed the required gate to complete; no environment file was staged.

The separate P05 API finding that PATCH reports a SQLite transaction failure as HTTP 500 remains with the API owner; this fix does not touch API files.
