#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"
RENDERED_CONFIG_FILE=""
PYTEST_OUTPUT_FILE=""

cleanup() {
  if [[ -n "$PYTEST_OUTPUT_FILE" ]]; then
    rm -f "$PYTEST_OUTPUT_FILE"
  fi
  if [[ -n "$RENDERED_CONFIG_FILE" ]]; then
    rm -f "$RENDERED_CONFIG_FILE"
  fi
}
trap cleanup EXIT

fail() {
  printf 'baseline verification: %s\n' "$1" >&2
  exit "${2:-1}"
}

require_make_targets() {
  local target
  for target in test compose-config baseline-check; do
    if ! make -n "$target" >/dev/null 2>&1; then
      fail "missing Make target '$target'"
    fi
  done
}

require_env_file() {
  if [[ ! -f .env ]]; then
    fail "missing .env; create it with 'cp .env.example .env'"
  fi
}

run_compose_config() {
  require_env_file
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    docker compose config -q
  elif command -v docker-compose >/dev/null 2>&1; then
    docker-compose config -q
  else
    fail "Docker Compose is required (install Docker Compose, then retry)" 127
  fi
  printf 'Compose configuration is valid\n'
}

verify_edge_topology() {
  RENDERED_CONFIG_FILE="$(mktemp)"

  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    docker compose config --format json > "$RENDERED_CONFIG_FILE"
  elif command -v docker-compose >/dev/null 2>&1; then
    docker-compose config --format json > "$RENDERED_CONFIG_FILE"
  else
    fail "Docker Compose is required (install Docker Compose, then retry)" 127
  fi

  python3 - "$RENDERED_CONFIG_FILE" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as rendered_file:
    config = json.load(rendered_file)

network_name = "grag-edge-net"
if network_name not in config.get("networks", {}):
    raise SystemExit(f"baseline verification: rendered Compose is missing network '{network_name}'")

required_services = ("fastapi", "ollama", "neo4j", "open-webui", "ollama-init")
for service_name in required_services:
    service = config.get("services", {}).get(service_name)
    if service is None:
        raise SystemExit(f"baseline verification: rendered Compose is missing service '{service_name}'")
    attached_networks = service.get("networks") or {}
    if isinstance(attached_networks, dict):
        attached_networks = attached_networks.keys()
    if network_name not in attached_networks:
        raise SystemExit(f"baseline verification: service '{service_name}' is not attached to '{network_name}'")
PY

  printf 'Edge network topology is valid\n'
}

run_pytest() {
  uv run pytest -q
}

run_pytest_baseline() {
  PYTEST_OUTPUT_FILE="$(mktemp)"
  local pytest_status=0
  # Always emit every failure/error node ID, without terminal color codes.
  uv run pytest -q -r fE --color=no > "$PYTEST_OUTPUT_FILE" 2>&1 || pytest_status=$?
  cat "$PYTEST_OUTPUT_FILE"
  if [[ "$pytest_status" -eq 0 ]]; then
    printf 'Pytest baseline is fully green\n'
    return 0
  fi
  if [[ "$pytest_status" -ne 1 ]]; then
    fail "pytest did not complete normally (exit $pytest_status)" "$pytest_status"
  fi

  python3 - "$PYTEST_OUTPUT_FILE" docs/superpowers/verification/2026-09-30-grag-edge-p00-known-failures.txt <<'PYTEST_GATE'
from pathlib import Path
import sys

output = Path(sys.argv[1]).read_text(encoding="utf-8")
expected_path = Path(sys.argv[2])
if not expected_path.is_file():
    raise SystemExit(f"baseline verification: missing imported-baseline failure list: {expected_path}")
expected_lines = expected_path.read_text(encoding="utf-8").splitlines()
if not expected_lines or any(not line.strip() or "::" not in line for line in expected_lines) or len(set(expected_lines)) != len(expected_lines):
    raise SystemExit("baseline verification: invalid imported-baseline failure list")
expected = set(expected_lines)
actual = set()
for line in output.splitlines():
    if line.startswith("ERROR "):
        raise SystemExit("baseline verification: pytest reported an error; imported failures cannot accept errors")
    if line.startswith("FAILED "):
        actual.add(line.removeprefix("FAILED ").split(" - ", 1)[0])
if actual != expected:
    print("baseline verification: pytest failure set differs from the imported baseline", file=sys.stderr)
    for node_id in sorted(actual - expected):
        print(f"  added: {node_id}", file=sys.stderr)
    for node_id in sorted(expected - actual):
        print(f"  removed: {node_id}", file=sys.stderr)
    raise SystemExit(1)
print(f"Pytest matches the recorded imported baseline ({len(expected)} known failures); no regression")
PYTEST_GATE
}

case "${1:-all}" in
  all)
    require_make_targets
    run_compose_config
    verify_edge_topology
    run_pytest_baseline
    ;;
  pytest)
    run_pytest
    ;;
  compose)
    run_compose_config
    ;;
  *)
    fail "usage: $0 [all|pytest|compose]" 2
    ;;
esac
