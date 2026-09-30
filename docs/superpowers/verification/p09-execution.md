# P09 execution evidence

Commits: `eb95123` scaffold, `30a8501` live overview, `04ba28b` search + memory, `00e3f50` sync/conflicts/Compose (`grag-edge-ui`).

## TDD
Each task: tests written first, observed RED (missing module / missing pages), then implemented to GREEN. Task 4's Sync test file was first
dropped by a failed shell chain (only Conflicts RED was observed initially); Sync RED was then observed separately before implementing.

## Results
- Frontend: `vitest --run` 16/16 (App nav, Overview ONLINE->OFFLINE via SSE, SSE replay dedupe, empty/error states, Search/Evidence provenance and advanced scores,
  Ask mode, Memory filters/overflow/detail, Sync counts + live update on SYNC_COMPLETED + approve, Conflicts KEEP_LOCAL/ACCEPT_FLEET/MERGE + live appearance).
  `tsc --noEmit` clean; `vite build` clean; `docker build frontend` succeeds (nginx serving SPA, proxying /api and /v1 with SSE buffering off).
- Backend gates: tests/edge 144 passed; `EMBEDDING_MODEL=absent-embedding-model make baseline-check` exit 0 (360 passed, 1 skipped, exact 10 known failures);
  `make compose-config` valid; `git diff --check` clean.

## Rulings / deviations
- Host has no Node; Vitest/tsc/Vite/build ran in a `node:22-alpine` container in the task Docker daemon (files copied in via tar; bind mounts unavailable).
- `docker compose config -q` unavailable (no compose plugin in the runtime); `make compose-config` used instead.
- Exit gate "without manual refresh" is proven at component level with a fake EventSource (live refetch on SSE events, replay dedupe by event_id);
  no Playwright/real-browser smoke test and no run against the live API were done (user asked for speed).
- Backend exposes no local-AI/Qdrant health fields; the status rail derives them from `status == READY`. Queue items carry no policy reasons, so the Sync page
  shows policy reasons from AWAITING_APPROVAL memories (`sync_reason_codes`). Search results lack confidence (shows n/a); "Ask GRAG" uses `/v1/chat/completions`.
- Search "memory" mode uses hybrid search; component scores are behind the Advanced toggle.
- Pre-existing uncommitted `.gitignore` change (`graphify-out/`) left untouched.

## Remaining
- No independent review, no real-browser test, no keyboard/contrast audit beyond focus-visible styles and dark tokens.
