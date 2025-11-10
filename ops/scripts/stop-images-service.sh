#!/usr/bin/env bash
# ==============================================================================
# KITTY Images Service Stop Script
# ==============================================================================
# Stops the images service and RQ worker
#
# Usage:
#   ./ops/scripts/stop-images-service.sh
#
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
SERVICE_DIR="${REPO_ROOT}/services/images_service"

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[images-service]${NC} $1"
}

log_error() {
    echo -e "${RED}[images-service]${NC} $1"
}

# ==============================================================================
# Stop Services
# ==============================================================================

log_info "Stopping KITTY Images Service..."

cd "${SERVICE_DIR}"

# Stop FastAPI service
if [[ -f ".service.pid" ]]; then
    PID=$(cat .service.pid)
    if ps -p "${PID}" > /dev/null 2>&1; then
        log_info "Stopping FastAPI service (PID: ${PID})..."
        kill "${PID}" || true
        sleep 2
        # Force kill if still running
        if ps -p "${PID}" > /dev/null 2>&1; then
            kill -9 "${PID}" || true
        fi
    fi
    rm -f .service.pid
    log_info "FastAPI service stopped"
else
    log_info "No FastAPI service PID file found"
fi

# Stop RQ worker
if [[ -f ".rq_worker.pid" ]]; then
    PID=$(cat .rq_worker.pid)
    if ps -p "${PID}" > /dev/null 2>&1; then
        log_info "Stopping RQ worker (PID: ${PID})..."
        kill "${PID}" || true
        sleep 2
        # Force kill if still running
        if ps -p "${PID}" > /dev/null 2>&1; then
            kill -9 "${PID}" || true
        fi
    fi
    rm -f .rq_worker.pid
    log_info "RQ worker stopped"
else
    log_info "No RQ worker PID file found"
fi

log_info "Images service stopped successfully"
