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
- P05: PASS (`f4ddc65..363e803`); root edge 72/72 and baseline-check exit 0 (272 passed, 1 skipped, exact 10). Actual Docker disconnected/reconnected cloud bridge; offline local embedding-backed create/revise/hybrid, restricted exclusion, cloudless startup and idempotent remote upsert verified.
- P06: IN PROGRESS.
- P07–P12: NOT STARTED.

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
