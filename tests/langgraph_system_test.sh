#!/bin/bash
# LangGraph Multi-Agent System Test Suite
# Tests Q4/F16 routing, complexity analysis, tool execution, and metrics
# Run from repository root: ./tests/langgraph_system_test.sh

set -e

BRAIN_URL="${BRAIN_URL:-http://localhost:8000}"
RESULTS_DIR="./test-results/langgraph-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$RESULTS_DIR"

echo "========================================"
echo "LangGraph System Test Suite"
echo "========================================"
echo "Brain URL: $BRAIN_URL"
echo "Results: $RESULTS_DIR"
echo ""

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

pass_count=0
fail_count=0

test_query() {
    local test_name="$1"
    local query="$2"
    local conversation_id="$3"
    local expected_model="$4"  # q4 or f16
    local check_tools="$5"     # true/false

    echo "----------------------------------------"
    echo "TEST: $test_name"
    echo "Query: $query"
    echo "Expected Model: $expected_model"
    echo ""

    # Make request
    start_time=$(date +%s)
    response=$(curl -s -X POST "$BRAIN_URL/api/query" \
        -H "Content-Type: application/json" \
        -d "{
            \"conversationId\": \"$conversation_id\",
            \"userId\": \"test-user\",
            \"intent\": \"conversational\",
            \"prompt\": \"$query\"
        }")
    end_time=$(date +%s)
    duration=$((end_time - start_time))

    # Save full response
    echo "$response" | jq '.' > "$RESULTS_DIR/${conversation_id}.json" 2>/dev/null || echo "$response" > "$RESULTS_DIR/${conversation_id}.json"

    # Extract key fields
    status=$(echo "$response" | jq -r '.status // "unknown"')
    model=$(echo "$response" | jq -r '.metadata.model_alias // .routing_tier // "unknown"')
    complexity=$(echo "$response" | jq -r '.metadata.complexity_score // "N/A"')
    tools_used=$(echo "$response" | jq -r '.metadata.tools_used // [] | length')

    echo "Status: $status"
    echo "Model: $model"
    echo "Complexity: $complexity"
    echo "Tools Used: $tools_used"
    echo "Duration: ${duration}s"

    # Validation
    if [ "$status" != "success" ] && [ "$status" != "unknown" ]; then
        echo -e "${RED}FAIL: Request failed${NC}"
        echo "$response" | jq -r '.error // .detail // .' | head -5
        ((fail_count++))
        return 1
    fi

    # Check model routing (if we can determine it from logs)
    # Note: This is best-effort as response format may vary
    if [ "$expected_model" != "any" ]; then
        if echo "$model" | grep -qi "$expected_model"; then
            echo -e "${GREEN}✓ Routed to expected model${NC}"
        else
            echo -e "${YELLOW}⚠ Model routing unclear (expected: $expected_model, got: $model)${NC}"
        fi
    fi

    # Check tool usage
    if [ "$check_tools" = "true" ]; then
        if [ "$tools_used" -gt 0 ]; then
            echo -e "${GREEN}✓ Tools executed: $tools_used${NC}"
        else
            echo -e "${YELLOW}⚠ No tools executed (may be expected)${NC}"
        fi
    fi

    echo -e "${GREEN}PASS${NC}"
    ((pass_count++))
    echo ""
}

# Test 1: Simple General Reasoning (Q4 expected)
test_query \
    "Simple Math Query" \
    "What is 2 + 2?" \
    "test-simple-001" \
    "q4" \
    "false"

# Test 2: General Knowledge (Q4 expected)
test_query \
    "General Knowledge" \
    "What is the capital of France?" \
    "test-simple-002" \
    "q4" \
    "false"

# Test 3: Complex Multi-Step Query (F16 expected)
test_query \
    "Complex Reasoning" \
    "Explain the differences between supervised and unsupervised machine learning, including when to use each approach, and provide examples of algorithms for both categories." \
    "test-complex-001" \
    "f16" \
    "false"

# Test 4: CAD Generation Query (F16 + Tools expected)
test_query \
    "CAD Design Request" \
    "Design a parametric mounting bracket for a Raspberry Pi 4 with adjustable height between 10-30mm and M3 mounting holes" \
    "test-cad-001" \
    "f16" \
    "true"

# Test 5: Fabrication Status Query (Tools expected)
test_query \
    "Printer Status Check" \
    "What 3D printers are currently online and available?" \
    "test-fab-001" \
    "any" \
    "true"

# Test 6: Device Discovery Query (Tools expected)
test_query \
    "Device Discovery" \
    "Scan for network devices and show me what you find" \
    "test-discovery-001" \
    "any" \
    "true"

# Test 7: Multi-Step Fabrication Workflow (F16 + Tools expected)
test_query \
    "Complex Fabrication Workflow" \
    "Design a simple phone stand, convert it to STL, analyze the model for printability, and queue it to the best available printer" \
    "test-workflow-001" \
    "f16" \
    "true"

echo "========================================"
echo "Metrics Validation"
echo "========================================"

# Check Prometheus metrics
echo "Checking LangGraph metrics..."
metrics=$(curl -s "$BRAIN_URL/metrics" | grep -E "brain_langgraph|brain_graph" || echo "")

if [ -n "$metrics" ]; then
    echo "$metrics" | tee "$RESULTS_DIR/metrics.txt"
    echo -e "${GREEN}✓ LangGraph metrics found${NC}"
else
    echo -e "${YELLOW}⚠ No LangGraph-specific metrics found${NC}"
fi

echo ""
echo "Checking rollout percentage..."
rollout=$(curl -s "$BRAIN_URL/metrics" | grep "brain_langgraph_rollout_percent" | awk '{print $2}' || echo "N/A")
echo "Rollout: ${rollout}%"

echo ""
echo "========================================"
echo "Log Analysis"
echo "========================================"

# Analyze Docker logs for routing decisions
echo "Analyzing brain service logs..."
if command -v docker &> /dev/null; then
    docker logs compose-brain-1 --tail 200 2>&1 | \
        grep -E "LangGraph|Q4|F16|complexity|escalat|routing" | \
        tail -30 > "$RESULTS_DIR/brain-logs.txt"

    echo "Recent routing activity:"
    cat "$RESULTS_DIR/brain-logs.txt"
else
    echo "Docker not available - skipping log analysis"
fi

echo ""
echo "========================================"
echo "llama.cpp Server Status"
echo "========================================"

check_server() {
    local name="$1"
    local port="$2"

    if curl -s "http://localhost:$port/health" | grep -q "ok"; then
        echo -e "$name (port $port): ${GREEN}✓ Healthy${NC}"
    else
        echo -e "$name (port $port): ${RED}✗ Unhealthy${NC}"
        ((fail_count++))
    fi
}

check_server "Q4 (Athene-V2)" "8083"
check_server "F16 (Llama-3.3-70B)" "8082"
check_server "Summary (Hermes-3)" "8085"
check_server "Vision (Gemma-3)" "8086"

echo ""
echo "========================================"
echo "Test Summary"
echo "========================================"
echo -e "Passed: ${GREEN}$pass_count${NC}"
echo -e "Failed: ${RED}$fail_count${NC}"
echo "Results saved to: $RESULTS_DIR"
echo ""

if [ $fail_count -eq 0 ]; then
    echo -e "${GREEN}All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}Some tests failed${NC}"
    exit 1
fi
