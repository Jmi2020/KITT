#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PID_FILE="$REPO_ROOT/.logs/llamacpp.pid"
PROCESS_NAME="${LLAMACPP_PROCESS_NAME:-llama-server}"

stop_pid() {
  local pid="$1"
  if [[ -z "$pid" ]]; then
    return 0
  fi

  if kill -0 "$pid" >/dev/null 2>&1; then
    echo "Stopping llama.cpp (PID $pid)..."
    kill "$pid" >/dev/null 2>&1 || true
    wait "$pid" 2>/dev/null || true
  fi
}

if [[ -f "$PID_FILE" ]]; then
  PID="$(cat "$PID_FILE")"
  stop_pid "$PID"
  rm -f "$PID_FILE"
  exit 0
fi

# Fallback if PID file is missing (manual start, crash, etc.)
PIDS="$(pgrep -f "$PROCESS_NAME" || true)"
if [[ -n "$PIDS" ]]; then
  echo "No PID file found. Stopping all running \"$PROCESS_NAME\" processes: $PIDS"
  for pid in $PIDS; do
    stop_pid "$pid"
  done
else
  echo "No running llama.cpp process detected."
fi
