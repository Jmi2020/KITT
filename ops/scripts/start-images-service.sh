#!/usr/bin/env bash
# ==============================================================================
# KITTY Images Service Startup Script
# ==============================================================================
# Starts the images service (FastAPI) and RQ worker for Stable Diffusion
# image generation.
#
# Usage:
#   ./ops/scripts/start-images-service.sh
#
# Environment:
#   - Reads .env from repository root
#   - Requires Redis to be running
#   - Requires MinIO to be running
#   - Models must be downloaded and models.yaml configured
#
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
SERVICE_DIR="${REPO_ROOT}/services/images_service"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[images-service]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[images-service]${NC} $1"
}

log_error() {
    echo -e "${RED}[images-service]${NC} $1"
}

# ==============================================================================
# Pre-flight Checks
# ==============================================================================

log_info "Starting KITTY Images Service..."

# Check if .env exists
if [[ ! -f "${REPO_ROOT}/.env" ]]; then
    log_error ".env file not found. Copy .env.example to .env and configure."
    exit 1
fi

# Load environment
source "${REPO_ROOT}/.env"

# Check if service directory exists
if [[ ! -d "${SERVICE_DIR}" ]]; then
    log_error "Images service directory not found: ${SERVICE_DIR}"
    exit 1
fi

cd "${SERVICE_DIR}"

# Check if virtual environment exists, create if not
if [[ ! -d ".venv" ]]; then
    log_info "Creating virtual environment..."
    python3 -m venv .venv
    log_info "Installing dependencies..."
    .venv/bin/pip install --upgrade pip
    .venv/bin/pip install -r requirements.txt
fi

# Check if models.yaml exists
MODELS_YAML="${MODELS_YAML:-/Users/Shared/Coding/models/models.yaml}"
if [[ ! -f "${MODELS_YAML}" ]]; then
    log_warn "models.yaml not found at: ${MODELS_YAML}"
    log_warn "Copy models.yaml.example and configure model paths"
    log_warn "Download models with:"
    log_warn "  huggingface-cli download stabilityai/stable-diffusion-xl-base-1.0 --local-dir /Users/Shared/Coding/models/sd_xl_base"
fi

# Check if Redis is running
if ! command -v redis-cli &> /dev/null; then
    log_warn "redis-cli not found. Install with: brew install redis"
elif ! redis-cli ping &> /dev/null; then
    log_warn "Redis is not running. Start with: brew services start redis"
fi

# Check if MinIO is accessible
S3_ENDPOINT="${S3_ENDPOINT_URL:-http://localhost:9000}"
if ! curl -s "${S3_ENDPOINT}/minio/health/live" &> /dev/null; then
    log_warn "MinIO is not accessible at: ${S3_ENDPOINT}"
    log_warn "Make sure MinIO is running (should be started by docker-compose)"
fi

# ==============================================================================
# Start RQ Worker
# ==============================================================================

log_info "Starting RQ worker..."

# Kill existing RQ worker if running
if [[ -f ".rq_worker.pid" ]]; then
    OLD_PID=$(cat .rq_worker.pid)
    if ps -p "${OLD_PID}" > /dev/null 2>&1; then
        log_info "Stopping existing RQ worker (PID: ${OLD_PID})..."
        kill "${OLD_PID}" || true
        sleep 2
    fi
    rm -f .rq_worker.pid
fi

# Start RQ worker in background
.venv/bin/rq worker images \
    --url "${REDIS_URL:-redis://127.0.0.1:6379/0}" \
    --verbose \
    > .logs/rq_worker.log 2>&1 &

RQ_PID=$!
echo "${RQ_PID}" > .rq_worker.pid
log_info "RQ worker started (PID: ${RQ_PID})"

# ==============================================================================
# Start FastAPI Service
# ==============================================================================

log_info "Starting FastAPI service..."

# Kill existing service if running
if [[ -f ".service.pid" ]]; then
    OLD_PID=$(cat .service.pid)
    if ps -p "${OLD_PID}" > /dev/null 2>&1; then
        log_info "Stopping existing service (PID: ${OLD_PID})..."
        kill "${OLD_PID}" || true
        sleep 2
    fi
    rm -f .service.pid
fi

# Create logs directory
mkdir -p .logs

# Start service
SERVICE_HOST="${SERVICE_HOST:-127.0.0.1}"
SERVICE_PORT="${SERVICE_PORT:-8089}"

.venv/bin/uvicorn main:app \
    --host "${SERVICE_HOST}" \
    --port "${SERVICE_PORT}" \
    --log-level info \
    > .logs/service.log 2>&1 &

SERVICE_PID=$!
echo "${SERVICE_PID}" > .service.pid
log_info "FastAPI service started (PID: ${SERVICE_PID})"
log_info "Service URL: http://${SERVICE_HOST}:${SERVICE_PORT}"
log_info "API docs: http://${SERVICE_HOST}:${SERVICE_PORT}/docs"

# ==============================================================================
# Monitor and Cleanup
# ==============================================================================

log_info "Service started successfully!"
log_info "Logs:"
log_info "  - Service: ${SERVICE_DIR}/.logs/service.log"
log_info "  - Worker:  ${SERVICE_DIR}/.logs/rq_worker.log"
log_info ""
log_info "To stop:"
log_info "  ./ops/scripts/stop-images-service.sh"

# Wait for processes
wait
