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
- P04: PASS (`89cd809..1b8b74a`); root actual edge gate 55/55 and baseline-check exit 0 (255 passed, 1 skipped, exact 10 imported failures).
- P05: IN PROGRESS.
- P06–P12: NOT STARTED.

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
