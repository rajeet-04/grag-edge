# P01 Execution Record

Base: P00 commit `45fae76` on `codex/grag-edge-p00-baseline`.

## Task 1: storage contract

- RED: `UV_CACHE_DIR=/private/tmp/grag-edge-uv-cache uv run pytest tests/edge/memory/test_store_contract.py -v` failed collection with `ModuleNotFoundError: app.edge.memory.store` before implementation.
- GREEN: same command passed, 3 tests, after adding the application-owned `StoredPoint` and `EdgeMemoryStore`, configuration, and dependency.
- Dependency: `uv add qdrant-edge-py` resolved `qdrant-edge-py==0.8.0`; exact resolution is in `uv.lock`.
- Commit: `7ef0217 feat: define edge memory storage contract`.

## Task 2: Qdrant Edge adapter

- API verification: inspected the installed 0.8.0 type stub and exercised the published native wheel on Darwin ARM. The usable API is `EdgeShard.create/load`, `EdgeConfig` with named vectors, `UpdateOperation.upsert_points`, `retrieve`, `flush`, and `close`. The wheel also offers local `Bm25` helpers. IDs must parse as UUIDs.
- RED: `UV_CACHE_DIR=/private/tmp/grag-edge-uv-cache uv run pytest tests/edge/memory/test_qdrant_store.py -v` failed collection with `ModuleNotFoundError: app.edge.memory.qdrant_store` before implementation.
- Initial GREEN attempt found Qdrant requires the target shard directory to exist before `EdgeShard.create`; after that fix, reopen verification found cosine distance normalizes dense vectors. Final fixture uses a unit-length vector so it tests persisted values exactly.
- GREEN: `UV_CACHE_DIR=/private/tmp/grag-edge-uv-cache uv run pytest tests/edge/memory -v` passed, 6 tests, covering persistence after close/reopen, sparse vector + payload persistence, dimension rejection before mutation, and actionable empty-shard error.

## Rulings

- Ruling: `.env.example` is the environment template to update, per P01 handoff; the plan's `env.example` filename is stale — reason: the repository contains `.env.example` and no `env.example` — cost if wrong: expected setup documentation would be absent from the actual template.
- Ruling: IDs are validated as UUID strings at the adapter boundary — reason: Qdrant Edge 0.8.0 rejects arbitrary string IDs — cost if wrong: callers with another intended identifier format need a deterministic ID mapping.
- Ruling: sparse values are passed through as Qdrant sparse vectors or `{indices, values}` mappings — reason: P01's `StoredPoint.sparse` is backend-neutral `Any | None` and the local BM25 embedding can be performed before storage — cost if wrong: a later memory service may need a small text-to-BM25 conversion helper.
- Ruling: existing empty directories return an actionable error, while absent directories are created — reason: an empty existing shard can be an interrupted/corrupt deployment and must not be mistaken for new data — cost if wrong: first-time setup must configure a path that does not already exist.

## Platform

- qdrant-edge-py 0.8.0 native wheel and actual close/load persistence were verified on Darwin ARM.
- Linux x86_64 and ARM64 wheels are published per PyPI artifact metadata, but a Linux container smoke test was not run in this checkout because Podman has no active machine; the adapter integration tests ran against the real native library on Darwin.

## Regression gate

- `make baseline-check` first encountered the restricted default uv cache at `/Users/rajeet/.cache/uv`; rerun with the mandated writable cache: `UV_CACHE_DIR=/private/tmp/grag-edge-uv-cache make baseline-check`.
- Compose configuration and edge network topology checks passed. The recorded repository baseline was reproduced: 206 passed, 1 skipped, 10 known failures, followed by `Pytest matches the recorded imported baseline (10 known failures); no regression`.
- `git diff --check` passed. Source scan confirms only `app/edge/memory/qdrant_store.py` imports the `qdrant_edge` module.
