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
