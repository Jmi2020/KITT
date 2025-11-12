#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ENV_FILE="${ENV_FILE:-$REPO_ROOT/.env}"
COMPOSE_FILE="${COMPOSE_FILE:-$REPO_ROOT/infra/compose/docker-compose.yml}"

# Stop Docker services
if [[ -f "$COMPOSE_FILE" ]]; then
  if [[ -f "$ENV_FILE" ]]; then
    docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" down || true
  else
    docker compose -f "$COMPOSE_FILE" down || true
  fi
fi

# Stop dual-model llama.cpp servers
"$SCRIPT_DIR/stop-llamacpp-dual.sh" || true

echo "KITTY stack stopped."
