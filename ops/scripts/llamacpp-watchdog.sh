#!/usr/bin/env bash
# Inspect llama.cpp (llama-server) listeners and optionally kill stray ones.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LOG_DIR="$REPO_ROOT/.logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/llamacpp-watchdog.log"

EXPECTED_PORTS_DEFAULT="${LLAMACPP_Q4_PORT:-8083} ${LLAMACPP_F16_PORT:-8082}"
SUMMARY_PORT="${LLAMACPP_SUMMARY_PORT:-8085}"
SUMMARY_ENABLED="${LLAMACPP_SUMMARY_ENABLED:-1}"
if [[ -n "${SUMMARY_PORT:-}" ]] && [[ "${SUMMARY_ENABLED,,}" != "0" && "${SUMMARY_ENABLED,,}" != "false" ]]; then
  EXPECTED_PORTS_DEFAULT+=" ${SUMMARY_PORT}"
fi
EXPECTED_PORTS="${LLAMACPP_EXPECTED_PORTS:-$EXPECTED_PORTS_DEFAULT}"

KILL_UNEXPECTED=false
if [[ ${1:-} == "--kill" ]]; then
  KILL_UNEXPECTED=true
  shift
fi

timestamp="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

log() {
  local msg="$1"
  echo "$timestamp | $msg" | tee -a "$LOG_FILE"
}

if ! command -v lsof >/dev/null 2>&1; then
  log "lsof not available; fallback to pgrep"
  pgrep -fl "llama-server" || log "No llama-server processes detected"
  exit 0
fi

declare -A expected_map
for port in $EXPECTED_PORTS; do
  if [[ -n "$port" ]]; then
    expected_map["$port"]=1
  fi
done

format_bytes() {
  local rss_kb="$1"
  if [[ -z "$rss_kb" ]]; then
    echo "0"
    return
  fi
  awk -v kb="$rss_kb" 'BEGIN {printf "%.2f MB", kb/1024}'
}

unexpected_count=0
found_count=0

while IFS= read -r line; do
  [[ -z "$line" ]] && continue
  if [[ "$line" != *"llama-server"* ]]; then
    continue
  fi
  # lsof columns: COMMAND PID USER FD TYPE DEVICE SIZE/OFF NODE NAME
  read -r command pid user _ _ _ _ _ endpoint <<<"$line"
  port="${endpoint##*:}"
  mem_kb=$(ps -o rss= -p "$pid" 2>/dev/null || echo "")
  mem_human=$(format_bytes "$mem_kb")
  status="unexpected"
  if [[ -n "${expected_map[$port]:-}" ]]; then
    status="expected"
  fi
  log "PID $pid ($command) listening on :$port | RSS $mem_human | $status"
  ((found_count++)) || true

  if [[ "$status" == "unexpected" ]]; then
    ((unexpected_count++)) || true
    if $KILL_UNEXPECTED; then
      log "Terminating unexpected llama-server PID $pid"
      kill "$pid" 2>/dev/null || true
    fi
  fi
done < <(lsof -nP -iTCP -sTCP:LISTEN)

if [[ $found_count -eq 0 ]]; then
  log "No llama-server listeners detected."
elif [[ $unexpected_count -eq 0 ]]; then
  log "All llama-server listeners match expected ports: $EXPECTED_PORTS"
else
  log "$unexpected_count unexpected listener(s) detected."
  if ! $KILL_UNEXPECTED; then
    log "Re-run with --kill to terminate them."
  fi
fi
