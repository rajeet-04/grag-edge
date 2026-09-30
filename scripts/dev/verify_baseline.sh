#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

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

run_pytest() {
  uv run pytest -q
}

case "${1:-all}" in
  all)
    require_make_targets
    run_compose_config
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
