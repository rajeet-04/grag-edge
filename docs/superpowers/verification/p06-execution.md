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
