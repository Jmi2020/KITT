#!/usr/bin/env bash
# ==============================================================================
# KITTY Voice Service Startup Script
# ==============================================================================
# Starts the voice service (FastAPI) for STT/TTS and WebSocket streaming.
#
# Usage:
#   ./ops/scripts/start-voice-service.sh
#
# Environment:
#   - Reads .env from repository root
#   - VOICE_BASE_URL defaults to http://localhost:8400
#   - VOICE_PREFER_LOCAL enables local Whisper/Piper
#
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
SERVICE_DIR="${REPO_ROOT}/services/voice"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

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
# Pre-flight Checks
# ==============================================================================

log_info "Starting KITTY Voice Service..."

# Check if .env exists
if [[ ! -f "${REPO_ROOT}/.env" ]]; then
    log_error ".env file not found. Copy .env.example to .env and configure."
    exit 1
fi

# Load environment (export everything)
set -a
source "${REPO_ROOT}/.env"
set +a

# Override Docker-specific hostnames for native process
# (Docker hostnames don't resolve outside Docker)
export OLLAMA_HOST="${OLLAMA_HOST//host.docker.internal/localhost}"
export LLAMACPP_HOST="${LLAMACPP_HOST//host.docker.internal/localhost}"
export LLAMACPP_Q4_HOST="${LLAMACPP_Q4_HOST//host.docker.internal/localhost}"
export LLAMACPP_F16_HOST="${LLAMACPP_F16_HOST//host.docker.internal/localhost}"
export LLAMACPP_SUMMARY_HOST="${LLAMACPP_SUMMARY_HOST//host.docker.internal/localhost}"
# Memory service (mem0-mcp is a Docker service name)
export MEM0_MCP_URL="http://localhost:8765"
# MQTT broker
export MQTT_HOST="${MQTT_HOST:-localhost}"
export MQTT_BROKER="${MQTT_BROKER:-localhost}"
log_info "Configured service hosts for native process (using localhost)"

# Check if service directory exists
if [[ ! -d "${SERVICE_DIR}" ]]; then
    log_error "Voice service directory not found: ${SERVICE_DIR}"
    exit 1
fi

cd "${SERVICE_DIR}"

# Ensure logs directory exists
LOG_DIR="${REPO_ROOT}/.logs"
mkdir -p "$LOG_DIR"

# Check if virtual environment exists, create if not
if [[ ! -d ".venv" ]]; then
    log_info "Creating virtual environment..."
    python3 -m venv .venv
    log_info "Installing dependencies..."
    .venv/bin/pip install --upgrade pip
    .venv/bin/pip install -e .
fi

# ==============================================================================
# Start FastAPI Service
# ==============================================================================

log_info "Starting FastAPI voice service..."

# Kill existing service if running
PID_FILE="${LOG_DIR}/voice-service.pid"
if [[ -f "${PID_FILE}" ]]; then
    OLD_PID=$(cat "${PID_FILE}")
    if ps -p "${OLD_PID}" > /dev/null 2>&1; then
        log_info "Stopping existing voice service (PID: ${OLD_PID})..."
        kill "${OLD_PID}" || true
        sleep 2
    fi
    rm -f "${PID_FILE}"
fi

# Start service
VOICE_HOST="${VOICE_HOST:-127.0.0.1}"
VOICE_PORT="${VOICE_PORT:-8410}"

.venv/bin/uvicorn voice.app:app \
    --host "${VOICE_HOST}" \
    --port "${VOICE_PORT}" \
    --log-level info \
    > "${LOG_DIR}/voice-service.log" 2>&1 &

SERVICE_PID=$!
echo "${SERVICE_PID}" > "${PID_FILE}"
log_info "Voice service started (PID: ${SERVICE_PID})"
log_info "Service URL: http://${VOICE_HOST}:${VOICE_PORT}"
log_info "Health endpoint: http://${VOICE_HOST}:${VOICE_PORT}/healthz"

# ==============================================================================
# Health Check
# ==============================================================================

log_info "Waiting for voice service to be ready..."

MAX_WAIT=30
ELAPSED=0
while [ $ELAPSED -lt $MAX_WAIT ]; do
    if curl -s "http://${VOICE_HOST}:${VOICE_PORT}/healthz" | grep -q "ok"; then
        log_info "Voice service is healthy!"
        break
    fi
    sleep 1
    ELAPSED=$((ELAPSED + 1))
done

if [ $ELAPSED -ge $MAX_WAIT ]; then
    log_warn "Voice service health check timed out (may still be starting)"
fi

# ==============================================================================
# Summary
# ==============================================================================

log_info "Voice service started successfully!"
log_info "Logs: ${LOG_DIR}/voice-service.log"
log_info ""
log_info "To stop:"
log_info "  ./ops/scripts/stop-voice-service.sh"
