# P12 Execution Evidence

Commits: `439c9cd` privacy and restart recovery tests, `7038682` observability gaps and performance targets, `c0d8f06` submission documentation. Verified product commit: `c0d8f06` (the verification commit only adds docs).

## Results (actual)
- Task 1: tests/e2e/test_privacy_boundary.py (5) and test_restart_recovery.py (4) passed on first run against the real native Edge store. No product defect was found, so these are characterization tests without an observed RED (rule: no fix without a revealed defect). Covered: local_only/restricted (auto and approval_required, explicit approve) had zero upload calls across repeated runs; only fleet-safe memory uploaded alongside blocked neighbours; privacy downgrade after queueing blocked upload; offline restart, interrupted UPLOADING restart, restart after upload before fleet refresh (no re-upload, not SYNCHRONIZED), unresolved conflict restart.
- Task 2: RED observed (3 of 4 failed) for missing `last_fleet_refresh`, `origin_counts` and `search_latency_ms` (always null). Fixed in `app/edge/api/operations.py`, `memories.py`, `runtime.py` (plus optional TypeScript fields). Latency targets already met on a 60-memory deterministic dataset: search p95 < 250 ms, write p95 < 300 ms, status < 100 ms (test asserts; live demo search 12 ms). Events endpoint already persisted (existing tests). Dashboard <2 s connectivity update is not automated here (verified only by the P10 demo transitions).
- Task 3: README/SETUP rewritten, ARCHITECTURE, DEMO_RUNBOOK, PS3_REQUIREMENTS_TRACEABILITY added, stale ChromaDB text removed from flow_diagram.md and code comments, stale Windows path removed from OPENWEBUI doc. Doc links checked programmatically; Make targets referenced all exist.
- Task 4 gate: tests/edge+demo+e2e+performance 202 passed (live Docker); frontend vitest 16/16, `tsc --noEmit` + `vite build` clean; `make compose-config` valid; `git diff --check` clean; `EMBEDDING_MODEL=absent-embedding-model make baseline-check` exit 0 (400 passed, 1 skipped, exact 10 imported failures); `make demo-acceptance` PASSED twice from reset (real network cut, fleet=7, queue 0, SYNCHRONIZED); `make demo-robot-b` PASSED (FLEET origin ROBOT-01).
- Secret scan: tracked files scanned for key/token/private-key patterns: none. `.env` is untracked; `.env.example` holds only blank keys and the dev sample Neo4j password. No log statements interpolate keys.

## Rulings
- Search latency in stats is measured in the API search handler (last and p95 over 200 samples), not in the store.
- Task 1 tests use fake cloud without snapshot service (UPLOADED boundary); live snapshot recovery remains covered by P05/P06 native tests.
- No independent P12 review was run (user-directed fast finish). Clean-checkout validation was not repeated in a fresh clone; commands were run from this worktree with the Docker runtime and Ollama models already present.

## Deferred items (P07-P11) and known issues
- P07: M6, M7, N3, N4, N7 (stale 3-device conflicts remain open), N8 (fleet resolves_memory_ids trusted); losing device does not adopt a peer resolution (blocked with 409); Task 3 tests written after implementation; no fourth independent review.
- P08: hybrid search returns zero-relevance dense hits when memory is non-empty (no relevance threshold); query-agent failure routes to the error handler even if edge hits exist; ranker docstrings partly legacy; no independent review.
- P09: no Playwright/real-browser test, no keyboard/contrast audit beyond focus-visible and dark tokens; no independent review.
- P10: seed fleet points are dense-only (no BM25 sparse vector); API reached via docker exec because host port 8000 is unreachable in this runtime; TDD partially retroactive for scripts; no independent review.
- P11: Robot B restart preserving its own fleet checkpoint not separately tested; no independent review.
- Baseline: 10 imported GRAG AI failures remain unfixed by instruction; `test_handle_entity_pair` needs `EMBEDDING_MODEL=absent-embedding-model` to stay in the recorded set.
- No push, PR, or publication was performed.
