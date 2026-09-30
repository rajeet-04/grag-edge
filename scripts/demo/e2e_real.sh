#!/usr/bin/env bash
# Real-stack browser e2e: the built console served by nginx (grag-edge-ui) proxying the real
# Edge API of the live Compose stack, driven by Playwright/Chromium in a runner container that
# shares the edge network. The runner gets the Docker socket (it is a test tool, never an app
# container) so the test can execute the real scripts/demo/offline.sh and online.sh.
#   E2E_SKIP_PREPARE=1  reuse the running stack instead of reset + start + conflict seed
#   E2E_RUNNER          runner container name (default grag-edge-e2e-runner, reused across runs)
source "$(dirname -- "${BASH_SOURCE[0]}")/lib.sh"
RUNNER="${E2E_RUNNER:-grag-edge-e2e-runner}"
project="${COMPOSE_PROJECT_NAME:-$(basename "$DEMO_ROOT" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9_-')}"

if [[ -z "${E2E_SKIP_PREPARE:-}" ]]; then
  bash scripts/demo/reset.sh
  bash scripts/demo/start.sh
fi
compose up -d --build grag-edge-ui >/dev/null
[[ -n "${E2E_SKIP_PREPARE:-}" ]] || bash scripts/demo/conflict.sh

if ! docker inspect "$RUNNER" >/dev/null 2>&1; then
  docker run -d --name "$RUNNER" --network grag-edge-net -v /var/run/docker.sock:/var/run/docker.sock \
    node:22-alpine sleep infinity >/dev/null
  docker exec "$RUNNER" apk add --no-cache chromium bash curl python3 docker-cli docker-cli-compose >/dev/null
fi
docker start "$RUNNER" >/dev/null
docker exec "$RUNNER" sh -c 'rm -rf /repo/scripts /repo/docker-compose.yml /repo/demo; mkdir -p /repo /app/frontend'
COPYFILE_DISABLE=1 tar -cf - docker-compose.yml scripts/demo demo/seed | docker exec -i "$RUNNER" tar -C /repo -xf -
docker exec "$RUNNER" sh -c 'cd /app/frontend && find . -path ./node_modules -prune -o -type f -print | xargs -r rm -f'
COPYFILE_DISABLE=1 tar -C frontend --exclude=node_modules --exclude=dist -cf - . | docker exec -i "$RUNNER" tar -C /app/frontend -xf -
docker exec -w /app/frontend "$RUNNER" sh -c '[ -d node_modules/@playwright ] && [ node_modules/.package-lock.json -nt package-lock.json ] || npm ci >/dev/null 2>&1'

# Wait until nginx answers through to the API.
deadline=$((SECONDS + WAIT_SECONDS))
until docker exec "$RUNNER" curl -fsS -m 5 http://grag-edge-ui/api/v1/edge/status >/dev/null 2>&1; do
  (( SECONDS < deadline )) || die "grag-edge-ui did not proxy the edge API"
  sleep 2
done
docker exec -w /app/frontend -e CHROMIUM_PATH=/usr/bin/chromium -e DEMO_ROOT=/repo -e COMPOSE_PROJECT_NAME="$project" \
  "$RUNNER" npm run e2e:real
