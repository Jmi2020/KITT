#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ENV_FILE="${ENV_FILE:-$REPO_ROOT/.env}"
COMPOSE_FILE="${COMPOSE_FILE:-$REPO_ROOT/infra/compose/docker-compose.yml}"
LLAMACPP_Q4_LOG="${LLAMACPP_Q4_LOG:-$REPO_ROOT/.logs/llamacpp-q4.log}"
LLAMACPP_F16_LOG="${LLAMACPP_F16_LOG:-$REPO_ROOT/.logs/llamacpp-f16.log}"

mkdir -p "$REPO_ROOT/.logs"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Environment file not found at $ENV_FILE" >&2
  exit 1
fi

set -a
source "$ENV_FILE"
set +a

Q4_PID_FILE="$REPO_ROOT/.logs/llamacpp-q4.pid"
F16_PID_FILE="$REPO_ROOT/.logs/llamacpp-f16.pid"

cleanup() {
  if [[ -n "${COMPOSE_UP:-}" ]]; then
    docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" down || true
  fi
  # Use the stop script to cleanly shut down both servers
  "$SCRIPT_DIR/stop-llamacpp-dual.sh" || true
  # Stop images service if it was started
  if [[ -n "${IMAGES_SERVICE_STARTED:-}" ]]; then
    "$SCRIPT_DIR/stop-images-service.sh" || true
  fi
}

trap cleanup EXIT

# Start dual llama.cpp servers in background
"$SCRIPT_DIR/start-llamacpp-dual.sh" > "$REPO_ROOT/.logs/llamacpp-dual.log" 2>&1 &
DUAL_PID=$!

sleep 3

echo "Dual-model llama.cpp servers started:"
echo "  Q4 (Tool Orchestrator) logging to $LLAMACPP_Q4_LOG"
echo "  F16 (Reasoning Engine) logging to $LLAMACPP_F16_LOG"

docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d --build
COMPOSE_UP=1

# Optionally start images service (Stable Diffusion)
if [[ "${IMAGES_SERVICE_ENABLED:-false}" == "true" ]]; then
  echo "Starting images service (Stable Diffusion)..."
  "$SCRIPT_DIR/start-images-service.sh" > "$REPO_ROOT/.logs/images-service-startup.log" 2>&1 &
  IMAGES_SERVICE_STARTED=1
  echo "Images service started (logs: .logs/images-service-startup.log)"
fi

echo "KITTY stack running. Press Ctrl+C to stop."
wait $DUAL_PID
