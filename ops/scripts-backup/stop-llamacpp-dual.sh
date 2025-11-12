#!/usr/bin/env bash
# Stop dual llama.cpp servers (Q4 and F16)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
Q4_PID_FILE="$REPO_ROOT/.logs/llamacpp-q4.pid"
F16_PID_FILE="$REPO_ROOT/.logs/llamacpp-f16.pid"
SUMMARY_PID_FILE="$REPO_ROOT/.logs/llamacpp-summary.pid"
VISION_PID_FILE="$REPO_ROOT/.logs/llamacpp-vision.pid"
PROCESS_NAME="${LLAMACPP_PROCESS_NAME:-llama-server}"

stop_pid() {
  local pid="$1"
  local name="$2"
  if [[ -z "$pid" ]]; then
    return 0
  fi

  if kill -0 "$pid" >/dev/null 2>&1; then
    echo "Stopping $name (PID $pid)..."
    kill "$pid" >/dev/null 2>&1 || true
    # Give it a moment to shut down gracefully
    sleep 1
    # Force kill if still running
    if kill -0 "$pid" >/dev/null 2>&1; then
      kill -9 "$pid" >/dev/null 2>&1 || true
    fi
  fi
}

stopped_any=false

# Stop Q4 server
if [[ -f "$Q4_PID_FILE" ]]; then
  Q4_PID="$(cat "$Q4_PID_FILE")"
  stop_pid "$Q4_PID" "Q4 server"
  rm -f "$Q4_PID_FILE"
  stopped_any=true
fi

# Stop F16 server
if [[ -f "$F16_PID_FILE" ]]; then
  F16_PID="$(cat "$F16_PID_FILE")"
  stop_pid "$F16_PID" "F16 server"
  rm -f "$F16_PID_FILE"
  stopped_any=true
fi

# Stop summary server
if [[ -f "$SUMMARY_PID_FILE" ]]; then
  SUMMARY_PID="$(cat "$SUMMARY_PID_FILE")"
  stop_pid "$SUMMARY_PID" "Hermes summary server"
  rm -f "$SUMMARY_PID_FILE"
  stopped_any=true
fi

# Stop vision server
if [[ -f "$VISION_PID_FILE" ]]; then
  VISION_PID="$(cat "$VISION_PID_FILE")"
  stop_pid "$VISION_PID" "Vision server"
  rm -f "$VISION_PID_FILE"
  stopped_any=true
fi

# Fallback if PID files are missing (manual start, crash, etc.)
if [[ "$stopped_any" == "false" ]]; then
  PIDS="$(pgrep -f "$PROCESS_NAME" || true)"
  if [[ -n "$PIDS" ]]; then
    echo "No PID files found. Stopping all running \"$PROCESS_NAME\" processes: $PIDS"
    for pid in $PIDS; do
      stop_pid "$pid" "llama-server"
    done
  else
    echo "No running llama.cpp processes detected."
  fi
else
  echo "Dual-model servers stopped."
fi
