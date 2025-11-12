#!/bin/bash
# Smoke test for Collective Meta-Agent integration
# Run this on the workstation after deployment

set -e

GATEWAY_BASE="${GATEWAY_BASE:-http://localhost:8080}"
BRAIN_BASE="${BRAIN_BASE:-http://localhost:8000}"

echo "========================================="
echo "Collective Meta-Agent Smoke Test"
echo "========================================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test counter
PASSED=0
FAILED=0

# Test function for GET requests
test_get() {
    local name="$1"
    local url="$2"
    local expected_status="${3:-200}"

    echo -n "Testing: $name... "

    response=$(curl -s -w "\n%{http_code}" "$url" --max-time 30)

    http_code=$(echo "$response" | tail -n 1)
    body=$(echo "$response" | sed '$d')

    if [ "$http_code" = "$expected_status" ]; then
        echo -e "${GREEN}PASS${NC} (HTTP $http_code)"
        ((PASSED++))
        return 0
    else
        echo -e "${RED}FAIL${NC} (HTTP $http_code, expected $expected_status)"
        echo "Response: $body"
        ((FAILED++))
        return 1
    fi
}

# Test function for POST requests
test_endpoint() {
    local name="$1"
    local url="$2"
    local payload="$3"
    local expected_status="${4:-200}"

    echo -n "Testing: $name... "

    response=$(curl -s -w "\n%{http_code}" -X POST "$url" \
        -H 'Content-Type: application/json' \
        -d "$payload" \
        --max-time 300)

    http_code=$(echo "$response" | tail -n 1)
    body=$(echo "$response" | sed '$d')

    if [ "$http_code" = "$expected_status" ]; then
        echo -e "${GREEN}PASS${NC} (HTTP $http_code)"
        ((PASSED++))
        return 0
    else
        echo -e "${RED}FAIL${NC} (HTTP $http_code, expected $expected_status)"
        echo "Response: $body"
        ((FAILED++))
        return 1
    fi
}

# Test health endpoints
echo -e "${YELLOW}1. Health Checks${NC}"
test_get "Brain Health" "$BRAIN_BASE/health" 200
echo ""

# Test council pattern (minimal)
echo -e "${YELLOW}2. Council Pattern (k=2)${NC}"
test_endpoint "Council k=2" "$GATEWAY_BASE/api/collective/run" \
    '{"task":"Quick test: PETG or PLA for outdoor use?","pattern":"council","k":2}' 200
echo ""

# Test debate pattern
echo -e "${YELLOW}3. Debate Pattern${NC}"
test_endpoint "Debate" "$GATEWAY_BASE/api/collective/run" \
    '{"task":"Should I use tree supports for overhangs?","pattern":"debate"}' 200
echo ""

# Test validation errors
echo -e "${YELLOW}4. Validation Tests${NC}"
test_endpoint "Invalid pattern" "$GATEWAY_BASE/api/collective/run" \
    '{"task":"Test","pattern":"invalid","k":3}' 422

test_endpoint "k too low" "$GATEWAY_BASE/api/collective/run" \
    '{"task":"Test","pattern":"council","k":1}' 422

test_endpoint "k too high" "$GATEWAY_BASE/api/collective/run" \
    '{"task":"Test","pattern":"council","k":10}' 422

test_endpoint "Missing task" "$GATEWAY_BASE/api/collective/run" \
    '{"pattern":"council","k":3}' 422
echo ""

# Optional: Test brain direct endpoint
echo -e "${YELLOW}5. Direct Brain API${NC}"
test_endpoint "Brain Direct" "$BRAIN_BASE/api/collective/run" \
    '{"task":"Test direct brain access","pattern":"council","k":2}' 200
echo ""

# Optional: Detailed council test (commented out - takes 1-2 minutes)
# echo -e "${YELLOW}6. Detailed Council (k=3)${NC}"
# test_endpoint "Council k=3 detailed" "$GATEWAY_BASE/api/collective/run" \
#     '{"task":"Compare PETG vs ABS vs ASA for outdoor furniture. Consider UV resistance, temperature range, and ease of printing.","pattern":"council","k":3}' 200
# echo ""

# Summary
echo "========================================="
echo -e "Test Summary: ${GREEN}$PASSED passed${NC}, ${RED}$FAILED failed${NC}"
echo "========================================="

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}All tests passed! ✓${NC}"
    exit 0
else
    echo -e "${RED}Some tests failed! ✗${NC}"
    exit 1
fi
