#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"
RENDERED_CONFIG_FILE=""

cleanup() {
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

case "${1:-all}" in
  all)
    require_make_targets
    run_compose_config
    verify_edge_topology
    run_pytest
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
