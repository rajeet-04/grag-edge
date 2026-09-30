# P11 Execution Evidence

Commits: `cc2cefe` optional Robot B runtime, then `feat: demonstrate robot-to-fleet knowledge transfer` (scenario + `make demo-robot-b`).

## Results
- `make demo-robot-b` run twice from reset on the live Compose stack: PASS both times. A cut from the cloud network (real `docker network disconnect`), memory written offline on A with device ROBOT-01, B search asserted empty, A reconnected and synced to SYNCHRONIZED, B sync/refresh run, B search returns the same memory_id with origin FLEET and device_id ROBOT-01.
- `make demo-acceptance` still passes after P11 (run post-change); tests/demo 27, tests/edge 144, baseline-check exit 0 (387 passed, 1 skipped, exact 10 imported failures), `make compose-config` valid, `git diff --check` clean. Frontend untouched.
- Default compose (no profile) excludes `robot-b-api`; `--profile fleet-demo` includes it (tested via docker-compose config --services).

## Notes
- Robot B: service `robot-b-api`, container `grag-robot-b-api`, `DEVICE_ID=ROBOT-02`, host port 8002, own `robot_b_data` volume (shard + SQLite); shares only qdrant-server with A.
- Scenario uses public Edge APIs only via `docker exec curl` (host cannot reach published ports in this runtime). `robot_b.sh` also removes Robot B and its volume on reset (reset.sh left unchanged).
- Not separately tested: restarting B preserving its own fleet checkpoint (relies on P5/P6 checkpoint behaviour with B's separate SQLite volume); no independent review.
- Unrelated `.gitignore` graphify-out edit in worktree left uncommitted/untouched.
