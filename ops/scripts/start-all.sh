#!/bin/bash
# Start all KITTY services with validation
# Combines llama.cpp servers + Docker services with health checks

set -e

# ========================================
# Configuration
# ========================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
COMPOSE_DIR="$PROJECT_ROOT/infra/compose"
IMAGE_SERVICE_URL="${IMAGE_SERVICE_URL:-http://127.0.0.1:8089}"
IMAGE_SERVICE_HEALTH_ENDPOINT="$IMAGE_SERVICE_URL"
cd "$PROJECT_ROOT"

# Docker compose helper (always run from infra/compose)
# Includes message queue (P2 #15) by default
compose_cmd() {
    (cd "$COMPOSE_DIR" && docker compose -f docker-compose.yml -f docker-compose.message-queue.yml "$@")
}

is_images_service_running() {
    curl -sf "$IMAGE_SERVICE_HEALTH_ENDPOINT" >/dev/null 2>&1
}

start_images_service() {
    if is_images_service_running; then
        success "Images service already running"
        return 0
    fi

    log "Starting images service"

    # Ensure log exists
    : > "$IMAGE_SERVICE_LOG"

    nohup "$SCRIPT_DIR/start-images-service.sh" >> "$IMAGE_SERVICE_LOG" 2>&1 &
    IMAGE_BOOT_PID=$!

    # Wait for health endpoint
    MAX_WAIT=120
    ELAPSED=0
    while [ $ELAPSED -lt $MAX_WAIT ]; do
        if ! kill -0 "$IMAGE_BOOT_PID" >/dev/null 2>&1; then
            error "Images service launcher exited unexpectedly"
            tail -n 50 "$IMAGE_SERVICE_LOG"
            return 1
        fi

        if is_images_service_running; then
            success "Images service running"
            return 0
        fi

        sleep 5
        ELAPSED=$((ELAPSED + 5))
        log "Waiting for images service... (${ELAPSED}s)"
    done

    error "Images service failed to become healthy (check $IMAGE_SERVICE_LOG)"
    return 1
}

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Logging
LOG_DIR="$PROJECT_ROOT/.logs"
mkdir -p "$LOG_DIR"
STARTUP_LOG="$LOG_DIR/startup-$(date +%Y%m%d-%H%M%S).log"
IMAGE_SERVICE_LOG="$LOG_DIR/images-service.log"

# Helper functions
log() {
    echo -e "${BLUE}[$(date '+%H:%M:%S')]${NC} $1" | tee -a "$STARTUP_LOG"
}

success() {
    echo -e "${GREEN}✓${NC} $1" | tee -a "$STARTUP_LOG"
}

error() {
    echo -e "${RED}✗${NC} $1" | tee -a "$STARTUP_LOG"
}

warn() {
    echo -e "${YELLOW}⚠${NC} $1" | tee -a "$STARTUP_LOG"
}

to_lower() {
    echo "$1" | tr '[:upper:]' '[:lower:]'
}

is_enabled() {
    local value
    value=$(to_lower "${1:-1}")
    [[ "$value" == "1" || "$value" == "true" || "$value" == "yes" || "$value" == "on" ]]
}

# ========================================
# Load Environment
# ========================================

if [ ! -f .env ]; then
    error "Error: .env file not found"
    exit 1
fi

log "Loading environment from .env"
set -a
source .env
set +a

# ========================================
# Cleanup Handler
# ========================================

cleanup() {
    warn "Interrupt received, stopping services..."
    "$SCRIPT_DIR/stop-all.sh"
    exit 130
}

trap cleanup INT TERM

# ========================================
# Phase 1: Start LLM Servers
# ========================================

# Optional: skip discovery container if host-native discovery is used
if [ "${DISCOVERY_HOST_NATIVE:-0}" = "1" ]; then
    log "DISCOVERY_HOST_NATIVE=1 set - skipping discovery container; expecting host service on ${DISCOVERY_BASE:-http://localhost:8500}"
    SKIP_DISCOVERY=1
else
    SKIP_DISCOVERY=0
fi

# Resolve ports/aliases (defaults align with .env keys)
Q4_PORT="${LLAMACPP_Q4_PORT:-8083}"
Q4_ALIAS="${LLAMACPP_Q4_ALIAS:-kitty-q4}"
F16_PORT="${LLAMACPP_F16_PORT:-8082}"
F16_ALIAS="${LLAMACPP_F16_ALIAS:-kitty-f16}"
SUMMARY_PORT="${LLAMACPP_SUMMARY_PORT:-8084}"
SUMMARY_ALIAS="${LLAMACPP_SUMMARY_ALIAS:-kitty-summary}"
VISION_PORT="${LLAMACPP_VISION_PORT:-8086}"
VISION_ALIAS="${LLAMACPP_VISION_ALIAS:-kitty-vision}"

# Determine reasoning provider: ollama (GPTOSS 120B - default) or llamacpp (deprecated Llama 3.3 F16)
LOCAL_REASONER_PROVIDER="${LOCAL_REASONER_PROVIDER:-ollama}"

if [ "$LOCAL_REASONER_PROVIDER" == "ollama" ]; then
    log "Phase 1a: Starting Ollama (GPTOSS 120B - primary reasoning model)"

    if ! "$SCRIPT_DIR/ollama/start.sh"; then
        error "Failed to start Ollama"
        exit 1
    fi

    success "Ollama started"
fi

log "Phase 1b: Starting llama.cpp servers"

if ! "$SCRIPT_DIR/llama/start.sh"; then
    error "Failed to start llama.cpp servers"
    exit 1
fi

success "llama.cpp servers started"

# ========================================
# Phase 2: Wait for LLM Server Health
# ========================================

log "Phase 2: Waiting for LLM servers to be ready"

MAX_WAIT=600  # 10 minutes for model loading
ELAPSED=0
INTERVAL=10

PORTS_TO_CHECK=("$Q4_PORT")
PORT_LABELS=("$Q4_ALIAS (Q4)")
HEALTH_ENDPOINTS=("/health")

# Add F16 or Ollama depending on LOCAL_REASONER_PROVIDER
if [ "$LOCAL_REASONER_PROVIDER" == "ollama" ]; then
    # Ollama health check uses /api/tags endpoint
    OLLAMA_PORT="${OLLAMA_HOST##*:}"
    OLLAMA_PORT="${OLLAMA_PORT:-11434}"
    PORTS_TO_CHECK+=("$OLLAMA_PORT")
    PORT_LABELS+=("Ollama (GPTOSS 120B reasoner)")
    HEALTH_ENDPOINTS+=("/api/tags")
else
    # DEPRECATED: llama.cpp F16 health check (Llama 3.3 70B - legacy fallback)
    PORTS_TO_CHECK+=("$F16_PORT")
    PORT_LABELS+=("$F16_ALIAS (F16 - deprecated)")
    HEALTH_ENDPOINTS+=("/health")
fi

SUMMARY_ENABLED="${LLAMACPP_SUMMARY_ENABLED:-1}"
VISION_ENABLED="${LLAMACPP_VISION_ENABLED:-1}"

if is_enabled "$SUMMARY_ENABLED"; then
    PORTS_TO_CHECK+=("$SUMMARY_PORT")
    PORT_LABELS+=("$SUMMARY_ALIAS (summary)")
    HEALTH_ENDPOINTS+=("/health")
fi

if is_enabled "$VISION_ENABLED"; then
    PORTS_TO_CHECK+=("$VISION_PORT")
    PORT_LABELS+=("$VISION_ALIAS (vision)")
    HEALTH_ENDPOINTS+=("/health")
fi

while [ $ELAPSED -lt $MAX_WAIT ]; do
    missing=()
    for idx in "${!PORTS_TO_CHECK[@]}"; do
        port="${PORTS_TO_CHECK[$idx]}"
        label="${PORT_LABELS[$idx]}"
        endpoint="${HEALTH_ENDPOINTS[$idx]}"

        # Different health check for Ollama vs llama.cpp
        if [[ "$endpoint" == "/api/tags" ]]; then
            # Ollama health check: verify /api/tags returns JSON with models
            if ! curl -s "http://localhost:${port}${endpoint}" 2>/dev/null | grep -q '"models"'; then
                missing+=("${label}:${port}")
            fi
        else
            # llama.cpp health check: verify /health returns status:ok
            if ! curl -s "http://localhost:${port}${endpoint}" 2>/dev/null | grep -q '"status":"ok"'; then
                missing+=("${label}:${port}")
            fi
        fi
    done

    if [ ${#missing[@]} -eq 0 ]; then
        success "All LLM servers healthy"
        break
    fi

    if [ $((ELAPSED % 30)) -eq 0 ]; then
        log "Still waiting for LLM servers... missing: ${missing[*]} (${ELAPSED}s elapsed)"
    fi

    sleep $INTERVAL
    ELAPSED=$((ELAPSED + INTERVAL))
done

if [ ${#missing[@]} -ne 0 ]; then
    error "LLM servers failed to become healthy within ${MAX_WAIT}s"
    error "Still waiting on: ${missing[*]}"
    if [ "$LOCAL_REASONER_PROVIDER" == "ollama" ]; then
        error "Check logs: $LOG_DIR/llamacpp-*.log and $LOG_DIR/ollama.log"
    else
        error "Check logs: $LOG_DIR/llamacpp-*.log"
    fi
    exit 1
fi

# ========================================
# Phase 3: Start Docker Services
# ========================================

log "Phase 3: Starting Docker Compose services"

# Change to infra/compose directory for docker compose
if [ "$SKIP_DISCOVERY" -eq 1 ]; then
    log "Bringing up compose services without discovery (scaled to 0)"
    if ! compose_cmd up -d --build --scale discovery=0 2>&1 | tee -a "$STARTUP_LOG"; then
        error "Docker Compose startup failed"
        exit 1
    fi
else
    if ! compose_cmd up -d --build 2>&1 | tee -a "$STARTUP_LOG"; then
        error "Docker Compose startup failed"
        exit 1
    fi
fi

success "Docker services started"

# ========================================
# Phase 3.5: Start Load Balancer (P1 #4)
# ========================================

log "Phase 3.5: Starting Gateway Load Balancer"

# Start load balancer with 3 gateway replicas
if ! compose_cmd up -d gateway load-balancer 2>&1 | tee -a "$STARTUP_LOG"; then
    warn "Load balancer startup failed (non-critical)"
else
    success "Load balancer started (3 gateway replicas)"

    # Wait for load balancer health
    sleep 5
    if curl -s http://localhost:8080/healthz | grep -q "ok"; then
        success "Load balancer health check passed"
    else
        warn "Load balancer health check failed (may still be starting)"
    fi
fi

# ========================================
# Phase 4: Validate Services
# ========================================

log "Phase 4: Validating service health"

sleep 10  # Give services time to initialize

# Check brain service
if docker ps | grep -q compose-brain-1; then
    success "Brain service running"

    # Check for LangGraph initialization
    if docker logs compose-brain-1 2>&1 | grep -q "LangGraph"; then
        ROLLOUT=$(docker logs compose-brain-1 2>&1 | grep "rollout" | tail -1)
        success "LangGraph initialized: $ROLLOUT"
    fi
else
    error "Brain service not running"
    compose_cmd ps
    exit 1
fi

# Check critical services
CRITICAL_SERVICES=("brain" "gateway" "postgres" "redis" "rabbitmq")
for service in "${CRITICAL_SERVICES[@]}"; do
    if compose_cmd ps | grep -q "$service.*Up"; then
        success "$service service healthy"
    else
        error "$service service not healthy"
        compose_cmd ps
        exit 1
    fi
done

# ========================================
# Phase 5: API Health Check
# ========================================

log "Phase 5: Checking API endpoints"

sleep 5

# Check brain API
if curl -s http://localhost:8000/health > /dev/null; then
    success "Brain API responding"
else
    warn "Brain API not responding (may still be initializing)"
fi

# Check metrics endpoint
if curl -s http://localhost:8000/metrics | grep -q "brain_"; then
    success "Prometheus metrics available"
else
    warn "Prometheus metrics not yet available"
fi

# ========================================
# Phase 6: Images Service
# ========================================

log "Phase 6: Ensuring images service is running"

if ! start_images_service; then
    error "Failed to start images service"
    exit 1
fi

# ========================================
# Phase 7: Voice Service
# ========================================

log "Phase 7: Starting voice service"

VOICE_SERVICE_LOG="$LOG_DIR/voice-service.log"
VOICE_PORT="${VOICE_PORT:-8400}"

is_voice_service_running() {
    curl -sf "http://localhost:${VOICE_PORT}/healthz" >/dev/null 2>&1
}

if is_voice_service_running; then
    success "Voice service already running"
else
    if "$SCRIPT_DIR/start-voice-service.sh" >> "$VOICE_SERVICE_LOG" 2>&1; then
        # Wait for voice service to become healthy
        MAX_WAIT=30
        ELAPSED=0
        while [ $ELAPSED -lt $MAX_WAIT ]; do
            if is_voice_service_running; then
                success "Voice service running"
                break
            fi
            sleep 2
            ELAPSED=$((ELAPSED + 2))
        done

        if [ $ELAPSED -ge $MAX_WAIT ]; then
            warn "Voice service health check timed out (check $VOICE_SERVICE_LOG)"
        fi
    else
        warn "Voice service startup failed (check $VOICE_SERVICE_LOG)"
    fi
fi

# ========================================
# Startup Summary
# ========================================

echo ""
echo "=========================================="
echo " KITTY Stack Started Successfully"
echo "=========================================="
echo ""
echo "Services:"
echo "  llama.cpp Q4:  http://localhost:8083"
echo "  llama.cpp F16: http://localhost:8082"
echo "  Brain API:     http://localhost:8000"
echo "  Gateway (LB):  http://localhost:8080  (3 replicas + HAProxy)"
echo "  HAProxy Stats: http://localhost:8404/stats  (admin/changeme)"
echo "  Voice Service: http://localhost:8400"
echo "  UI:            http://localhost:4173"
echo "  Research UI:   http://localhost:8080/research  (P1 #2)"
echo "  I/O Control:   http://localhost:8080/io-control  (P1 #3)"
echo "  Grafana:       http://localhost:3000"
echo "  Prometheus:    http://localhost:9090"
echo "  RabbitMQ:      http://localhost:15672/rabbitmq/  (kitty/changeme)"
echo ""
echo "P0/P1 Features:"
echo "  ✅ Conversation state persistence (P0 #1)"
echo "  ✅ Autonomous job persistence (P0 #2)"
echo "  ✅ Semantic cache TTL (P0 #3)"
echo "  ✅ Research graph wiring (P0 #4)"
echo "  ✅ Database writes awaited (P0 #5)"
echo "  ✅ Distributed locking (P1 #1)"
echo "  ✅ Research Web UI (P1 #2)"
echo "  ✅ I/O Control Dashboard (P1 #3)"
echo "  ✅ Gateway Load Balancer (P1 #4)"
echo "  ✅ CAD AI Cycling Docs (P1 #5)"
echo ""
echo "P2 Features:"
echo "  ✅ Material Inventory Dashboard (P2 #11)"
echo "  ✅ Print Intelligence Dashboard (P2 #12)"
echo "  ✅ Vision Service Dashboard (P2 #13)"
echo "  ✅ Database Clustering Ready (P2 #14)"
echo "  ✅ RabbitMQ Message Queue (P2 #15) - http://localhost:15672/rabbitmq/"
echo ""
echo "Logs:"
echo "  Startup:       $STARTUP_LOG"
echo "  llama.cpp:     $LOG_DIR/llamacpp-*.log"
echo "  Docker:        docker compose logs -f"
echo ""
echo "Monitoring:"
echo "  ./ops/scripts/monitor/inference.sh 5"
echo ""
echo "To stop:"
echo "  ./ops/scripts/stop-all.sh"
echo ""
echo "=========================================="
echo ""

# Keep running if interactive, exit if scripted
if [ -t 0 ]; then
    log "Press Ctrl+C to stop all services"
    # Wait indefinitely
    while true; do
        sleep 3600
    done
else
    success "Startup complete (detached mode)"
fi
