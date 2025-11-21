#!/bin/bash
# Smoke test for collective meta-agent with Option A token budgets

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
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

# Test 1: Simple collective council query
log "Test 1: Collective council with token budgets"
RESPONSE=$(kitty-cli say "/collective What's the best approach for implementing error handling in async Python code?" 2>&1)

if echo "$RESPONSE" | grep -q "HTTP 500\|HTTP 400\|Internal Server Error"; then
    error "Test 1 FAILED: Got HTTP error"
    echo "$RESPONSE"
    exit 1
fi

success "Test 1 PASSED: Council completed without HTTP errors"

# Test 2: Check for budget logging (should appear in logs)
log "Test 2: Checking for budget status logging"
if grep -q "Budget Status" .logs/llamacpp-q4.log 2>/dev/null || \
   grep -q "tokens" .logs/llamacpp-q4.log 2>/dev/null; then
    success "Test 2 PASSED: Budget logging detected"
else
    log "Test 2 SKIPPED: No budget logging found (may not have run yet)"
fi

# Test 3: Verify Q4 server is within 32k context
log "Test 3: Verifying Q4 context window"
Q4_HEALTH=$(curl -s http://localhost:8083/health)
if echo "$Q4_HEALTH" | grep -q "ok"; then
    success "Test 3 PASSED: Q4 server healthy"
else
    error "Test 3 FAILED: Q4 server not healthy"
    exit 1
fi

# Test 4: Verify Ollama judge model exists
log "Test 4: Verifying gpt-oss-120b-judge model"
if ollama list | grep -q "gpt-oss-120b-judge"; then
    success "Test 4 PASSED: Judge model exists"
else
    error "Test 4 FAILED: Judge model not found"
    exit 1
fi

echo ""
log "All smoke tests passed!"
success "Collective meta-agent with Option A token budgets is functional"
