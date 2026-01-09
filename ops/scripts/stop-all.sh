#!/bin/bash
# Stop all KITTY services
# Gracefully stops Docker services, llama.cpp servers, and Ollama (if running)

set -e

# ========================================
# Configuration
# ========================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
COMPOSE_DIR="$PROJECT_ROOT/infra/compose"
cd "$PROJECT_ROOT"

# Docker compose helper (always run from infra/compose)
# Includes message queue (P2 #15) for proper shutdown
compose_cmd() {
    (cd "$COMPOSE_DIR" && docker compose -f docker-compose.yml -f docker-compose.message-queue.yml "$@")
}

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() {
    echo -e "${BLUE}[$(date '+%H:%M:%S')]${NC} $1"
}

success() {
    echo -e "${GREEN}✓${NC} $1"
}

error() {
    echo -e "${RED}✗${NC} $1"
}

warn() {
    echo -e "${YELLOW}⚠${NC} $1"
}

# ========================================
# Phase 1: Stop Images Service
# ========================================

log "Phase 1: Stopping images service"
if "$SCRIPT_DIR/stop-images-service.sh" >/dev/null 2>&1; then
    success "Images service stopped"
else
    warn "Images service stop script reported an issue (check logs)"
fi

# ========================================
# Phase 1.5: Stop Voice Service
# ========================================

log "Phase 1.5: Stopping voice service"
if "$SCRIPT_DIR/stop-voice-service.sh" >/dev/null 2>&1; then
    success "Voice service stopped"
else
    warn "Voice service stop script reported an issue (check logs)"
fi

# ========================================
# Phase 1.6: Stop HexStrike
# ========================================

log "Phase 1.6: Stopping HexStrike (if running)"
if [ -x "$SCRIPT_DIR/stop-hexstrike.sh" ]; then
    if "$SCRIPT_DIR/stop-hexstrike.sh" >/dev/null 2>&1; then
        success "HexStrike stopped"
    else
        warn "HexStrike stop script reported an issue (may not have been running)"
    fi
fi

# ========================================
# Phase 2: Stop Docker Services
# ========================================

log "Phase 2: Stopping Docker Compose services"

if compose_cmd ps > /dev/null 2>&1; then
    compose_cmd down
    success "Docker services stopped"
else
    log "No Docker services running"
fi

# ========================================
# Phase 3: Stop llama.cpp Servers
# ========================================

log "Phase 3: Stopping llama.cpp servers"

if ! "$SCRIPT_DIR/llama/stop.sh"; then
    error "Failed to stop llama.cpp servers gracefully"
    error "You may need to manually kill processes"
else
    success "llama.cpp servers stopped"
fi

# ========================================
# Phase 4: Stop Ollama (GPT-OSS reasoner)
# ========================================

log "Phase 4: Stopping Ollama server (if running)"

if [ -x "$SCRIPT_DIR/ollama/stop.sh" ]; then
    if "$SCRIPT_DIR/ollama/stop.sh"; then
        success "Ollama server stopped"
    else
        warn "Ollama stop script reported an issue (check logs)"
    fi
else
    log "Ollama stop script not found, skipping"
fi

# ========================================
# Summary
# ========================================

echo ""
echo "=========================================="
echo " All KITTY Services Stopped"
echo "=========================================="
echo ""

# Verify nothing running
REMAINING_PROCESSES=$(ps aux | grep -E "llama-server|docker" | grep -v grep | wc -l)

# Check for running Ollama models (daemon may remain up)
OLLAMA_RUNNING_MODELS=""
if command -v ollama >/dev/null 2>&1; then
    OLLAMA_RUNNING_MODELS=$(ollama ps 2>/dev/null | awk 'NR>1 && $1!="" {print $1}' | paste -sd " " -)
fi

if [ "$REMAINING_PROCESSES" -gt 0 ] || [ -n "$OLLAMA_RUNNING_MODELS" ]; then
    error "Warning: services may still be running"
    [ "$REMAINING_PROCESSES" -gt 0 ] && echo "Run: ps aux | grep -E 'llama-server|docker'"
    [ -n "$OLLAMA_RUNNING_MODELS" ] && echo "Ollama models still running: $OLLAMA_RUNNING_MODELS (run: ollama stop <model>)"
else
    success "All processes terminated cleanly"
fi

echo ""
