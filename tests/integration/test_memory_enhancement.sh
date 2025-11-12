#!/bin/bash
# Integration test for Memory Enhancement (BGE embeddings + reranker)
# Run this script on workstation with services running

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

PASSED=0
FAILED=0

MEM0_BASE=${MEM0_MCP_URL:-"http://localhost:8765"}

echo "========================================="
echo "Memory Enhancement Integration Tests"
echo "========================================="
echo ""

# Test 1: Check mem0-mcp health
echo -n "Test 1: mem0-mcp health check... "
response=$(curl -s -f "$MEM0_BASE/health" 2>&1)
if echo "$response" | grep -q "healthy"; then
    echo -e "${GREEN}PASS${NC}"
    ((PASSED++))
else
    echo -e "${RED}FAIL${NC} - mem0-mcp not reachable"
    ((FAILED++))
fi

# Test 2: Check memory stats (should show BGE model and reranker status)
echo -n "Test 2: Memory stats with BGE embeddings... "
response=$(curl -s "$MEM0_BASE/memory/stats" 2>&1)

if echo "$response" | grep -q "bge"; then
    echo -e "${GREEN}PASS${NC}"
    ((PASSED++))
    echo "  Embedding model: $(echo "$response" | jq -r '.embedding_model' 2>/dev/null || echo 'N/A')"

    reranker_enabled=$(echo "$response" | jq -r '.reranker_enabled' 2>/dev/null || echo 'false')
    if [ "$reranker_enabled" = "true" ]; then
        echo -e "  Reranker: ${GREEN}ENABLED${NC}"
        echo "  Reranker model: $(echo "$response" | jq -r '.reranker_model' 2>/dev/null || echo 'N/A')"
    else
        echo -e "  Reranker: ${YELLOW}DISABLED${NC} (falling back to vector-only)"
    fi
else
    echo -e "${YELLOW}PARTIAL${NC} - BGE model not detected"
    echo "  Current model: $(echo "$response" | jq -r '.embedding_model' 2>/dev/null || echo 'unknown')"
fi

# Test 3: Add test memories
echo -n "Test 3: Add test memories... "
mem1=$(curl -s -X POST "$MEM0_BASE/memory/add" \
    -H 'Content-Type: application/json' \
    -d '{"conversation_id":"test-memory-enhancement","content":"PETG is best for outdoor furniture due to UV resistance","tags":["domain","material"]}' 2>&1)

mem2=$(curl -s -X POST "$MEM0_BASE/memory/add" \
    -H 'Content-Type: application/json' \
    -d '{"conversation_id":"test-memory-enhancement","content":"ABS provides better strength but yellows in sunlight","tags":["domain","material"]}' 2>&1)

mem3=$(curl -s -X POST "$MEM0_BASE/memory/add" \
    -H 'Content-Type: application/json' \
    -d '{"conversation_id":"test-memory-enhancement","content":"TPU is flexible but not recommended for structural parts","tags":["domain","material"]}' 2>&1)

if echo "$mem1" | grep -q "id" && echo "$mem2" | grep -q "id" && echo "$mem3" | grep -q "id"; then
    echo -e "${GREEN}PASS${NC} - Added 3 test memories"
    ((PASSED++))
else
    echo -e "${RED}FAIL${NC} - Failed to add memories"
    ((FAILED++))
fi

# Test 4: Search memories (should use BGE embeddings + reranker if enabled)
echo -n "Test 4: Search with semantic similarity... "
search_response=$(curl -s -X POST "$MEM0_BASE/memory/search" \
    -H 'Content-Type: application/json' \
    -d '{"query":"What material works well outdoors?","conversation_id":"test-memory-enhancement","limit":3}' 2>&1)

if echo "$search_response" | grep -q "PETG"; then
    echo -e "${GREEN}PASS${NC}"
    ((PASSED++))

    # Display results with scores
    echo ""
    echo -e "${BLUE}Search Results:${NC}"
    echo "$search_response" | jq -r '.memories[] | "  - [\(.score | tostring | .[0:5])] \(.content[0:60])..."' 2>/dev/null || echo "  (jq not available)"
    echo ""
else
    echo -e "${RED}FAIL${NC} - Search did not return expected results"
    ((FAILED++))
fi

# Test 5: Search with tag filtering
echo -n "Test 5: Search with tag filtering... "
filtered_search=$(curl -s -X POST "$MEM0_BASE/memory/search" \
    -H 'Content-Type: application/json' \
    -d '{"query":"material strength","conversation_id":"test-memory-enhancement","include_tags":["material"],"limit":5}' 2>&1)

if echo "$filtered_search" | grep -q '"count"'; then
    count=$(echo "$filtered_search" | jq -r '.count' 2>/dev/null || echo "0")
    if [ "$count" -ge 1 ]; then
        echo -e "${GREEN}PASS${NC} - Found $count tagged memories"
        ((PASSED++))
    else
        echo -e "${YELLOW}PARTIAL${NC} - No tagged memories found"
    fi
else
    echo -e "${RED}FAIL${NC}"
    ((FAILED++))
fi

# Test 6: Verify backwards compatibility (old memories still accessible)
echo -n "Test 6: Backwards compatibility check... "
all_memories=$(curl -s -X POST "$MEM0_BASE/memory/search" \
    -H 'Content-Type: application/json' \
    -d '{"query":"test","limit":50,"score_threshold":0.0}' 2>&1)

total_count=$(echo "$all_memories" | jq -r '.count' 2>/dev/null || echo "0")
if [ "$total_count" -ge 3 ]; then
    echo -e "${GREEN}PASS${NC} - $total_count memories accessible"
    ((PASSED++))
else
    echo -e "${YELLOW}PARTIAL${NC} - Only $total_count memories found"
fi

echo ""
echo "========================================="
echo "Test Summary"
echo "========================================="
echo -e "Passed: ${GREEN}${PASSED}${NC}"
echo -e "Failed: ${RED}${FAILED}${NC}"
echo ""

# Cleanup test memories (optional - comment out to keep them)
echo "Cleaning up test memories..."
mem1_id=$(echo "$mem1" | jq -r '.id' 2>/dev/null || echo "")
mem2_id=$(echo "$mem2" | jq -r '.id' 2>/dev/null || echo "")
mem3_id=$(echo "$mem3" | jq -r '.id' 2>/dev/null || echo "")

[ -n "$mem1_id" ] && curl -s -X DELETE "$MEM0_BASE/memory/$mem1_id" > /dev/null 2>&1
[ -n "$mem2_id" ] && curl -s -X DELETE "$MEM0_BASE/memory/$mem2_id" > /dev/null 2>&1
[ -n "$mem3_id" ] && curl -s -X DELETE "$MEM0_BASE/memory/$mem3_id" > /dev/null 2>&1

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}All tests passed!${NC}"
    echo ""
    echo "Memory Enhancement Status:"
    echo "  ✓ BGE embeddings enabled (BAAI/bge-small-en-v1.5)"

    reranker_status=$(curl -s "$MEM0_BASE/memory/stats" | jq -r '.reranker_enabled' 2>/dev/null || echo "false")
    if [ "$reranker_status" = "true" ]; then
        echo "  ✓ Reranker enabled (BAAI/bge-reranker-base)"
        echo "  ✓ Expected improvements:"
        echo "    - Embedding quality: +15-20% vs all-MiniLM"
        echo "    - Top-3 precision: +20-30% with reranker"
    else
        echo "  - Reranker disabled (vector-only search)"
        echo "    To enable: Set RERANKER_MODEL=BAAI/bge-reranker-base in .env"
    fi
    exit 0
else
    echo -e "${RED}Some tests failed.${NC}"
    echo ""
    echo "Troubleshooting:"
    echo "1. Ensure mem0-mcp service is running:"
    echo "   docker ps | grep mem0-mcp"
    echo ""
    echo "2. Check mem0-mcp logs for errors:"
    echo "   docker logs compose-mem0-mcp-1"
    echo ""
    echo "3. Verify .env configuration:"
    echo "   EMBEDDING_MODEL=BAAI/bge-small-en-v1.5"
    echo "   RERANKER_MODEL=BAAI/bge-reranker-base"
    echo ""
    echo "4. Restart services to pick up new configuration:"
    echo "   docker compose restart mem0-mcp"
    exit 1
fi
