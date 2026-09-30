# P0 baseline verification

Date: 2026-09-30
Branch: `codex/grag-edge-p00-baseline`

## Environment

- Python 3.12.14 with pytest and pytest-asyncio installed through the project dev group.
- Docker CLI/daemon and NVIDIA runtime are unavailable in this environment.
- Standalone `docker-compose` v5.5.1 is available and validates configuration without starting services.

## TDD and verification results

- Task 1 RED: `bash scripts/dev/verify_baseline.sh` failed because Make target `test` was absent.
- Missing-env check: `make compose-config` failed with the documented instruction to create `.env` from `.env.example`.
- Task 1 verification: Compose configuration passed. The full pytest run reported 10 failed, 200 passed, 1 skipped, and 20 warnings.
- Base control: the same full pytest suite on original commit `202b372` reported the same 10 failures, 200 passes, 1 explicit service-dependent skip, and 20 warnings. The P0 changes did not introduce these failures.
- Task 2 RED: the topology assertion failed because `grag-edge-net` was absent.
- Task 2 verification: rendered Compose configuration and the `grag-edge-net` membership assertion passed. The full pytest run again reported the same 10 failures, 200 passes, 1 skipped, and 20 warnings.
- The verifier ran all tests without filters. The existing health-check skip requires Neo4j/Ollama services.
- `uv lock --check`, `bash -n scripts/dev/verify_baseline.sh`, `git diff --check`, and Compose service/network inspection passed.
- `make baseline-check` is still red due to the 10 pre-existing failures. The P0 exit gate is not satisfied. Container startup and GPU behavior remain unverified because Docker and NVIDIA are unavailable.

## Scope and spec notes

- The binding spec requires the local demo to work without external SaaS credentials. Current legacy query and entity/relation extraction code still selects Ollama Cloud. P0 preserves imported application behavior and does not implement local inference routing; the README and `.env.example` identify this as an unresolved spec-conformance issue.
- `ollama-init` is attached to `grag-edge-net` because it calls `http://ollama:11434` and must share the service network.
- The plan's Task 2 expected full `make baseline-check` pass conflicts with the verified pre-existing test failures and its Task 1 allowance to document them. This report preserves the failure evidence; the phase gate remains red rather than being weakened.
