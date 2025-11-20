#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Stop Ollama daemon gracefully

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

PID_FILE="$PROJECT_ROOT/.ollama.pid"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

log() {
    echo -e "${GREEN}[Ollama]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[Ollama]${NC} $1"
}

error() {
    echo -e "${RED}[Ollama]${NC} $1"
}

# Check if PID file exists
if [ ! -f "$PID_FILE" ]; then
    warn "No PID file found at $PID_FILE"

    # Try to find Ollama process by name
    if pgrep -x "ollama" >/dev/null 2>&1; then
        warn "Found Ollama process(es) running without PID file"
        log "Stopping all Ollama processes..."
        pkill -x "ollama" || true
        sleep 2

        # Force kill if still running
        if pgrep -x "ollama" >/dev/null 2>&1; then
            warn "Ollama still running, force killing..."
            pkill -9 -x "ollama" || true
        fi

        log "✓ Ollama stopped"
    else
        log "Ollama is not running"
    fi
    exit 0
fi

# Read PID from file
PID=$(cat "$PID_FILE")

# Check if process is running
if ! kill -0 "$PID" 2>/dev/null; then
    warn "Process $PID is not running (stale PID file)"
    rm -f "$PID_FILE"
    log "Cleaned up stale PID file"
    exit 0
fi

# Gracefully stop Ollama
log "Stopping Ollama daemon (PID: $PID)..."
kill -TERM "$PID" 2>/dev/null || true

# Wait for graceful shutdown (up to 10 seconds)
MAX_WAIT=10
ELAPSED=0
while [ $ELAPSED -lt $MAX_WAIT ]; do
    if ! kill -0 "$PID" 2>/dev/null; then
        log "✓ Ollama stopped gracefully"
        rm -f "$PID_FILE"
        exit 0
    fi
    sleep 1
    ELAPSED=$((ELAPSED + 1))
done

# Force kill if still running
if kill -0 "$PID" 2>/dev/null; then
    warn "Ollama did not stop gracefully, force killing..."
    kill -9 "$PID" 2>/dev/null || true
    sleep 1

    if kill -0 "$PID" 2>/dev/null; then
        error "Failed to stop Ollama (PID: $PID)"
        exit 1
    fi
fi

rm -f "$PID_FILE"
log "✓ Ollama stopped"
