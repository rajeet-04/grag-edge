# P05 execution evidence

P05 implements durable upload of eligible edge memories to the fleet Qdrant server. P06 completion semantics remain intentionally out of scope: uploads stop at `UPLOADED`; they do not mark memories `SYNCHRONIZED` or emit `SYNC_COMPLETED`.

## TDD and implementation

- Server client: the initial focused test collection was RED because `app.edge.sync.server_client` did not exist; after implementation, the focused client tests passed (3 passed).
- Connectivity: the initial focused test collection was RED because the connectivity module did not exist; after implementation, the server and connectivity tests passed (4 passed).
- Upload worker: the initial focused test collection was RED because `app.edge.sync.service` did not exist. The implementation added durable retries, restart recovery, eligibility/policy checks immediately before payload creation, and idempotent Qdrant upserts. SQLite-overlaid policy is used instead of the raw vector payload default.
- API/runtime coverage verifies offline local readiness, local create/revise/search, async sync requests, persisted SSE replay, lifecycle shutdown, and PATCH database errors returning 503.

## Verification

- `UV_CACHE_DIR=/private/tmp/grag-edge-uv-cache uv run pytest tests/edge -q`: **72 passed**, 24 warnings.
- `PATH=/private/tmp/grag-edge-runtime/bin:$PATH DOCKER_HOST=tcp://127.0.0.1:23750 UV_CACHE_DIR=/private/tmp/grag-edge-uv-cache make baseline-check`: **exit 0**; full suite 272 passed, 1 skipped, and exactly 10 previously recorded imported failures, with no baseline regression.
- `docker-compose config -q` and `git diff --check`: passed.

## Real Docker network gate

Executed against the isolated Docker Engine 29.8.1 (`overlay2`), cached Qdrant 1.17.1, and CPU Ollama image `grag-edge-ollama:cpu` with the local embedding and generation models. Compose uses named data volumes. Qdrant is only on the cloud network with no published host ports; Ollama is only on the edge network; API joins both.

- With API cloud connectivity disconnected, API status transitioned to `READY/OFFLINE`. Actual local Ollama embedding-backed create, revise, and hybrid search requests succeeded; eligible revisions queued and a restricted record stayed local-only.
- Reconnecting cloud connectivity drained eligible work. The newest revision uploaded, its older revision was superseded, and restricted data remained local-only.
- Restarted API while Qdrant/cloud was unavailable: startup reached `READY/OFFLINE`, local records remained searchable, and a new eligible record queued. Restoring Qdrant/network returned connectivity to online and uploaded the queued record.
- Verified the real Qdrant collection schema (one shard, 768-dimensional dense vectors, sparse `text` vector with IDF modifier). Repeating an upsert for the same point left the exact collection count unchanged, confirming idempotency.
- During runtime validation, an explicitly empty Qdrant API-key setting caused an authentication error; omitting the empty key corrected the configuration and restored ONLINE status.

P05 is complete at the `UPLOADED` boundary. Synchronization completion and snapshot semantics remain for P06.

## Review corrections

The P05 review reproduced three upload lifecycle defects and one shutdown race. Regression tests first failed because a SQL policy change after point materialization attempted to cancel an active claim, successful uploads had no `sync_attempts` row, and runtime shutdown returned while a blocking cloud health probe was still running. The fix makes claim/state/attempt creation and terminal/retry policy updates atomic in SQLite; pre-send denial can cancel the worker's claim; materialization and eligibility exceptions become recorded retries; interrupted attempts are recorded and numbered before restart retry. The final outbound `StoredPoint` is a copy projected with effective SQLite policy and accepted `UPLOADED` state. Blocking cloud calls are shielded and awaited after coroutine cancellation, so owned store/database/client resources remain open until the bounded call finishes.

- Retained regression coverage: policy change during materialization cancels without sending, preparation failure records retry, success records an attempt, claim SQL failure rolls back both rows, and close waits for an in-flight connectivity probe.
- Post-review verification: `UV_CACHE_DIR=/private/tmp/grag-edge-uv-cache uv run pytest tests/edge -q` completed with **83 passed, 1 skipped**. `PATH=/private/tmp/grag-edge-runtime/bin:$PATH DOCKER_HOST=tcp://127.0.0.1:23750 UV_CACHE_DIR=/private/tmp/grag-edge-uv-cache make baseline-check` exited 0: **283 passed, 2 skipped, and exactly 10 recorded imported failures**; the baseline validator reported no regression.

## Attempt history lifecycle correction

Focused tests were RED (3 failures) because attempt rows lacked `started_at`, `finished_at`, and a terminal result, and older SQLite databases were not migrated. The additive migration preserves `created_at` as `started_at` and infers prior outcomes where possible. New attempts begin as `RUNNING`; upload, retry, cancellation, and restart recovery atomically finalize them as `SUCCESS`, `FAILED`, `CANCELLED`, and `INTERRUPTED` respectively.

- `UV_CACHE_DIR=/private/tmp/grag-edge-uv-cache uv run pytest tests/edge/sync/test_outbox.py -q`: **7 passed**.
- `UV_CACHE_DIR=/private/tmp/grag-edge-uv-cache uv run pytest tests/edge -q`: **91 passed, 1 skipped**.
- `PATH=/private/tmp/grag-edge-runtime/bin:$PATH DOCKER_HOST=tcp://127.0.0.1:23750 UV_CACHE_DIR=/private/tmp/grag-edge-uv-cache make baseline-check`: exit 0, **291 passed, 2 skipped, exact 10 known imported failures**; baseline validator reported no regression.
- Repeated both gates from a clean `git archive` of commit `bd1d5b5`, excluding in-progress P06 working-tree files: edge suite **91 passed, 1 skipped**; baseline validator **291 passed, 2 skipped, exact same 10 known imported failures**, no regression.

## Legacy history migration correction

A migration regression was RED because the first migration inferred attempt outcomes and timestamps from legacy `error`/outbox status. Those fields cannot reliably recover when an attempt started or ended, so the migration now preserves legacy `created_at`, `error`, and outbox status while marking the result `LEGACY_UNKNOWN` and leaving `started_at`/`finished_at` null. New attempts still record complete lifecycle data.

- The expanded legacy fixture was RED against inferred history, then passed with the unknown-history migration. Clean archive of commit `6b169e8` (excluding untracked P06 work): edge suite **93 passed, 1 skipped**; baseline-check exit 0 with **293 passed, 2 skipped, and exactly 10 known imported failures**, no regression.
