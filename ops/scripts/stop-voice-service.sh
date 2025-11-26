#!/usr/bin/env bash
# ==============================================================================
# KITTY Voice Service Stop Script
# ==============================================================================
# Stops the voice service (FastAPI).
#
# Usage:
#   ./ops/scripts/stop-voice-service.sh
#
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
LOG_DIR="${REPO_ROOT}/.logs"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[voice-service]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[voice-service]${NC} $1"
}

log_error() {
    echo -e "${RED}[voice-service]${NC} $1"
}

# ==============================================================================
# Stop Voice Service
# ==============================================================================

log_info "Stopping KITTY Voice Service..."

PID_FILE="${LOG_DIR}/voice-service.pid"

if [[ -f "${PID_FILE}" ]]; then
    PID=$(cat "${PID_FILE}")
    if ps -p "${PID}" > /dev/null 2>&1; then
        log_info "Stopping voice service (PID: ${PID})..."
        kill "${PID}" || true

        # Wait for graceful shutdown
        TIMEOUT=10
        while [ $TIMEOUT -gt 0 ] && ps -p "${PID}" > /dev/null 2>&1; do
            sleep 1
            TIMEOUT=$((TIMEOUT - 1))
        done

        # Force kill if still running
        if ps -p "${PID}" > /dev/null 2>&1; then
            log_warn "Force killing voice service..."
            kill -9 "${PID}" || true
        fi

        log_info "Voice service stopped"
    else
        log_info "Voice service not running (stale PID file)"
    fi
    rm -f "${PID_FILE}"
else
    log_info "Voice service not running (no PID file)"
fi

# Also check for any orphaned uvicorn processes on voice port
VOICE_PORT="${VOICE_PORT:-8400}"
ORPHAN_PID=$(lsof -ti:${VOICE_PORT} 2>/dev/null || true)
if [[ -n "${ORPHAN_PID}" ]]; then
    log_warn "Found orphaned process on port ${VOICE_PORT} (PID: ${ORPHAN_PID}), killing..."
    kill "${ORPHAN_PID}" || true
fi

log_info "Voice service shutdown complete"
