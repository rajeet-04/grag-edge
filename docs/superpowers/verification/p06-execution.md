# P06 execution evidence

## Task 1 — full bootstrap

- RED: `uv run pytest tests/edge/sync/test_snapshot_bootstrap.py -q` failed collection with `ModuleNotFoundError: app.edge.sync.snapshot` before implementation.
- GREEN: focused bootstrap plus memory regression suite: **19 passed**.
- Ruling: publish independent generation directories via a fsynced JSON pointer replaced atomically on the same filesystem. Populated directories cannot be atomically replaced, and native apply may consume its handle on failure. Cost if wrong: recovery requires choosing an explicitly retained validated generation.
- Ruling: use a threading fleet access lock for all synchronous native fleet reads and publication, plus a separate refresh mutex. FastAPI threaded readers cannot be protected by an asyncio lock alone. Local writes use neither fleet lock. Cost if wrong: fleet lock contention can affect fleet search latency.
- Ruling: bootstrap is identified by committed generation metadata, not an existing empty P01 fleet directory. An empty server snapshot is a valid bootstrap. Cost if wrong: an absent marker redownloads a full snapshot.
- Graphify queried the existing project graph for `QdrantEdgeStore SyncService EdgeRuntime fleet snapshot sync_checkpoints`; the graph covered plan/spec nodes but predates the new adapter interfaces, so current files were read to ground implementation.
