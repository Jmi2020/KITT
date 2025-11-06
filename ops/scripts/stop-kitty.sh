#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ENV_FILE="${ENV_FILE:-$REPO_ROOT/.env}"
COMPOSE_FILE="${COMPOSE_FILE:-$REPO_ROOT/infra/compose/docker-compose.yml}"
LLAMACPP_PID_FILE="$REPO_ROOT/.logs/llamacpp.pid"

if [[ -f "$COMPOSE_FILE" ]]; then
  if [[ -f "$ENV_FILE" ]]; then
    docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" down || true
  else
    docker compose -f "$COMPOSE_FILE" down || true
  fi
fi

if [[ -f "$LLAMACPP_PID_FILE" ]]; then
  PID=$(cat "$LLAMACPP_PID_FILE")
  if kill -0 "$PID" >/dev/null 2>&1; then
    kill "$PID"
  fi
  rm -f "$LLAMACPP_PID_FILE"
fi

echo "KITTY stack stopped."
