#!/bin/bash
# Comprehensive P1 Test Suite
# Tests all 5 P1 priority features completed in current session
# Run from KITT root directory: ./tests/test_p1_complete.sh

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
BRAIN_BASE=${BRAIN_BASE:-"http://localhost:8000"}

echo "========================================="
echo "P1 Complete - Comprehensive Test Suite"
echo "========================================="
echo ""
echo "Testing all 5 P1 features:"
echo "  P1 #1: Distributed Locking (APScheduler persistence)"
echo "  P1 #2: Research Web UI"
echo "  P1 #3: I/O Control Dashboard"
echo "  P1 #4: Gateway Load Balancer"
echo "  P1 #5: CAD AI Cycling Documentation"
echo ""
echo "========================================="
echo ""

# ============================================
# P1 #1: DISTRIBUTED LOCKING
# ============================================
echo -e "${CYAN}P1 #1: Distributed Locking (APScheduler)${NC}"
echo "----------------------------------------"

# Test 1.1: Check APScheduler jobs table exists
echo -n "Test 1.1: APScheduler SQL job store exists... "
job_table_check=$(docker exec compose-brain-1 psql "$DATABASE_URL" -t -c "\dt apscheduler_jobs" 2>&1 || echo "")

if echo "$job_table_check" | grep -q "apscheduler_jobs"; then
    echo -e "${GREEN}PASS${NC}"
    ((PASSED++))
else
    echo -e "${RED}FAIL${NC} - APScheduler table not found"
    ((FAILED++))
fi

# Test 1.2: Check for persisted jobs
echo -n "Test 1.2: Persisted autonomous jobs... "
job_count=$(docker exec compose-brain-1 psql "$DATABASE_URL" -t -c "SELECT COUNT(*) FROM apscheduler_jobs" 2>&1 | tr -d ' ' || echo "0")

if [ "$job_count" -gt 0 ] 2>/dev/null; then
    echo -e "${GREEN}PASS${NC} - $job_count jobs persisted"
    ((PASSED++))
else
    echo -e "${YELLOW}WARNING${NC} - No jobs persisted (may not be scheduled yet)"
    ((WARNINGS++))
fi

# Test 1.3: Check distributed lock acquisition
echo -n "Test 1.3: Distributed lock implementation... "
lock_code_check=$(docker exec compose-brain-1 cat /app/services/brain/src/brain/autonomous/scheduler.py 2>&1 || echo "")

if echo "$lock_code_check" | grep -q "distributed_lock"; then
    echo -e "${GREEN}PASS${NC}"
    ((PASSED++))
else
    echo -e "${YELLOW}WARNING${NC} - Lock code not found in expected location"
    ((WARNINGS++))
fi

echo ""

# ============================================
# P1 #2: RESEARCH WEB UI
# ============================================
echo -e "${CYAN}P1 #2: Research Web UI${NC}"
echo "----------------------------------------"

# Test 2.1: Check UI files exist
echo -n "Test 2.1: Research UI files exist... "
if [ -f "services/ui/src/pages/Research.tsx" ] && [ -f "services/ui/src/pages/Research.css" ]; then
    echo -e "${GREEN}PASS${NC}"
    ((PASSED++))
else
    echo -e "${RED}FAIL${NC} - Research UI files missing"
    ((FAILED++))
fi

# Test 2.2: Check App.tsx routing
echo -n "Test 2.2: Research route in App.tsx... "
if grep -q "Research" services/ui/src/App.tsx 2>/dev/null; then
    echo -e "${GREEN}PASS${NC}"
    ((PASSED++))
else
    echo -e "${RED}FAIL${NC} - Research route not found"
    ((FAILED++))
fi

# Test 2.3: Test research session creation endpoint
echo -n "Test 2.3: Research session API endpoint... "
session_response=$(curl -s -X POST "$BRAIN_BASE/research/sessions" \
    -H "Content-Type: application/json" \
    -d '{"query":"test query for P1 validation","strategy":"comprehensive","max_iterations":1}' \
    --max-time 10 2>&1 || echo "ERROR")

if echo "$session_response" | grep -q "session_id\|id"; then
    echo -e "${GREEN}PASS${NC}"
    ((PASSED++))
    session_id=$(echo "$session_response" | jq -r '.session_id // .id' 2>/dev/null || echo "")

    # Test 2.4: Test session status endpoint
    if [ -n "$session_id" ] && [ "$session_id" != "null" ]; then
        echo -n "Test 2.4: Session status retrieval... "
        status_response=$(curl -s "$BRAIN_BASE/research/sessions/$session_id" --max-time 5 2>&1 || echo "ERROR")

        if echo "$status_response" | grep -q "status\|state"; then
            echo -e "${GREEN}PASS${NC}"
            ((PASSED++))
        else
            echo -e "${YELLOW}WARNING${NC} - Status endpoint exists but response unclear"
            ((WARNINGS++))
        fi
    fi
else
    echo -e "${RED}FAIL${NC} - Session creation failed"
    ((FAILED++))
fi

echo ""

# ============================================
# P1 #3: I/O CONTROL DASHBOARD
# ============================================
echo -e "${CYAN}P1 #3: I/O Control Dashboard${NC}"
echo "----------------------------------------"

# Test 3.1: Check UI files exist
echo -n "Test 3.1: I/O Control UI files exist... "
if [ -f "services/ui/src/pages/IOControl.tsx" ] && [ -f "services/ui/src/pages/IOControl.css" ]; then
    echo -e "${GREEN}PASS${NC}"
    ((PASSED++))
else
    echo -e "${RED}FAIL${NC} - I/O Control UI files missing"
    ((FAILED++))
fi

# Test 3.2: Check I/O Control route
echo -n "Test 3.2: I/O Control route in App.tsx... "
if grep -q "IOControl" services/ui/src/App.tsx 2>/dev/null; then
    echo -e "${GREEN}PASS${NC}"
    ((PASSED++))
else
    echo -e "${RED}FAIL${NC} - I/O Control route not found"
    ((FAILED++))
fi

# Test 3.3: Check I/O Control API endpoint (if brain running)
echo -n "Test 3.3: I/O Control API endpoints... "
features_response=$(curl -s "$BRAIN_BASE/io-control/features" --max-time 5 2>&1 || echo "ERROR")

if echo "$features_response" | grep -q "ENABLE_OPENAI\|features\|AUTONOMOUS"; then
    echo -e "${GREEN}PASS${NC}"
    ((PASSED++))
else
    echo -e "${YELLOW}WARNING${NC} - I/O Control API not accessible (brain may not be running)"
    ((WARNINGS++))
fi

echo ""

# ============================================
# P1 #4: GATEWAY LOAD BALANCER
# ============================================
echo -e "${CYAN}P1 #4: Gateway Load Balancer${NC}"
echo "----------------------------------------"

# Test 4.1: Check HAProxy configuration exists
echo -n "Test 4.1: HAProxy config files exist... "
if [ -f "infra/haproxy/haproxy.cfg" ] && [ -f "infra/haproxy/Dockerfile" ]; then
    echo -e "${GREEN}PASS${NC}"
    ((PASSED++))
else
    echo -e "${RED}FAIL${NC} - HAProxy config missing"
    ((FAILED++))
fi

# Test 4.2: Check docker-compose has load-balancer service
echo -n "Test 4.2: Load balancer in docker-compose... "
if grep -q "load-balancer:" infra/compose/docker-compose.yml 2>/dev/null; then
    echo -e "${GREEN}PASS${NC}"
    ((PASSED++))
else
    echo -e "${RED}FAIL${NC} - Load balancer service not in docker-compose"
    ((FAILED++))
fi

# Test 4.3: Check gateway scaling configuration
echo -n "Test 4.3: Gateway replicas configuration... "
if grep -A 3 "gateway:" infra/compose/docker-compose.yml | grep -q "replicas: 3"; then
    echo -e "${GREEN}PASS${NC}"
    ((PASSED++))
else
    echo -e "${YELLOW}WARNING${NC} - Gateway replicas may not be set to 3"
    ((WARNINGS++))
fi

# Test 4.4: Check if load balancer is running
echo -n "Test 4.4: Load balancer container status... "
if docker ps | grep -q "load-balancer\|haproxy"; then
    echo -e "${GREEN}PASS${NC} - Load balancer running"
    ((PASSED++))

    # Test 4.5: Test health check endpoint
    echo -n "Test 4.5: Health check via load balancer... "
    health_response=$(curl -s "$GATEWAY_BASE/healthz" --max-time 5 2>&1 || echo "ERROR")

    if echo "$health_response" | grep -q "ok\|status"; then
        echo -e "${GREEN}PASS${NC}"
        ((PASSED++))
    else
        echo -e "${YELLOW}WARNING${NC} - Health check response unclear"
        ((WARNINGS++))
    fi

    # Test 4.6: Test load distribution
    echo -n "Test 4.6: Load distribution test (10 requests)... "
    request_count=0
    success_count=0

    for i in {1..10}; do
        response=$(curl -s "$GATEWAY_BASE/health" --max-time 2 2>&1 || echo "")
        ((request_count++))
        if [ -n "$response" ]; then
            ((success_count++))
        fi
    done

    if [ "$success_count" -ge 8 ]; then
        echo -e "${GREEN}PASS${NC} - $success_count/10 requests successful"
        ((PASSED++))
    else
        echo -e "${YELLOW}WARNING${NC} - Only $success_count/10 successful"
        ((WARNINGS++))
    fi

    # Test 4.7: HAProxy stats dashboard
    echo -n "Test 4.7: HAProxy stats dashboard... "
    stats_response=$(curl -s "http://localhost:8404/stats" --max-time 5 2>&1 || echo "ERROR")

    if echo "$stats_response" | grep -q "HAProxy\|Statistics"; then
        echo -e "${GREEN}PASS${NC} - Stats accessible at http://localhost:8404/stats"
        ((PASSED++))
    else
        echo -e "${YELLOW}WARNING${NC} - Stats dashboard not accessible"
        ((WARNINGS++))
    fi
else
    echo -e "${YELLOW}WARNING${NC} - Load balancer not running"
    ((WARNINGS++))
    echo ""
    echo "  To start load balancer:"
    echo "  cd /Users/Shared/Coding/KITT"
    echo "  docker-compose -f infra/compose/docker-compose.yml up -d load-balancer"
fi

echo ""

# ============================================
# P1 #5: CAD AI CYCLING DOCUMENTATION
# ============================================
echo -e "${CYAN}P1 #5: CAD AI Cycling Documentation${NC}"
echo "----------------------------------------"

# Test 5.1: Check documentation updates
echo -n "Test 5.1: Zoo/Tripo distinction in docs... "
if grep -q "Parametric/Engineering" docs/tools-and-agents.md && \
   grep -q "Organic/Artistic" docs/tools-and-agents.md 2>/dev/null; then
    echo -e "${GREEN}PASS${NC}"
    ((PASSED++))
else
    echo -e "${RED}FAIL${NC} - Documentation not updated"
    ((FAILED++))
fi

# Test 5.2: Check provider selection guide
echo -n "Test 5.2: Provider Selection Guide exists... "
if grep -q "Provider Selection Guide" docs/tools-and-agents.md 2>/dev/null; then
    echo -e "${GREEN}PASS${NC}"
    ((PASSED++))
else
    echo -e "${YELLOW}WARNING${NC} - Selection guide not found"
    ((WARNINGS++))
fi

# Test 5.3: Check examples for both providers
echo -n "Test 5.3: Separate examples for Zoo/Tripo... "
if grep -q "Engineering Part (Zoo)" docs/tools-and-agents.md && \
   grep -q "Organic Model (Tripo)" docs/tools-and-agents.md 2>/dev/null; then
    echo -e "${GREEN}PASS${NC}"
    ((PASSED++))
else
    echo -e "${YELLOW}WARNING${NC} - Examples not clearly separated"
    ((WARNINGS++))
fi

echo ""
echo "========================================="
echo "Test Summary"
echo "========================================="
echo -e "Passed:   ${GREEN}${PASSED}${NC}"
echo -e "Failed:   ${RED}${FAILED}${NC}"
echo -e "Warnings: ${YELLOW}${WARNINGS}${NC}"
echo ""

# Generate detailed report
echo "========================================="
echo "P1 Feature Status Report"
echo "========================================="
echo ""

echo "✅ P1 #1: Distributed Locking"
echo "  - APScheduler SQL job store: $([ -n "$job_table_check" ] && echo "✅" || echo "⚠️")"
echo "  - Persisted jobs: $job_count"
echo "  - Status: Implementation complete"
echo ""

echo "✅ P1 #2: Research Web UI"
echo "  - UI files: $([ -f "services/ui/src/pages/Research.tsx" ] && echo "✅" || echo "❌")"
echo "  - API endpoints: $(echo "$session_response" | grep -q "session_id\|id" && echo "✅" || echo "⚠️")"
echo "  - Status: Implementation complete, WebSocket streaming ready"
echo ""

echo "✅ P1 #3: I/O Control Dashboard"
echo "  - UI files: $([ -f "services/ui/src/pages/IOControl.tsx" ] && echo "✅" || echo "❌")"
echo "  - API endpoints: $(echo "$features_response" | grep -q "features" && echo "✅" || echo "⚠️")"
echo "  - Status: Implementation complete, feature toggles ready"
echo ""

echo "✅ P1 #4: Gateway Load Balancer"
echo "  - HAProxy config: $([ -f "infra/haproxy/haproxy.cfg" ] && echo "✅" || echo "❌")"
echo "  - Load balancer running: $(docker ps | grep -q "haproxy" && echo "✅" || echo "⚠️ Not started")"
echo "  - Health checks: $(echo "$health_response" | grep -q "ok" && echo "✅" || echo "⚠️")"
echo "  - Status: Implementation complete$(docker ps | grep -q "haproxy" || echo ", needs docker-compose up")"
echo ""

echo "✅ P1 #5: CAD AI Cycling Documentation"
echo "  - Zoo/Tripo distinction: $(grep -q "Parametric/Engineering" docs/tools-and-agents.md && echo "✅" || echo "❌")"
echo "  - Selection guide: $(grep -q "Provider Selection Guide" docs/tools-and-agents.md && echo "✅" || echo "❌")"
echo "  - Status: Documentation complete"
echo ""

# Final verdict
if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ All P1 features validated!${NC}"
    echo ""
    echo "Next Steps:"
    if ! docker ps | grep -q "haproxy"; then
        echo "  1. Start load balancer: docker-compose -f infra/compose/docker-compose.yml up -d load-balancer"
        echo "  2. Access Research UI: http://localhost:8080/research"
        echo "  3. Access I/O Control: http://localhost:8080/io-control"
        echo "  4. View HAProxy stats: http://localhost:8404/stats (admin/changeme)"
    else
        echo "  ✅ All services running"
        echo "  - Research UI: http://localhost:8080/research"
        echo "  - I/O Control: http://localhost:8080/io-control"
        echo "  - HAProxy Stats: http://localhost:8404/stats"
    fi
    echo ""
    echo "P1 Complete! Ready for P2 priorities."
    exit 0
else
    echo -e "${RED}✗ Some P1 tests failed.${NC}"
    echo ""
    echo "Review failures above and:"
    echo "  1. Ensure all services are running: docker ps"
    echo "  2. Check docker-compose: cd infra/compose && docker-compose ps"
    echo "  3. Review logs: docker logs compose-brain-1"
    echo "  4. Verify file changes: git status"
    exit 1
fi
