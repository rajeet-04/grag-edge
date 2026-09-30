# P07 Task 2: Conflict detector execution

Date: 2026-09-30

## RED

Before implementation, the requested conflict test module could not be collected because `app.edge.conflicts` did not exist (`ModuleNotFoundError`). This confirms the planned public interface was absent. The focused test file now exercises the missing detector behavior directly.

## GREEN

Command:

```sh
UV_CACHE_DIR=/private/tmp/grag-edge-uv-cache uv run --group dev pytest -q tests/edge/conflicts/test_conflict_detection.py
```

Initial result: **7 passed**. The identity-contract follow-up first failed because JSON had replaced the fleet reference column value. After the schema correction and legacy migration test, final result: **8 passed**.

Coverage includes procedure and learned-fact divergence, append-only observations/incidents, equal content, different logical identities and bases, metadata persistence without content, exactly-once activity emission, restart recovery, and 24 concurrent duplicate detector calls.

## Interface and persistence

- `ConflictService.detect(local, fleet)` returns a persisted `ConflictRecord` only for differing conflict-sensitive sibling revisions with one logical ID and a shared non-null parent revision.
- `list_open()` and `get(conflict_id)` return metadata-only records with revision identities, content hashes, provenance, timestamps, sync states, shared base, and open state.
- A deterministic conflict ID identifies the same divergent revision pair. Conflict insertion and `CONFLICT_DETECTED` event insertion share one SQLite transaction.
- The existing `conflicts` table keeps local and fleet memory ID columns as references and adds `metadata_json` for the metadata snapshot. Existing databases receive the new column with `{}` defaults; no memory text is stored in the control-plane database.

## Scope note

The shared `implementation-ledger.md` had concurrent edits before this task's commit. Those edits are intentionally left unstaged and are not included in this execution record or Task 2 commit.
