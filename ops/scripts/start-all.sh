#!/bin/bash
# Start all KITTY services with validation
# Combines llama.cpp servers + Docker services with health checks

set -e

# ========================================
# Configuration
# ========================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

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
# Phase 1: Start llama.cpp Servers
# ========================================

log "Phase 1: Starting llama.cpp servers"

if ! "$SCRIPT_DIR/llama/start.sh"; then
    error "Failed to start llama.cpp servers"
    exit 1
fi

success "llama.cpp servers started"

# ========================================
# Phase 2: Wait for llama.cpp Health
# ========================================

log "Phase 2: Waiting for llama.cpp servers to be ready"

MAX_WAIT=600  # 10 minutes for model loading
ELAPSED=0
INTERVAL=10

while [ $ELAPSED -lt $MAX_WAIT ]; do
    Q4_HEALTH=$(curl -s http://localhost:8083/health 2>/dev/null | grep -o '"status":"ok"' || echo "")
    F16_HEALTH=$(curl -s http://localhost:8082/health 2>/dev/null | grep -o '"status":"ok"' || echo "")

    if [ -n "$Q4_HEALTH" ] && [ -n "$F16_HEALTH" ]; then
        success "All llama.cpp servers healthy"
        break
    fi

    if [ $((ELAPSED % 30)) -eq 0 ]; then
        log "Still waiting for llama.cpp servers... (${ELAPSED}s elapsed)"
    fi

    sleep $INTERVAL
    ELAPSED=$((ELAPSED + INTERVAL))
done

if [ $ELAPSED -ge $MAX_WAIT ]; then
    error "llama.cpp servers failed to become healthy within ${MAX_WAIT}s"
    error "Check logs: $LOG_DIR/llamacpp-*.log"
    exit 1
fi

# ========================================
# Phase 3: Start Docker Services
# ========================================

log "Phase 3: Starting Docker Compose services"

docker compose up -d --build 2>&1 | tee -a "$STARTUP_LOG"

if [ ${PIPESTATUS[0]} -ne 0 ]; then
    error "Docker Compose startup failed"
    exit 1
fi

success "Docker services started"

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
    docker compose ps
    exit 1
fi

# Check critical services
CRITICAL_SERVICES=("brain" "gateway" "postgres" "redis")
for service in "${CRITICAL_SERVICES[@]}"; do
    if docker compose ps | grep -q "$service.*Up"; then
        success "$service service healthy"
    else
        error "$service service not healthy"
        docker compose ps
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
echo "  Gateway:       http://localhost:8080"
echo "  UI:            http://localhost:4173"
echo "  Grafana:       http://localhost:3000"
echo "  Prometheus:    http://localhost:9090"
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
