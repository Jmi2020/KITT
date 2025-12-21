#!/bin/bash
# Stop all llama.cpp servers gracefully

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
cd "$PROJECT_ROOT"

LOG_DIR="$PROJECT_ROOT/.logs"

# Color output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() {
    echo -e "${BLUE}[$(date '+%H:%M:%S')]${NC} $1"
}

success() {
    echo -e "${GREEN}✓${NC} $1"
}

warn() {
    echo -e "${YELLOW}⚠${NC} $1"
}

# ========================================
# Stop servers by PID file
# ========================================

stop_server() {
    local name=$1
    local pid_file="$LOG_DIR/llamacpp-${name}.pid"

    if [ ! -f "$pid_file" ]; then
        log "$name server: No PID file found"
        return 0
    fi

    local pid=$(cat "$pid_file")

    if ! kill -0 "$pid" 2>/dev/null; then
        log "$name server: Not running (stale PID file)"
        rm -f "$pid_file"
        return 0
    fi

    log "Stopping $name server (PID $pid)"

    # Try graceful SIGTERM first
    kill -TERM "$pid" 2>/dev/null || true

    # Wait up to 10 seconds for graceful shutdown
    local waited=0
    while kill -0 "$pid" 2>/dev/null && [ $waited -lt 10 ]; do
        sleep 1
        waited=$((waited + 1))
    done

    # Force kill if still running
    if kill -0 "$pid" 2>/dev/null; then
        warn "$name server didn't stop gracefully, forcing..."
        kill -KILL "$pid" 2>/dev/null || true
        sleep 1
    fi

    # Verify stopped
    if ! kill -0 "$pid" 2>/dev/null; then
        success "$name server stopped"
        rm -f "$pid_file"
    else
        warn "$name server may still be running"
    fi
}

# Stop all known servers
stop_server "q4"
stop_server "f16"
stop_server "summary"
stop_server "vision"
stop_server "coder"

# ========================================
# Fallback: Kill any remaining llama-server processes
# ========================================

REMAINING=$(pgrep -f llama-server | wc -l)

if [ "$REMAINING" -gt 0 ]; then
    warn "Found $REMAINING remaining llama-server processes"
    log "Attempting to kill remaining processes..."

    pkill -TERM -f llama-server 2>/dev/null || true
    sleep 2

    # Force kill if still running
    if pgrep -f llama-server > /dev/null; then
        pkill -KILL -f llama-server 2>/dev/null || true
        sleep 1
    fi

    # Final check
    if pgrep -f llama-server > /dev/null; then
        warn "Some llama-server processes may still be running"
        echo "Manual check: ps aux | grep llama-server"
    else
        success "All llama-server processes terminated"
    fi
else
    success "All servers stopped"
fi

# Clean up PID files
rm -f "$LOG_DIR/llamacpp-*.pid" 2>/dev/null || true

exit 0
