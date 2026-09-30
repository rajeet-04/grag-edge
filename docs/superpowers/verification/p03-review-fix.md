# P03 Boundary A Review Fix

Base under review: `0617c4a`.

## RED reproductions

- The pinned reproduction `.venv/bin/python /private/tmp/grag-edge-boundary-a-repro.py` showed: two concurrent writes for one `memory_id` both succeeding and overwriting; two updates from parent revision 1 both creating revision 2; reuse of a `logical_id` producing a second revision 1; fleet coordinator returning a hit while the API returned no result and GET returned 404; malformed ID, blank query, naive timestamp, and PATCH of a tombstone returning 500; tombstoned semantic top-1 returning no result while top-10 found the live record.
- Added 13 independent native persistence/API cases in `tests/edge/test_p03_review_regressions.py` for duplicate-ID and same-parent races, revise/tombstone races, root identity reuse after deletion, canonical UUID and fleet duplicate IDs, fleet GET/list/search/read-only behavior, tombstone/obsolete top-1 in semantic/keyword/hybrid modes, and each invalid-request response.
- RED command against the pinned `0617c4a` archive: `UV_CACHE_DIR=/private/tmp/grag-edge-uv-cache /private/tmp/grag-edge-p00-baseline/.venv/bin/python -m pytest tests/edge/test_p03_review_regressions.py -q --tb=short` — 13 failed. Independent failures observed included duplicate create count 2; history `[1,2,2]`; second root accepted after tombstone; duplicate fleet ID returned 201; fleet GET returned 404; all three top-1 modes returned no result; malformed ID returned 500; whitespace search returned 500; naive timestamp returned 500; tombstone PATCH raised `KeyError`/500.

## Fixes and rulings

- Serialize create, revise, and tombstone transitions with a per-`MemoryService` async lock. The app owns one runtime/service per lifespan. Writes now re-check persistent state after taking the lock; all roots, including tombstoned roots, reserve their logical identity.
- Parse client IDs as UUID values and persist their lowercase canonical representation. Duplicate memory IDs are checked against both local and fleet shards.
- Expose read-only fleet retrieval/listing through the adapter. Memory inspection and list include fleet data; revise of a fleet-only or tombstoned record returns HTTP 409.
- Filter immutable revisions and tombstones inside `HybridSearchService` before rank fusion and final top-k. Candidate retrieval expands to the persisted shard point count so stale vectors cannot consume the requested result window.
- Convert invalid memory IDs to 404, whitespace search and timezone-naive time filters to 422.
- Ruling: writes are serialized within the one runtime's `MemoryService` instance — reason: FastAPI lifespan creates one runtime and the native race tests exercise concurrent calls through that owner — cost if wrong: separate processes or independently constructed services over the same shard would require a cross-process transaction/lock.
- Ruling: search visibility scans local and fleet persisted points and expands candidate depth to the point count — reason: immutable obsolete vectors cannot be modified and must not starve live matches — cost if wrong: each search currently incurs an O(local + fleet points) scan and broad candidate query.

## GREEN evidence

- `UV_CACHE_DIR=/private/tmp/grag-edge-uv-cache uv run pytest tests/edge/memory tests/edge/api tests/edge/test_runtime.py tests/edge/test_p03_review_regressions.py -q` — 33 passed.
- Native regressions reopen Qdrant Edge shards via the application adapter and exercise actual `app.main` lifespan with the persistent local/fleet shard paths.
- `UV_CACHE_DIR=/private/tmp/grag-edge-uv-cache make baseline-check` — exit 0; compose and edge topology checks passed; 233 passed, 1 skipped, the same 10 imported baseline failures as P02; verifier reported no regression.
- `git diff --check` — passed.
