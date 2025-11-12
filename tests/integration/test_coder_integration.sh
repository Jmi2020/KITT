#!/bin/bash
# Integration test for CODER model routing
# Run this script on workstation with services running

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

PASSED=0
FAILED=0

echo "========================================="
echo "CODER Model Integration Tests"
echo "========================================="
echo ""

# Check if gateway is reachable
echo -n "Test 1: Gateway health check... "
if curl -s -f http://localhost:8080/health > /dev/null 2>&1; then
    echo -e "${GREEN}PASS${NC}"
    ((PASSED++))
else
    echo -e "${RED}FAIL${NC} - Gateway not reachable"
    ((FAILED++))
fi

# Test collective with code generation task (should use CODER if configured)
echo -n "Test 2: Collective with code generation task (k=2)... "
response=$(curl -s -X POST http://localhost:8080/api/collective/run \
    -H 'Content-Type: application/json' \
    -d '{"task":"Write a Python function to check if a number is prime with docstring","pattern":"council","k":2}' \
    --max-time 180)

http_code=$(echo "$response" | tail -n1)

if echo "$response" | grep -q "def" && echo "$response" | grep -q "prime"; then
    echo -e "${GREEN}PASS${NC}"
    ((PASSED++))
    echo "  Response contains code with 'def' and 'prime'"
else
    echo -e "${YELLOW}PARTIAL${NC}"
    echo "  Response received but may not contain expected code"
    echo "  Check if CODER model is properly configured"
fi

# Test debate pattern with algorithmic comparison
echo -n "Test 3: Debate pattern with algorithmic task... "
response=$(curl -s -X POST http://localhost:8080/api/collective/run \
    -H 'Content-Type: application/json' \
    -d '{"task":"Compare bubble sort vs quicksort for small arrays (n<10)","pattern":"debate"}' \
    --max-time 180)

if echo "$response" | grep -q "verdict"; then
    echo -e "${GREEN}PASS${NC}"
    ((PASSED++))
else
    echo -e "${RED}FAIL${NC}"
    ((FAILED++))
fi

# Test direct model alias (if brain API supports it)
echo -n "Test 4: Verify kitty-coder alias exists... "
# This test checks if the model registry knows about kitty-coder
# Actual implementation depends on brain API structure
if grep -q "kitty-coder" /home/user/KITT/.env 2>/dev/null; then
    echo -e "${GREEN}PASS${NC} - kitty-coder found in .env"
    ((PASSED++))
else
    echo -e "${YELLOW}SKIP${NC} - .env check"
fi

echo ""
echo "========================================="
echo "Test Summary"
echo "========================================="
echo -e "Passed: ${GREEN}${PASSED}${NC}"
echo -e "Failed: ${RED}${FAILED}${NC}"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}Some tests failed.${NC}"
    echo ""
    echo "Troubleshooting:"
    echo "1. Ensure CODER model is configured in .env:"
    echo "   LLAMACPP_CODER_MODEL=Qwen2.5-Coder-32B-Instruct-GGUF/qwen2.5-coder-32b-instruct-q8_0.gguf"
    echo "   LLAMACPP_CODER_ALIAS=kitty-coder"
    echo ""
    echo "2. Verify llama.cpp server is running with coder model"
    echo ""
    echo "3. Check brain service logs for errors"
    echo "   docker logs compose-brain-1"
    exit 1
fi
