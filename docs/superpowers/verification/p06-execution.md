# P06 execution evidence

## Task 1 — full bootstrap

- RED: `uv run pytest tests/edge/sync/test_snapshot_bootstrap.py -q` failed collection with `ModuleNotFoundError: app.edge.sync.snapshot` before implementation.
- GREEN: focused bootstrap plus memory regression suite: **19 passed**.
- Ruling: publish independent generation directories via a fsynced JSON pointer replaced atomically on the same filesystem. Populated directories cannot be atomically replaced, and native apply may consume its handle on failure. Cost if wrong: recovery requires choosing an explicitly retained validated generation.
- Ruling: use a threading fleet access lock for all synchronous native fleet reads and publication, plus a separate refresh mutex. FastAPI threaded readers cannot be protected by an asyncio lock alone. Local writes use neither fleet lock. Cost if wrong: fleet lock contention can affect fleet search latency.
- Ruling: bootstrap is identified by committed generation metadata, not an existing empty P01 fleet directory. An empty server snapshot is a valid bootstrap. Cost if wrong: an absent marker redownloads a full snapshot.
- Graphify queried the existing project graph for `QdrantEdgeStore SyncService EdgeRuntime fleet snapshot sync_checkpoints`; the graph covered plan/spec nodes but predates the new adapter interfaces, so current files were read to ground implementation.

## Task 2 — partial refresh

- RED: partial tests failed (4) with missing `refresh` and `fleet_manifest` interfaces before implementation.
- GREEN: bootstrap, partial, real native/server roundtrip, and memory regressions: **29 passed**.
- Additional stale-base regression RED: adapter rejected the not-yet-implemented `expected_generation` keyword. GREEN after atomic manifest/generation capture and expected-base validation before clone/apply.
- Actual Qdrant Server **1.17.1** (cloud-only Docker network) and installed **qdrant-edge-py 0.8.0** full/partial binary compatibility verified, not inferred from route presence. Initial actual fleet full stream `/private/tmp/p06-live-full.snapshot` imported two existing records and reopened them. Dedicated live test seeds A, streams full into native adapter, sends the exact native manifest (no wrapper), adds B/deletes A remotely, streams and stages changed partial, repeats unchanged partial, and reopens the published B generation. Opt-in test: `PATH=/private/tmp/grag-edge-runtime/bin:$PATH DOCKER_HOST=tcp://127.0.0.1:23750 QDRANT_LIVE_DOCKER_CONTAINER=grag-api uv run pytest tests/edge/sync/test_snapshot_live.py -v`.
- Native late-invalid tar apply is exercised on a closed independent clone; previous fleet remains queryable and restart preserves local/fleet state.
- Interrupted streaming removes `.part` files and commits no checkpoint. Publication followed by interrupted SQLite checkpoint is reconciled once from the pointer metadata; deterministic refresh-event identity prevents duplicate completion events.
- Local writes complete during paused network download and while copy holds the fleet access lock. Filesystem/native work is offloaded to a worker thread; cancellation waits that worker before removing the download or allowing resource shutdown.
- Ruling: use an atomic `(manifest, generation)` capture and reject a stale generation before applying a downloaded partial. A separate service mutex serializes network work, while the adapter mutex serializes native publication and close. Cost if wrong: a stale refresh is retried instead of attempting an unsafe incremental base.
- Ruling: retain a validated generation if pointer replacement succeeded but subsequent durability fsync failed, so restart never follows a dangling committed pointer. Previous generations and previous pointer metadata remain available. Cost if wrong: disk space is retained until later retention policy work.

### Additional recovery regressions

- Incomplete committed metadata (valid generation UUID but absent refresh ID/timestamp/kind) was RED (`DID NOT RAISE`), then GREEN after validating all publication fields and closing failed-load handles.
- Losing the current pointer after the first valid publication was RED (restart silently selected the original empty shard), then GREEN after retaining an atomic recovery pointer even for the first publication. Both current/recovery references protect their validated generation from cleanup after a durability error. Stages with neither pointer remain ignored.

## Task 3 — synchronization lifecycle and runtime

- RED: six prepared lifecycle tests failed with the missing `snapshots` constructor interface; runtime wiring failed with missing `EdgeRuntime.snapshots`, and history endpoint failed with HTTP 404. Implementation kept the existing async `SyncService.run_once()` interface and uses the runtime's owned event loop for the async snapshot client.
- After upload acknowledgment, outbox and policy transition together to `SNAPSHOT_PENDING`. Durable acknowledged cohorts are recorded in existing `sync_checkpoints`. Every cohort waits for an active fleet generation/checkpoint pair and matching `memory_id`, `logical_id`, revision, and content hash for every acknowledged entry. Missing/mismatched fleet data, a missing checkpoint, and failed apply remain pending without another upload.
- Cohort state, outbox/policy completion, completed run checkpoint, and the deterministic `SYNC_COMPLETED` event commit in one SQLite transaction. A trigger-injected completion-event failure proved full rollback, then retry proved one eventual completion. Startup recovery preserves completed states; failed refresh resumes the pending cohort.
- Runtime owns one snapshot client and closes it after joining canceled native work. A shutdown failure regression was observed RED (SQLite connection leaked), then GREEN after preserving nested resource cleanup.
- `GET /api/v1/edge/sync/history` exposes durable cohort history. Status/queue include snapshot-pending work and synchronized counts. Existing operation counters were advanced to count `SYNCHRONIZED` as success; the previous uploaded-only count was observed RED (zero after successful sync), then GREEN.
- Ruling: a durable synchronization run is the acknowledged cohort, persisted in `sync_checkpoints` rather than a new table. All entries in that cohort must be present before its single completion event. Failed/unacknowledged uploads retain their independent retry lifecycle. Cost if wrong: UI may need a later display grouping across upload attempts and acknowledged cohorts.

### Real unchanged response correction

The real rebuilt Docker runtime exposed Qdrant **HTTP 304 with no archive body** once its native manifest was exactly unchanged. The initial helper had assumed every successful stream was HTTP 200; it now preserves actual HTTP status. The new regression was RED with `HTTPStatusError: 304`, then GREEN: 304 returns `UNCHANGED`, preserves the active generation/checkpoint, performs no native apply, and emits no duplicate completion for that generation.

### Final gates

- `QDRANT_LIVE_DOCKER_CONTAINER=grag-api uv run pytest tests/edge/sync -q`: **42 passed**, including actual server/native format and full lifecycle gates.
- `QDRANT_LIVE_DOCKER_CONTAINER=grag-api uv run pytest tests/edge -q`: **106 passed**, 25 warnings. Native live tests include a late apply failure on a nonempty server-seeded A generation and confirm A remains retrievable with the unchanged manifest.
- Actual Docker `make baseline-check` with the live gate enabled: **exit 0**, **306 passed, 1 skipped**, exactly **10 imported known failures**, no regression. Output: `/private/tmp/p06-final-baseline-check.log`.
- `docker-compose config -q` and `git diff --check`: passed.
- Rebuilt API image `sha256:41934516e7cb106fb0df0984a1b0ca900df5c33e73e80341d9e8ca3b9149fa06`: actual Docker health `healthy`. The API mounts only its named `/data` volume; no Docker socket. Qdrant has no host port bindings and is only on `grag-cloud-net`.

### Actual Docker API / Ollama embedding smoke

The rebuilt API used real local 768-dimensional Ollama embeddings and actual Qdrant 1.17.1 snapshots. A new learned fact (`f9ff72ee-dc6d-46e7-930a-c3ab27e29dac`) was observed through **QUEUED → SNAPSHOT_PENDING → SYNCHRONIZED**. Run `10d07c97-f7fb-5279-a02e-e554a9d7372c` had exactly one completion event after a repeated manual run. Hybrid search succeeded; fleet count was 4 and synchronized-success count was 4. Actual API restart preserved that record's synchronized state, its durable history, and exactly one completion event. Evidence: `/private/tmp/p06-runtime-smoke.json`.

No P07 local cleanup/deduplication or conflict implementation is included. Earlier fleet generations remain retained for recovery; retention policy is not changed in P06.
