#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Start Ollama daemon and warmup GPT-OSS:120B model

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# Load environment variables
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

# Configuration
OLLAMA_HOST="${OLLAMA_HOST:-http://localhost:11434}"
OLLAMA_MODEL="${OLLAMA_MODEL:-gpt-oss:120b}"
OLLAMA_PORT="${OLLAMA_HOST##*:}"
OLLAMA_PORT="${OLLAMA_PORT:-11434}"
PID_FILE="$PROJECT_ROOT/.ollama.pid"
LOG_FILE="$PROJECT_ROOT/.logs/ollama.log"

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

# When OLLAMA_HOST points at host.docker.internal (common in Docker envs), resolve to
# localhost for host-side CLI operations if that hostname is unavailable (e.g., on mac).
CLIENT_OLLAMA_HOST="$OLLAMA_HOST"
HOST_PART="$(printf "%s" "$OLLAMA_HOST" | sed -e 's|^[a-zA-Z0-9+.-]*://||' -e 's|:.*$||')"
if [[ "$HOST_PART" == "host.docker.internal" ]]; then
    if python3 - <<'PY' 2>/dev/null; then
import socket
socket.gethostbyname("host.docker.internal")
PY
        :
    else
        warn "host.docker.internal not resolvable; using localhost for CLI operations"
        CLIENT_OLLAMA_HOST="http://localhost:${OLLAMA_PORT}"
    fi
fi

# Ensure log directory exists
mkdir -p "$(dirname "$LOG_FILE")"

# Check if Ollama is already running
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        log "Ollama is already running (PID: $PID)"
        exit 0
    else
        warn "Stale PID file found, removing..."
        rm -f "$PID_FILE"
    fi
fi

# Check if port is in use
if lsof -Pi :"$OLLAMA_PORT" -sTCP:LISTEN -t >/dev/null 2>&1; then
    warn "Port $OLLAMA_PORT is already in use"
    EXISTING_PID=$(lsof -Pi :"$OLLAMA_PORT" -sTCP:LISTEN -t)
    log "Existing Ollama daemon detected (PID: $EXISTING_PID)"
    echo "$EXISTING_PID" > "$PID_FILE"
else
    # Start Ollama daemon
    log "Starting Ollama daemon on port $OLLAMA_PORT..."
    OLLAMA_HOST="0.0.0.0:$OLLAMA_PORT" ollama serve >> "$LOG_FILE" 2>&1 &
    OLLAMA_PID=$!
    echo "$OLLAMA_PID" > "$PID_FILE"
    log "Ollama daemon started (PID: $OLLAMA_PID)"
fi

# Wait for Ollama to be ready
log "Waiting for Ollama API to be ready..."
MAX_WAIT=30
ELAPSED=0
while [ $ELAPSED -lt $MAX_WAIT ]; do
    if curl -s "${CLIENT_OLLAMA_HOST}/api/tags" >/dev/null 2>&1; then
        log "Ollama API is ready"
        break
    fi
    sleep 1
    ELAPSED=$((ELAPSED + 1))
done

if [ $ELAPSED -ge $MAX_WAIT ]; then
    error "Ollama failed to start within ${MAX_WAIT}s"
    exit 1
fi

# Check if model is already pulled
log "Checking for model: $OLLAMA_MODEL"
if curl -s "${CLIENT_OLLAMA_HOST}/api/tags" | grep -q "\"$OLLAMA_MODEL\""; then
    log "Model $OLLAMA_MODEL is already available"
else
    warn "Model $OLLAMA_MODEL not found"
    log "Pulling model (this may take a while, ~65 GB download)..."
    log "You can also run manually: ollama pull $OLLAMA_MODEL"

    # Pull model
    if OLLAMA_HOST="$CLIENT_OLLAMA_HOST" ollama pull "$OLLAMA_MODEL"; then
        log "Model $OLLAMA_MODEL pulled successfully"
    else
        error "Failed to pull model $OLLAMA_MODEL"
        error "Please run manually: ollama pull $OLLAMA_MODEL"
        exit 1
    fi
fi

# Warmup: Load model into memory
log "Warming up model (keep_alive)..."
echo '{"model":"'"$OLLAMA_MODEL"'","prompt":"Hello","stream":false,"keep_alive":"5m"}' | \
    curl -s -X POST "${CLIENT_OLLAMA_HOST}/api/generate" \
    -H "Content-Type: application/json" \
    -d @- >/dev/null 2>&1 || {
    warn "Model warmup request failed (non-critical)"
}

log "✓ Ollama is ready with model: $OLLAMA_MODEL"
log "API endpoint: ${CLIENT_OLLAMA_HOST}"
log "Logs: $LOG_FILE"
