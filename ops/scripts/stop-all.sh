#!/bin/bash
# Stop all KITTY services
# Gracefully stops Docker services and llama.cpp servers

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

log() {
    echo -e "${BLUE}[$(date '+%H:%M:%S')]${NC} $1"
}

success() {
    echo -e "${GREEN}✓${NC} $1"
}

error() {
    echo -e "${RED}✗${NC} $1"
}

# ========================================
# Phase 1: Stop Docker Services
# ========================================

log "Phase 1: Stopping Docker Compose services"

if docker compose ps > /dev/null 2>&1; then
    docker compose down
    success "Docker services stopped"
else
    log "No Docker services running"
fi

# ========================================
# Phase 2: Stop llama.cpp Servers
# ========================================

log "Phase 2: Stopping llama.cpp servers"

if ! "$SCRIPT_DIR/llama/stop.sh"; then
    error "Failed to stop llama.cpp servers gracefully"
    error "You may need to manually kill processes"
else
    success "llama.cpp servers stopped"
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

if [ "$REMAINING_PROCESSES" -gt 0 ]; then
    error "Warning: $REMAINING_PROCESSES processes may still be running"
    echo "Run: ps aux | grep -E 'llama-server|docker'"
else
    success "All processes terminated cleanly"
fi

echo ""
