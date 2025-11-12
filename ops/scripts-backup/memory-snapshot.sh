#!/usr/bin/env bash
# Capture current system memory statistics for later comparison.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LOG_DIR="$REPO_ROOT/.logs/memory"
mkdir -p "$LOG_DIR"

timestamp="$(date -u +"%Y%m%dT%H%M%SZ")"
outfile="$LOG_DIR/memory-${timestamp}.log"

exec > >(tee "$outfile")
exec 2>&1

echo "=================================================="
echo "KITTY Memory Snapshot | UTC $timestamp"
echo "=================================================="

echo -e "\n[Top - first 20 lines]"
top -l 1 | head -n 20

echo -e "\n[vm_stat]"
vm_stat

echo -e "\n[memory_pressure]"
if command -v memory_pressure >/dev/null 2>&1; then
  memory_pressure
else
  echo "memory_pressure command not available on this host."
fi

echo -e "\n[llama-server processes listening]"
if command -v lsof >/dev/null 2>&1; then
  lsof -nP -iTCP -sTCP:LISTEN | grep -i "llama" || echo "No llama-server listeners detected."
else
  pgrep -fl "llama-server" || echo "No llama-server processes detected."
fi

echo -e "\nSnapshot saved to $outfile"
