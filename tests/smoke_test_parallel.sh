#!/bin/bash
#
# Smoke Test Script for Parallel Agent Orchestration
#
# Tests the parallel multi-agent system implemented in commit d8c1995.
# Usage: ./tests/smoke_test_parallel.sh [--quick|--full]
#

# Don't use set -e as it causes issues with test functions
# set -e

# Parse arguments
MODE="${1:-normal}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# Counters
TOTAL=0
PASSED=0
FAILED=0
SKIPPED=0

pass() { echo "[PASS] $1"; ((PASSED++)); ((TOTAL++)); }
fail() { echo "[FAIL] $1"; ((FAILED++)); ((TOTAL++)); }
skip() { echo "[SKIP] $1"; ((SKIPPED++)); ((TOTAL++)); }

echo "==================================================================="
echo "   KITTY Parallel Agent Orchestration - Smoke Test Suite"
echo "==================================================================="
echo ""

# ============================================================================
# Phase 1: Environment Check
# ============================================================================
echo "Phase 1: Environment Check"
echo "-------------------------------------------------------------------"

if command -v python3 &>/dev/null; then
    pass "Python3: $(python3 --version 2>&1)"
else
    fail "Python3 not found"
    exit 1
fi

if python3 -m pip show pytest &>/dev/null; then
    pass "pytest installed"
else
    fail "pytest not found"
    exit 1
fi

if [[ "${ENABLE_PARALLEL_AGENTS:-false}" == "true" ]]; then
    pass "ENABLE_PARALLEL_AGENTS=true"
else
    echo "[INFO] ENABLE_PARALLEL_AGENTS not set (using test fixtures)"
fi
echo ""

# ============================================================================
# Phase 2: LLM Endpoint Health Checks
# ============================================================================
echo "Phase 2: LLM Endpoint Health Checks"
echo "-------------------------------------------------------------------"

check_endpoint() {
    if curl -s --connect-timeout 3 "$2" &>/dev/null; then
        pass "$1"
    else
        fail "$1 - not responding"
    fi
}

check_endpoint "Q4 Tools (8083)" "http://localhost:8083/health"
check_endpoint "Summary (8084)" "http://localhost:8084/health"
check_endpoint "Vision (8086)" "http://localhost:8086/health"
check_endpoint "Coder (8087)" "http://localhost:8087/health"
check_endpoint "Ollama (11434)" "http://localhost:11434/api/tags"
echo ""

# ============================================================================
# Phase 3: Unit Tests
# ============================================================================
echo "Phase 3: Unit Tests"
echo "-------------------------------------------------------------------"

TEST_OUTPUT=$(PYTHONPATH=services/brain/src:services/common/src python3 -m pytest \
    services/brain/tests/agents/parallel/ -q --tb=no 2>&1) || true

PYTEST_PASSED=$(echo "$TEST_OUTPUT" | grep -oE "[0-9]+ passed" | grep -oE "[0-9]+" || echo "0")
PYTEST_FAILED=$(echo "$TEST_OUTPUT" | grep -oE "[0-9]+ failed" | grep -oE "[0-9]+" || echo "0")

if [[ "$PYTEST_FAILED" -eq 0 && "$PYTEST_PASSED" -gt 0 ]]; then
    pass "Unit tests: $PYTEST_PASSED passed"
else
    fail "Unit tests: $PYTEST_PASSED passed, $PYTEST_FAILED failed"
    echo "$TEST_OUTPUT" | tail -20
fi
echo ""

# ============================================================================
# Phase 4: Live Integration Tests
# ============================================================================
if [[ "$MODE" == "--quick" ]]; then
    echo "Phase 4: Live Integration Tests (skipped in --quick mode)"
    echo "-------------------------------------------------------------------"
    skip "Live LLM generation"
    skip "Slot acquisition"
else
    echo "Phase 4: Live Integration Tests"
    echo "-------------------------------------------------------------------"

    # Test Q4 endpoint
    if curl -s --connect-timeout 2 "http://localhost:8083/health" &>/dev/null; then
        RESPONSE=$(curl -s --connect-timeout 30 -X POST "http://localhost:8083/completion" \
            -H "Content-Type: application/json" \
            -d '{"prompt":"<|system|>\nTest</s>\n<|user|>\nHello</s>\n<|assistant|>\n","n_predict":5,"temperature":0.1,"stop":["</s>"]}' 2>/dev/null || echo "")
        if [[ -n "$RESPONSE" && "$RESPONSE" != *"error"* ]]; then
            pass "Live Q4 generation"
        else
            fail "Live Q4 generation"
        fi
    else
        skip "Live Q4 generation (endpoint down)"
    fi

    # Test slot acquisition
    SLOT_TEST=$(PYTHONPATH=services/brain/src:services/common/src python3 -c "
import asyncio
import warnings
warnings.filterwarnings('ignore')
from brain.agents.parallel.slot_manager import SlotManager
from brain.agents.parallel.types import ModelTier
async def test():
    try:
        sm = SlotManager()
        tier, acquired = await sm.acquire_slot(ModelTier.Q4_TOOLS, timeout=3.0, max_retries=2)
        if acquired:
            await sm.release_slot(tier)
            return 'OK'
        return 'SKIP'
    except Exception:
        return 'ERROR'
print(asyncio.run(test()))
" 2>/dev/null || echo "ERROR")

    case "$SLOT_TEST" in
        *OK*) pass "Slot acquisition" ;;
        *SKIP*) skip "Slot acquisition (endpoint unavailable)" ;;
        *) fail "Slot acquisition" ;;
    esac
fi
echo ""

# ============================================================================
# Summary
# ============================================================================
echo "==================================================================="
echo "   Summary"
echo "==================================================================="
echo ""
echo "  Total:   $TOTAL"
echo "  Passed:  $PASSED"
echo "  Failed:  $FAILED"
echo "  Skipped: $SKIPPED"
echo ""

if [[ $FAILED -eq 0 ]]; then
    echo "All checks passed!"
    exit 0
else
    echo "Some checks failed"
    exit 1
fi
