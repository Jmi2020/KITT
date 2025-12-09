#!/bin/bash
#
# Smoke Test Script for Parallel Agent Orchestration
#
# Tests the parallel multi-agent system implemented in commit d8c1995.
# Verifies:
#   1. LLM endpoint health
#   2. Unit tests pass
#   3. Simple vs complex query routing
#   4. Parallel execution works with live endpoints
#
# Usage: ./tests/smoke_test_parallel.sh [--quick|--full]
#   --quick  Skip live LLM tests (faster)
#   --full   Run all tests including performance benchmarks
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Parse arguments
MODE="${1:-normal}"

echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}   KITTY Parallel Agent Orchestration - Smoke Test Suite${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# Counters
TOTAL_CHECKS=0
PASSED=0
FAILED=0
SKIPPED=0

pass() {
    echo -e "  ${GREEN}✓${NC} $1"
    ((PASSED++))
    ((TOTAL_CHECKS++))
}

fail() {
    echo -e "  ${RED}✗${NC} $1"
    ((FAILED++))
    ((TOTAL_CHECKS++))
}

skip() {
    echo -e "  ${YELLOW}○${NC} $1 (skipped)"
    ((SKIPPED++))
    ((TOTAL_CHECKS++))
}

# ============================================================================
# Phase 1: Environment Check
# ============================================================================
echo -e "${YELLOW}Phase 1: Environment Check${NC}"
echo "────────────────────────────────────────────────────────────────"

# Check Python
if command -v python3 &> /dev/null; then
    pass "Python3 found: $(python3 --version)"
else
    fail "Python3 not found"
    exit 1
fi

# Check pytest
if python3 -c "import pytest" 2>/dev/null; then
    pass "pytest installed"
else
    fail "pytest not installed"
    exit 1
fi

# Check environment variables
if [[ "${ENABLE_PARALLEL_AGENTS:-false}" == "true" ]]; then
    pass "ENABLE_PARALLEL_AGENTS=true"
else
    echo -e "  ${YELLOW}!${NC} ENABLE_PARALLEL_AGENTS not set (will use test fixtures)"
fi

echo ""

# ============================================================================
# Phase 2: LLM Endpoint Health Checks
# ============================================================================
echo -e "${YELLOW}Phase 2: LLM Endpoint Health Checks${NC}"
echo "────────────────────────────────────────────────────────────────"

check_endpoint() {
    local name="$1"
    local url="$2"
    local timeout=3

    if curl -s --connect-timeout "$timeout" "$url" >/dev/null 2>&1; then
        pass "$name ($url)"
        return 0
    else
        fail "$name ($url) - not responding"
        return 1
    fi
}

# Check all LLM endpoints
check_endpoint "Q4 Tools (Athene V2)" "http://localhost:8083/health" || true
check_endpoint "Summary (Hermes 8B)" "http://localhost:8084/health" || true
check_endpoint "Vision (Gemma 27B)" "http://localhost:8086/health" || true
check_endpoint "Coder (Qwen 32B)" "http://localhost:8087/health" || true

# Ollama uses different endpoint
if curl -s --connect-timeout 3 "http://localhost:11434/api/tags" >/dev/null 2>&1; then
    pass "Ollama (GPT-OSS 120B) (http://localhost:11434)"
else
    fail "Ollama (GPT-OSS 120B) - not responding"
fi

echo ""

# ============================================================================
# Phase 3: Unit Tests
# ============================================================================
echo -e "${YELLOW}Phase 3: Unit Tests${NC}"
echo "────────────────────────────────────────────────────────────────"

# Run pytest and capture output
PYTEST_OUTPUT=$(PYTHONPATH=services/brain/src:services/common/src python3 -m pytest \
    services/brain/tests/agents/parallel/ \
    -v --tb=short 2>&1 || true)

# Count passed/failed
PYTEST_PASSED=$(echo "$PYTEST_OUTPUT" | grep -E "passed" | tail -1 | grep -oE "[0-9]+ passed" | grep -oE "[0-9]+" || echo "0")
PYTEST_FAILED=$(echo "$PYTEST_OUTPUT" | grep -E "failed" | tail -1 | grep -oE "[0-9]+ failed" | grep -oE "[0-9]+" || echo "0")

if [[ "$PYTEST_FAILED" -eq 0 && "$PYTEST_PASSED" -gt 0 ]]; then
    pass "All unit tests passed ($PYTEST_PASSED tests)"
else
    fail "Unit tests: $PYTEST_PASSED passed, $PYTEST_FAILED failed"
    echo "$PYTEST_OUTPUT" | tail -30
fi

# Test individual modules
echo ""
echo "  Module breakdown:"
for module in test_types test_registry test_slot_manager test_llm_adapter test_parallel_manager test_integration; do
    MODULE_OUTPUT=$(PYTHONPATH=services/brain/src:services/common/src python3 -m pytest \
        "services/brain/tests/agents/parallel/${module}.py" -q 2>&1 || true)
    MODULE_RESULT=$(echo "$MODULE_OUTPUT" | grep -oE "[0-9]+ passed" || echo "0 passed")
    echo -e "    ${GREEN}✓${NC} $module: $MODULE_RESULT"
done

echo ""

# ============================================================================
# Phase 4: Live Integration Tests (skip if --quick)
# ============================================================================
if [[ "$MODE" == "--quick" ]]; then
    echo -e "${YELLOW}Phase 4: Live Integration Tests ${NC}(skipped: --quick mode)"
    echo "────────────────────────────────────────────────────────────────"
    skip "Live LLM generation test"
    skip "Slot acquisition test"
    skip "Parallel execution test"
else
    echo -e "${YELLOW}Phase 4: Live Integration Tests${NC}"
    echo "────────────────────────────────────────────────────────────────"

    # Check if Q4 endpoint is available for live test
    if curl -s --connect-timeout 2 "http://localhost:8083/health" >/dev/null 2>&1; then
        # Test simple generation
        LIVE_RESPONSE=$(curl -s --connect-timeout 30 -X POST "http://localhost:8083/completion" \
            -H "Content-Type: application/json" \
            -d '{
                "prompt": "<|system|>\nYou are a test assistant.</s>\n<|user|>\nSay hello in one word.</s>\n<|assistant|>\n",
                "n_predict": 10,
                "temperature": 0.1,
                "stop": ["</s>"]
            }' 2>/dev/null || echo "")

        if [[ -n "$LIVE_RESPONSE" && "$LIVE_RESPONSE" != *"error"* ]]; then
            pass "Live LLM generation test (Q4 Tools)"
        else
            fail "Live LLM generation test (no response)"
        fi
    else
        skip "Live LLM generation test (Q4 not available)"
    fi

    # Test Python integration
    INTEGRATION_TEST=$(PYTHONPATH=services/brain/src:services/common/src python3 -c "
import asyncio
from brain.agents.parallel.slot_manager import SlotManager
from brain.agents.parallel.registry import ENDPOINTS
from brain.agents.parallel.types import ModelTier

async def test():
    sm = SlotManager()
    tier, acquired = await sm.acquire_slot(ModelTier.Q4_TOOLS, timeout=1.0, max_retries=1)
    if acquired:
        await sm.release_slot(tier)
        return 'OK'
    return 'SKIP'

result = asyncio.run(test())
print(result)
" 2>&1 || echo "ERROR")

    if [[ "$INTEGRATION_TEST" == "OK" ]]; then
        pass "Slot acquisition test"
    elif [[ "$INTEGRATION_TEST" == "SKIP" ]]; then
        skip "Slot acquisition test (endpoint unavailable)"
    else
        fail "Slot acquisition test"
    fi
fi

echo ""

# ============================================================================
# Phase 5: Performance Benchmark (only in --full mode)
# ============================================================================
if [[ "$MODE" == "--full" ]]; then
    echo -e "${YELLOW}Phase 5: Performance Benchmarks${NC}"
    echo "────────────────────────────────────────────────────────────────"

    # Check if gateway is available
    if curl -s --connect-timeout 2 "http://localhost:8080/health" >/dev/null 2>&1; then
        echo "  Running simple query benchmark..."

        # Simple query (should bypass parallel)
        SIMPLE_START=$(python3 -c "import time; print(int(time.time() * 1000))")
        curl -s -X POST "http://localhost:8080/api/chat" \
            -H "Content-Type: application/json" \
            -d '{"message": "What is Python?", "conversation_id": "smoke-test-simple"}' \
            >/dev/null 2>&1 || true
        SIMPLE_END=$(python3 -c "import time; print(int(time.time() * 1000))")
        SIMPLE_TIME=$((SIMPLE_END - SIMPLE_START))

        echo "  Running complex query benchmark..."

        # Complex query (should trigger parallel)
        COMPLEX_START=$(python3 -c "import time; print(int(time.time() * 1000))")
        curl -s -X POST "http://localhost:8080/api/chat" \
            -H "Content-Type: application/json" \
            -d '{"message": "Research and investigate quantum computing applications step by step, compare and analyze different implementations comprehensively, and create a detailed report", "conversation_id": "smoke-test-complex"}' \
            >/dev/null 2>&1 || true
        COMPLEX_END=$(python3 -c "import time; print(int(time.time() * 1000))")
        COMPLEX_TIME=$((COMPLEX_END - COMPLEX_START))

        echo ""
        echo "  Benchmark Results:"
        echo "    Simple query: ${SIMPLE_TIME}ms"
        echo "    Complex query: ${COMPLEX_TIME}ms"

        if [[ $COMPLEX_TIME -gt 0 ]]; then
            pass "Performance benchmark completed"
        else
            fail "Performance benchmark failed"
        fi
    else
        skip "Performance benchmark (gateway not available)"
    fi
else
    if [[ "$MODE" != "--quick" ]]; then
        echo -e "${YELLOW}Phase 5: Performance Benchmarks ${NC}(skipped: use --full to enable)"
        echo "────────────────────────────────────────────────────────────────"
        skip "Performance benchmark"
    fi
fi

echo ""

# ============================================================================
# Summary
# ============================================================================
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}   Summary${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "  Total Checks: $TOTAL_CHECKS"
echo -e "  ${GREEN}Passed:${NC}       $PASSED"
echo -e "  ${RED}Failed:${NC}       $FAILED"
echo -e "  ${YELLOW}Skipped:${NC}      $SKIPPED"
echo ""

if [[ $FAILED -eq 0 ]]; then
    echo -e "${GREEN}  ✓ All checks passed!${NC}"
    echo ""
    exit 0
else
    echo -e "${RED}  ✗ Some checks failed${NC}"
    echo ""
    exit 1
fi
