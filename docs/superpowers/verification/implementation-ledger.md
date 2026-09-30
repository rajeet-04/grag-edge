# GRAG Edge implementation ledger

Worktree: `/private/tmp/grag-edge-p00-baseline`
Branch: `codex/grag-edge-p00-baseline`
Starting HEAD: `45fae76`
Binding spec: `docs/superpowers/specs/2026-09-30-grag-edge-design.md`
Roadmap: `docs/superpowers/plans/2026-09-30-grag-edge-implementation-index.md`

## Execution contract

P01–P10 and P12 are mandatory; P11 is attempted only after P10 core acceptance. Each implementation task requires observed RED, GREEN, relevant regressions, and its planned commit. Root integrates interfaces and runs phase gates; fresh reviews occur after P03, P07, P08, P10, and P12. No push, merge, publication, or PR is authorized.

P00 is complete at `45fae76`; its regression gate accepts full green or exactly the recorded imported failure set. Later intentional legacy migrations must explain fixed/removed baseline failures and retain strict regression checking.

## Status

- P00: PASS (prior verified make baseline-check exit 0).
- P01: PASS (`7ef0217..213b766`); root gate `uv run pytest tests/edge/memory -v`: 6/6; real native reopen persistence verified.
- P02: PASS (`f5e10a4..964e306`); root planned retrieval gate 7/7, all memory tests 13/13.
- P03: PASS (`0cc767c..26166e3`); root native edge gate 33/33; root baseline-check exit 0 (233 passed, 1 skipped, exact 10 imported failures). Independent boundary A re-review at 26166e3 passed all five Important fixes, native 768-dimensional persistence and fleet immutability.
- P04: PASS (`89cd809..8366e95`); native recovery fix independently reviewed PASS. Root isolated fix gate 58 edge tests, baseline-check exit 0 (258 passed, 1 skipped, exact 10 imported failures).
- P05: PASS (`f4ddc65..6b169e8`, evidence020d997); realDockeroffline/reconnect verified; atomic worker/privacy/shutdown/attempt-history fixes independently reviewed PASS. Root actual current edge93passed1skip; baselineexit0(293passed2skip exact10).
- P06: PASS (`181209b..231a1d6`, interleaved prerequisite fixes); root actual sync gate42/42 including live Docker/native full+partial tests; baseline306passed1skip exact10 exit0. Actual API synchronized acknowledged memory and preserved one completion across restart.
- P07: COMPLETE (user-directed fast finish) at `53e9f1f` — tests/edge 144 passed (live), baseline-check exact 10 known failures, compose-config and diff-check clean. Boundary-B reviews 1-2 findings fixed; review 3 found N6, fixed in `53e9f1f` with a retained test; NO fourth independent review was run (user asked to finish fast). Deferred: M6, M7, N3, N4, N7 (stale 3-device conflicts stay open), N8 (fleet resolves_memory_ids trusted), and adoption of a peer resolution by the losing device (it is blocked from revise/delete with 409 instead). Task 3 tests were written after implementation (TDD deviation). See p07-execution.md.
- P08: COMPLETE (user-directed fast finish) at `6a02061` (`8614dc2`, `513d959`, `6a02061`) — tests/edge 144 passed, baseline-check exit 0 (360 passed, 1 skipped, exact 10 imported failures, known-failures file unchanged), compose-config and diff-check clean; offline streaming/non-streaming acceptance passes with Qdrant Server/Neo4j down and cloud unset; ChromaDB fully removed. No independent P08 review was run. See p08-execution.md.
- P09: COMPLETE (user-directed fast finish) at `00e3f50` (`eb95123`, `30a8501`, `04ba28b`, `00e3f50`) — frontend vitest 16/16, `tsc --noEmit` and `vite build` clean, frontend Docker image builds; tests/edge 144 passed, baseline-check exit 0 (360 passed, 1 skipped, exact 10 imported failures), compose-config and diff-check clean. No Playwright browser smoke test and no independent review. See p09-execution.md.
- P10: COMPLETE (user-directed fast finish) at `8a0ce30` (`83cab2d`, `402e9aa`, `8a0ce30`) — make demo-acceptance passed twice from reset with real Docker network cut; tests/demo 20, tests/edge 144, baseline-check exit 0 (380 passed, 1 skipped, exact 10 imported failures), compose-config and diff-check clean. See p10-execution.md.
- P11–P12: NOT STARTED.

## Rulings

Ruling: The subagent skill proposes fresh implementer/reviewer for each task → use the user's phase-scoped agents, reuse/resume strategy and five subsystem review boundaries → explicit model/token policy overrides the skill's default dispatch cadence → cost/risk if wrong: delayed detection of an intra-phase defect; mandatory TDD and phase gates remain enforced.

Ruling: The implementation worktree predates upstream plan corrections `81e2320`/`5e91677` → apply only the corrected P00/P08 document contents from origin/main without a merge → the authoritative regression gate and credential-free migration contract must remain visible to phase agents → cost/risk if wrong: documentation divergence; no application behavior changed.

Deviation: P03 Task2 API prototype preceded its initial RED run. The agent saved/removed that draft, observed the missing-runtime RED, and restored it before GREEN. This is recorded explicitly in p03-execution.md; boundary A independently checks requirement coverage. It cannot be represented as strict initial-draft TDD.

Runtime evidence: actual Docker Engine29.8.1 is isolated in task-owned DinD inside the existing Linux VM, with no host secret mounts and loopback-only API/service forwards. Actual Docker Compose bridge disconnect/reconnect and host-build-context smoke tests passed. Normal project artifacts will remain standard Docker Compose.

Boundary A at0617c4a: concurrency permits immutable overwrite/duplicate revision; logical identity can restart revision1; fleet API visibility missing; post-top-k lifecycle filtering starves live matches; native API invalid/state inputs yield500. Reviewer reproduction /private/tmp/grag-edge-boundary-a-repro.py proved all with real Qdrant/API. Initial unit gate passing is not sufficient; advancement held pending retained tests, fixes, and independent re-review.

Ruling: Persisted default LOCAL_ONLY cannot distinguish explicit operator intent from an omitted policy → add nullable requested operator policy separately from effective decision → spec requires explicit local_only precedence while incident/learned-fact auto rules remain reachable → risk if wrong: unintended upload eligibility; privacy/explicit-policy tests and upload-boundary rechecks are mandatory.

Ruling: Qdrant Edge and SQLite cannot participate in one atomic transaction → immutable Qdrant revision flushes LOCAL_DIRTY first; SQLite transaction owns effective policy/state, outbox and idempotent activity; reads overlay committed control metadata and startup reconciles missing control rows → searchable content stays in Edge and QUEUED is never published without durable work → risk if wrong: crash-gap orphan or misleading state; injected commit failures and restart reconciliation tests required.

Runtime preflight: root verified actual Docker Engine29.8.1 Linuxaarch64 overlay2 and real nomic-embed-text 768-dimensional response. Runtime agent verified real CPU qwen3.5:0.8b chat, Qdrant1.17.1 internal HTTP200 and final Engine network disconnect/reconnect. Task-local runtime details: /private/tmp/grag-edge-runtime/README.md.

P06 API preparation: /private/tmp/grag-edge-p06-api-notes.md records verified native0.8 snapshot signatures, server singular full/partial binary endpoints, staging requirements and atomic generation publication. Live server/Edge format compatibility remains P06 gate.

P04 review finding: SQLite root commit failure followed by a successful revision leaves a missing ancestor control row; restart reconciliation rejects backfilling the root and fails startup. Dedicated fix pass owns service/workflow and retained native reproduction. P05 independent server/connectivity work may continue, but its gate is held.

P04 recovery fix8366e95 (isolatedbbb3fac): missing root/intermediate operational rows reconcile in revision order as SUPERSEDED without scheduling old work; latest revision queues once; existing terminal upload preserved. Reviewer original native reproduction and 25 targeted tests passed. Shared in-progress P05 suite was expected RED on missing SyncService; clean P04 fix checkout was used for its full regression gate.

P05 runtime configuration finding: an explicitly blank Qdrant service API key enabled authentication unexpectedly → omit unset server-key configuration for credential-free demo, retain optional client key → real HTTP401 classification remained ERROR and correcting config restored ONLINE → risk: secure deployment must explicitly configure matching keys.

P05 also fixed the deferred minor PATCH SQLite error mapping to503 with a retained test. P06 owns only subsequent snapshot confirmation and synchronization completion; UPLOADED alone is not synchronized.

P05 review blockers at363e803: pre-send privacy denial cannot cancel UPLOADING; split claim/control-state transactions can strand work; successful attempts missing history; shutdown closes DB/transport while an owned health thread remains active. Dedicated retained RED/GREEN fix pass owns worker/outbox/runtime; P06 independent adapter work may continue.

P06 Task1 at181209b: real Qdrant1.17.1 full shard snapshot imported/reopened by Edge0.8.0 with two fleet points; root bootstrap3/3 passed.

Ruling: os.replace cannot atomically replace an existing nonempty fleet directory → stage immutable generation directories and atomically publish a small current-generation pointer under fleet-only locks → required rollback and restart safety are preserved without a two-rename crash gap → risk if wrong: stale generation/checkpoint; native restart/failure/partial tests required.

P05 bf08e33 scoped native re-review: atomic claim/rollback, pre-send cancellation, effective payload projection and shutdown joins passed (19 targeted tests). Remaining Important: attempt rows lack persisted end time and outcome required by spec section12; success/cancel/active indistinguishable. Separate schema/transition repair underway before P06 integration.

P06 Task2 at50e6059: bootstrap/partial/native suite29passed, actual Docker full→changed partial→deleted point→unchanged partial→reopen gate root1passed1.92s. Generation base capture prevents applying a stale downloaded delta, staged apply preserves active shard, cancellation joins native worker, local writes remain available. P06 Task3 held pending P05 review clearance.

P05 bd1d5b5 adds atomic attempt start/end/outcomes; fresh native transition checks and17targeted tests pass. Root active suite93passed1skip, baselineexit0(293passed2skip exact10). Remaining migration finding: legacy timestamps/outcomes were inferred without evidence.

Ruling: legacy attempt rows lack sufficient historical timing/outcome evidence → preserve original created_at and mark legacy outcome UNKNOWN with missing timestamps left NULL; only newly observed attempts must have complete lifecycle fields → fabricated history would undermine inspection/recovery evidence → risk: older history has explicit gaps, UI/history must handle unknowns without scheduling uploads again.

P06 recovery fixaa8efbf rejects incomplete publication metadata and retains first-publication recovery pointer; native recovery tests observedREDthenGREEN.

P05 final scoped clearance6b169e8: native old-bf08 migration retains genuine created_at/error, start/end NULL and LEGACY_UNKNOWN without queue resets. New FAILED→SUCCESS/CANCELLED/INTERRUPTED records persist real timings/outcomes across reopen. All reviewed Important/Critical resolved; P06 Task3 hold released.

Ruling: real Qdrant1.17.1 may return HTTP304 with no body for unchanged native manifest → treat as harmless UNCHANGED and retain generation/checkpoint/completion identity, do not apply an empty archive → spec requires no-change refresh idempotence → risk: stale unobserved remote mutation; exactmanifest server semantics/live changed+unchanged tests verify boundary.

User steering: gitignoredworktree.env now selects localgemma4:12b-mlx and optionalcloudnemotron-3-nano:30b-cloud. MacOllama0.35 supportsMLX, exacttagsverified, authorizedlocalmodeldownloads inprogress; DockerAPIhostroute verified. Requiredofflinepathsremainlocal. RemainingphaseagentsLuna peruserrequest.

User stop scope: complete current P07, run its hard gate and required boundaryBreview, then stop. Do not start P08 or later phases. Authorized Ollama model pull remains running independently.

Ruling: local-only/restricted tombstone must not upload blocked content or vectors, but explicit deletion must withdraw previously shared revisions → queue durable ID-only retractions for same-logical revisions with acknowledged or possibly accepted upload attempts, use idempotent server point deletes, refresh fleet and confirm absence before completion; archive own history locally → deletion tombstone semantics and privacy are both preserved → risk if wrong: operator intended local-only to prohibit withdrawal of previously shared content; retaining deleted data remotely would violate deletion/privacy intent.
