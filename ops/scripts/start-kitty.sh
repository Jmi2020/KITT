#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ENV_FILE="${ENV_FILE:-$REPO_ROOT/.env}"
COMPOSE_FILE="${COMPOSE_FILE:-$REPO_ROOT/infra/compose/docker-compose.yml}"
LLAMACPP_LOG="${LLAMACPP_LOG:-$REPO_ROOT/.logs/llamacpp.log}"

mkdir -p "$REPO_ROOT/.logs"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Environment file not found at $ENV_FILE" >&2
  exit 1
fi

set -a
source "$ENV_FILE"
set +a

LLAMACPP_PID_FILE="$REPO_ROOT/.logs/llamacpp.pid"

cleanup() {
  if [[ -n "${COMPOSE_UP:-}" ]]; then
    docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" down || true
  fi
  if [[ -f "$LLAMACPP_PID_FILE" ]]; then
    kill "$(cat "$LLAMACPP_PID_FILE")" >/dev/null 2>&1 || true
    rm -f "$LLAMACPP_PID_FILE"
  fi
}

trap cleanup EXIT

# Start llama.cpp in background
"$SCRIPT_DIR/start-llamacpp.sh" > "$LLAMACPP_LOG" 2>&1 &
LLAMACPP_PID=$!
echo "$LLAMACPP_PID" > "$LLAMACPP_PID_FILE"

sleep 2

echo "llama.cpp (PID $LLAMACPP_PID) logging to $LLAMACPP_LOG"

docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d --build
COMPOSE_UP=1

echo "KITTY stack running. Press Ctrl+C to stop."
wait $LLAMACPP_PID
