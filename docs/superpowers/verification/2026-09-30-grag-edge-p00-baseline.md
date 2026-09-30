# P0 baseline verification

Date: 2026-09-30
Branch: `codex/grag-edge-p00-baseline`

## Environment

- Python 3.12.14 with pytest and pytest-asyncio installed through the project dev group.
- Docker CLI/daemon and NVIDIA runtime are unavailable in this environment.
- Standalone `docker-compose` v5.5.1 is available and validates configuration without starting services.

## Initial TDD and verification results (before gate correction)

- Task 1 RED: `bash scripts/dev/verify_baseline.sh` failed because Make target `test` was absent.
- Missing-env check: `make compose-config` failed with the documented instruction to create `.env` from `.env.example`.
- Task 1 verification: Compose configuration passed. The full pytest run reported 10 failed, 200 passed, 1 skipped, and 20 warnings.
- Base control: the same full pytest suite on original commit `202b372` reported the same 10 failures, 200 passes, 1 explicit service-dependent skip, and 20 warnings. The P0 changes did not introduce these failures.
- Task 2 RED: the topology assertion failed because `grag-edge-net` was absent.
- Task 2 verification: rendered Compose configuration and the `grag-edge-net` membership assertion passed. The full pytest run again reported the same 10 failures, 200 passes, 1 skipped, and 20 warnings.
- The 10 failing test IDs are:
  - `tests/agents/test_explanation_agent.py::TestReasoningStepsWithConfidence::test_more_steps_than_paths`
  - `tests/agents/test_explanation_agent.py::TestReasoningStepsWithConfidence::test_empty_paths`
  - `tests/integration/test_ollama_client.py::TestOllamaClient::test_client_initialization_cloud`
  - `tests/services/test_entity_resolution.py::TestValidationService::test_validation_accuracy_calculation`
  - `tests/services/test_entity_resolution.py::TestValidationService::test_validation_precision_recall_f1`
  - `tests/services/test_entity_resolution.py::TestValidationService::test_threshold_analysis`
  - `tests/services/test_entity_resolution.py::TestEdgeCases::test_paris_city_vs_company`
  - `tests/services/test_similarity_service.py::TestSimilarityService::test_compute_similarity_weights`
  - `tests/services/test_similarity_service.py::TestSimilarityService::test_compute_similarity_fallback_to_names`
  - `tests/services/test_similarity_service.py::TestSimilarityService::test_handle_entity_pair`
- The verifier ran all tests without filters. The existing health-check skip requires Neo4j/Ollama services.
- `uv lock --check`, `bash -n scripts/dev/verify_baseline.sh`, `git diff --check`, and Compose service/network inspection passed.
- `make baseline-check` is still red due to the 10 pre-existing failures. The P0 exit gate is not satisfied. Container startup and GPU behavior remain unverified because Docker and NVIDIA are unavailable.

## Scope and spec notes

- The binding spec requires the local demo to work without external SaaS credentials. Current legacy query and entity/relation extraction code still selects Ollama Cloud. P0 preserves imported application behavior and does not implement local inference routing; the README and `.env.example` identify this as an unresolved spec-conformance issue.
- `ollama-init` is attached to `grag-edge-net` because it calls `http://ollama:11434` and must share the service network.
- The plan's Task 2 expected full `make baseline-check` pass conflicts with the verified pre-existing test failures and its Task 1 allowance to document them. This report preserves the failure evidence; the phase gate remains red rather than being weakened.

## Corrected P00 regression gate

The upstream P00 plan correction in `81e2320` and the user's resumed instructions supersede the earlier red gate status above. P00 accepts a fully green pytest suite or the exact imported failure set recorded in `2026-09-30-grag-edge-p00-known-failures.txt`. This does not repair or skip the imported failures. Local inference routing is explicitly assigned to P08 by upstream commit `5e91677` and remains outside this P00 change.

- Reconfirmed the control suite from original commit `202b372`: the same 10 failed node IDs, 200 passed, 1 skipped, and 20 warnings. The machine-readable list is derived from that control output.
- RED: the previous `make baseline-check` returned exit 2 with the exact imported failure set.
- GREEN: updated `make baseline-check` returned exit 0. Compose configuration and topology passed; pytest reported 10 failed, 200 passed, 1 skipped, and 20 warnings, followed by `Pytest matches the recorded imported baseline (10 known failures); no regression`.
- Deterministic command-shim checks passed for green pytest, exact failures in a different order, added/removed/changed failures, collection/command errors, unparseable failure output, Compose failure, topology failure, and fixture errors alongside the known failures. Strict pytest mode still returns nonzero for failing tests.
- `bash -n scripts/dev/verify_baseline.sh` and `git diff --check` passed.
- The corrected P00 exit gate is satisfied. Container startup/GPU validation remains unavailable in this environment, as recorded above. No P01 implementation, push, or merge was performed.
