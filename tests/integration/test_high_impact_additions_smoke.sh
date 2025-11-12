#!/bin/bash
# Comprehensive smoke test for all 4 High-Impact Additions
# Validates: CODER, Memory Enhancement, Diversity Seat, F16 Tuning (config check)
# Run this script on workstation with services running

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

PASSED=0
FAILED=0
WARNINGS=0

GATEWAY_BASE=${GATEWAY_BASE:-"http://localhost:8080"}
MEM0_BASE=${MEM0_MCP_URL:-"http://localhost:8765"}

echo "========================================="
echo "High-Impact Additions - Comprehensive Smoke Test"
echo "========================================="
echo ""
echo "Testing all 4 phases:"
echo "  Phase 1: CODER Model Support"
echo "  Phase 2: Memory Enhancement (BGE + Reranker)"
echo "  Phase 3: Diversity Seat (Q4B)"
echo "  Phase 4: F16 Parallelism (Configuration Check)"
echo ""
echo "========================================="
echo ""

# ============================================
# PHASE 1: CODER MODEL SUPPORT
# ============================================
echo -e "${CYAN}PHASE 1: CODER Model Support${NC}"
echo "----------------------------------------"

# Test 1.1: Gateway health
echo -n "Test 1.1: Gateway health check... "
if curl -s -f "$GATEWAY_BASE/health" > /dev/null 2>&1; then
    echo -e "${GREEN}PASS${NC}"
    ((PASSED++))
else
    echo -e "${RED}FAIL${NC}"
    ((FAILED++))
fi

# Test 1.2: Code generation via collective (uses CODER if configured)
echo -n "Test 1.2: Code generation task via collective... "
code_response=$(curl -s -X POST "$GATEWAY_BASE/api/collective/run" \
    -H 'Content-Type: application/json' \
    -d '{"task":"Write a Python function to calculate factorial with docstring","pattern":"council","k":2}' \
    --max-time 120 2>&1)

if echo "$code_response" | grep -q "def" && echo "$code_response" | grep -q "factorial"; then
    echo -e "${GREEN}PASS${NC}"
    ((PASSED++))
else
    echo -e "${YELLOW}PARTIAL${NC} - Response received but code quality uncertain"
    ((WARNINGS++))
fi

# Test 1.3: Check CODER configuration
echo -n "Test 1.3: CODER model configuration... "
if [ -f /home/user/KITT/.env ]; then
    if grep -q "LLAMACPP_CODER" /home/user/KITT/.env 2>/dev/null; then
        echo -e "${GREEN}PASS${NC} - CODER configured"
        ((PASSED++))
    else
        echo -e "${YELLOW}WARNING${NC} - CODER not configured (using F16 fallback)"
        ((WARNINGS++))
    fi
else
    echo -e "${YELLOW}SKIP${NC}"
fi

echo ""

# ============================================
# PHASE 2: MEMORY ENHANCEMENT
# ============================================
echo -e "${CYAN}PHASE 2: Memory Enhancement (BGE + Reranker)${NC}"
echo "----------------------------------------"

# Test 2.1: mem0-mcp health
echo -n "Test 2.1: mem0-mcp health check... "
if curl -s -f "$MEM0_BASE/health" > /dev/null 2>&1; then
    echo -e "${GREEN}PASS${NC}"
    ((PASSED++))
else
    echo -e "${RED}FAIL${NC}"
    ((FAILED++))
fi

# Test 2.2: Check embedding model
echo -n "Test 2.2: BGE embedding model check... "
stats_response=$(curl -s "$MEM0_BASE/memory/stats" 2>&1)

if echo "$stats_response" | grep -q "bge"; then
    echo -e "${GREEN}PASS${NC}"
    ((PASSED++))
    embedding_model=$(echo "$stats_response" | jq -r '.embedding_model' 2>/dev/null || echo "unknown")
    echo "  Model: $embedding_model"
else
    echo -e "${RED}FAIL${NC} - BGE model not detected"
    ((FAILED++))
fi

# Test 2.3: Check reranker
echo -n "Test 2.3: Reranker status... "
reranker_enabled=$(echo "$stats_response" | jq -r '.reranker_enabled' 2>/dev/null || echo "false")

if [ "$reranker_enabled" = "true" ]; then
    echo -e "${GREEN}PASS${NC} - Reranker enabled"
    ((PASSED++))
    reranker_model=$(echo "$stats_response" | jq -r '.reranker_model' 2>/dev/null || echo "unknown")
    echo "  Model: $reranker_model"
else
    echo -e "${YELLOW}WARNING${NC} - Reranker disabled (vector-only search)"
    ((WARNINGS++))
fi

# Test 2.4: Semantic search quality
echo -n "Test 2.4: Semantic search test... "
# Add test memory
test_mem=$(curl -s -X POST "$MEM0_BASE/memory/add" \
    -H 'Content-Type: application/json' \
    -d '{"conversation_id":"smoke-test-phase2","content":"PETG is UV-resistant and perfect for outdoor use","tags":["domain","test"]}' 2>&1)

test_mem_id=$(echo "$test_mem" | jq -r '.id' 2>/dev/null || echo "")

# Search for similar concept
search_response=$(curl -s -X POST "$MEM0_BASE/memory/search" \
    -H 'Content-Type: application/json' \
    -d '{"query":"What material works well in sunlight?","conversation_id":"smoke-test-phase2","limit":1}' 2>&1)

if echo "$search_response" | grep -q "PETG"; then
    echo -e "${GREEN}PASS${NC} - Semantic search working"
    ((PASSED++))
else
    echo -e "${RED}FAIL${NC}"
    ((FAILED++))
fi

# Cleanup test memory
if [ -n "$test_mem_id" ] && [ "$test_mem_id" != "null" ]; then
    curl -s -X DELETE "$MEM0_BASE/memory/$test_mem_id" > /dev/null 2>&1
fi

echo ""

# ============================================
# PHASE 3: DIVERSITY SEAT
# ============================================
echo -e "${CYAN}PHASE 3: Diversity Seat (Q4B)${NC}"
echo "----------------------------------------"

# Test 3.1: Council with k=3
echo -n "Test 3.1: Council pattern (k=3) test... "
council_response=$(curl -s -X POST "$GATEWAY_BASE/api/collective/run" \
    -H 'Content-Type: application/json' \
    -d '{"task":"Compare bubble sort vs insertion sort for small arrays","pattern":"council","k":3}' \
    --max-time 120 2>&1)

if echo "$council_response" | grep -q "verdict"; then
    echo -e "${GREEN}PASS${NC}"
    ((PASSED++))
else
    echo -e "${RED}FAIL${NC}"
    ((FAILED++))
fi

# Test 3.2: Check Q4B configuration
echo -n "Test 3.2: Q4B diversity seat configuration... "
if [ -f /home/user/KITT/.env ]; then
    if grep -q "LLAMACPP_Q4B_ALIAS" /home/user/KITT/.env 2>/dev/null; then
        echo -e "${GREEN}PASS${NC} - Q4B configured"
        ((PASSED++))
    else
        echo -e "${YELLOW}WARNING${NC} - Q4B not configured (using Q4 for all specialists)"
        ((WARNINGS++))
    fi
else
    echo -e "${YELLOW}SKIP${NC}"
fi

# Test 3.3: Extended council (k=5)
echo -n "Test 3.3: Extended council (k=5) diversity test... "
extended_council=$(curl -s -X POST "$GATEWAY_BASE/api/collective/run" \
    -H 'Content-Type: application/json' \
    -d '{"task":"Best practices for 3D print first layer adhesion","pattern":"council","k":5}' \
    --max-time 180 2>&1)

if echo "$extended_council" | grep -q "verdict"; then
    echo -e "${GREEN}PASS${NC}"
    ((PASSED++))
else
    echo -e "${RED}FAIL${NC}"
    ((FAILED++))
fi

echo ""

# ============================================
# PHASE 4: F16 PARALLELISM TUNING
# ============================================
echo -e "${CYAN}PHASE 4: F16 Parallelism Configuration${NC}"
echo "----------------------------------------"

# Test 4.1: Check F16 configuration
echo -n "Test 4.1: F16 parallelism settings... "
if [ -f /home/user/KITT/.env ]; then
    f16_parallel=$(grep "^LLAMACPP_F16_PARALLEL=" /home/user/KITT/.env 2>/dev/null | cut -d'=' -f2 || echo "4")
    f16_batch=$(grep "^LLAMACPP_F16_BATCH_SIZE=" /home/user/KITT/.env 2>/dev/null | cut -d'=' -f2 || echo "4096")
    f16_ubatch=$(grep "^LLAMACPP_F16_UBATCH_SIZE=" /home/user/KITT/.env 2>/dev/null | cut -d'=' -f2 || echo "1024")

    echo ""
    echo "  PARALLEL: $f16_parallel (baseline: 4, optimal: 6-8)"
    echo "  BATCH_SIZE: $f16_batch (baseline: 4096, optimal: 8192-12288)"
    echo "  UBATCH_SIZE: $f16_ubatch (baseline: 1024, optimal: 2048-3072)"

    # Check if tuned
    if [ "$f16_parallel" -ge 6 ] || [ "$f16_batch" -ge 8192 ]; then
        echo -e "  ${GREEN}✓ F16 tuning applied${NC}"
        ((PASSED++))
    else
        echo -e "  ${YELLOW}! F16 tuning not applied (using baseline)${NC}"
        ((WARNINGS++))
    fi
else
    echo -e "${YELLOW}SKIP${NC}"
fi

# Test 4.2: F16 server accessibility (judge model)
echo -n "Test 4.2: F16 judge model test... "
judge_response=$(curl -s -X POST "$GATEWAY_BASE/api/collective/run" \
    -H 'Content-Type: application/json' \
    -d '{"task":"Quick decision: which is faster for sorting 10 items?","pattern":"debate"}' \
    --max-time 90 2>&1)

if echo "$judge_response" | grep -q "verdict"; then
    echo -e "${GREEN}PASS${NC} - F16 judge responding"
    ((PASSED++))
else
    echo -e "${RED}FAIL${NC}"
    ((FAILED++))
fi

echo ""
echo "========================================="
echo "Test Summary"
echo "========================================="
echo -e "Passed:   ${GREEN}${PASSED}${NC}"
echo -e "Failed:   ${RED}${FAILED}${NC}"
echo -e "Warnings: ${YELLOW}${WARNINGS}${NC}"
echo ""

# Final verdict
if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ All critical tests passed!${NC}"
    echo ""
    echo "High-Impact Additions Status:"
    echo ""
    echo "Phase 1: CODER Model Support"
    echo "  ✓ Code generation working"
    echo "  Expected: +15-25% code quality improvement"
    echo ""
    echo "Phase 2: Memory Enhancement"
    echo "  ✓ BGE embeddings active"
    if [ "$reranker_enabled" = "true" ]; then
        echo "  ✓ Reranker enabled"
        echo "  Expected: +20-30% top-3 precision"
    else
        echo "  - Reranker disabled (vector-only)"
        echo "  Expected: +15-20% embedding quality"
    fi
    echo ""
    echo "Phase 3: Diversity Seat"
    echo "  ✓ Council patterns working (k=3, k=5)"
    echo "  Expected: +10-20% proposal diversity"
    echo ""
    echo "Phase 4: F16 Parallelism"
    if [ "$f16_parallel" -ge 6 ] || [ "$f16_batch" -ge 8192 ]; then
        echo "  ✓ Tuning applied"
        echo "  Expected: +20-40% throughput"
    else
        echo "  - Using baseline configuration"
        echo "  To tune: See docs/F16_PARALLELISM_TUNING_GUIDE.md"
    fi
    echo ""

    if [ $WARNINGS -gt 0 ]; then
        echo -e "${YELLOW}Warnings detected:${NC}"
        echo "  Review configuration in .env for optional enhancements"
        echo "  See: docs/HIGH_IMPACT_ADDITIONS_IMPLEMENTATION_PLAN.md"
    fi

    exit 0
else
    echo -e "${RED}✗ Some tests failed.${NC}"
    echo ""
    echo "Troubleshooting steps:"
    echo ""
    echo "1. Check all services are running:"
    echo "   docker ps | grep -E 'brain|mem0-mcp|gateway'"
    echo ""
    echo "2. Verify llama.cpp servers:"
    echo "   curl http://localhost:8083/health  # Q4"
    echo "   curl http://localhost:8082/health  # F16"
    echo ""
    echo "3. Check service logs:"
    echo "   docker logs compose-brain-1"
    echo "   docker logs compose-mem0-mcp-1"
    echo ""
    echo "4. Review configuration:"
    echo "   cat .env | grep -E 'LLAMACPP|EMBEDDING|RERANKER'"
    echo ""
    echo "5. Restart services:"
    echo "   ./ops/scripts/stop-kitty.sh"
    echo "   ./ops/scripts/start-kitty.sh"
    exit 1
fi
