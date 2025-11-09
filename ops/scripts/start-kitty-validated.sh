#!/bin/bash
# Start KITTY stack with sequential validation
# This script ensures each component is healthy before proceeding

set -e  # Exit on error

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper to treat various truthy env inputs consistently
is_enabled() {
    local value="${1:-}"
    value=$(printf '%s' "$value" | tr '[:upper:]' '[:lower:]')
    case "$value" in
        1|true|yes|on) return 0 ;;
        *) return 1 ;;
    esac
}

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Change to project root
cd "$PROJECT_ROOT"

# Load .env file if it exists
if [ -f .env ]; then
    echo -e "${BLUE}Loading environment from .env${NC}"
    set -a
    source .env
    set +a
else
    echo -e "${RED}Error: .env file not found${NC}"
    exit 1
fi

# Function to print status messages
print_status() {
    echo -e "${BLUE}[$(date '+%H:%M:%S')]${NC} $1"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

# Function to wait for HTTP endpoint
wait_for_http() {
    local url=$1
    local name=$2
    local max_attempts=${3:-30}
    local attempt=1

    print_status "Waiting for $name at $url..."

    while [ $attempt -le $max_attempts ]; do
        if curl -sf "$url" > /dev/null 2>&1; then
            print_success "$name is ready"
            return 0
        fi

        echo -n "."
        sleep 2
        attempt=$((attempt + 1))
    done

    echo ""
    print_error "$name failed to start within $((max_attempts * 2)) seconds"
    return 1
}

# Function to check if process is running
check_process() {
    local port=$1
    local name=$2

    if lsof -i :$port > /dev/null 2>&1; then
        print_success "$name is running on port $port"
        return 0
    else
        print_error "$name is not running on port $port"
        return 1
    fi
}

# Trap to handle cleanup on exit
cleanup() {
    if [ $? -ne 0 ]; then
        print_error "Startup failed. Check logs for details."
        echo ""
        echo "Troubleshooting:"
        echo "  - Q4 server logs: tail -f .logs/llamacpp-q4.log"
        echo "  - F16 server logs: tail -f .logs/llamacpp-f16.log"
        echo "  - Hermes summary logs: tail -f .logs/llamacpp-summary.log"
        echo "  - Docker logs: docker compose -f infra/compose/docker-compose.yml logs"
        echo "  - Check ports: lsof -i :8083,8082,8000,8080"
    fi
}
trap cleanup EXIT

echo ""
echo "╔═══════════════════════════════════════════════════════╗"
echo "║           KITTY Stack Startup Validator              ║"
echo "╚═══════════════════════════════════════════════════════╝"
echo ""

# Step 1: Check prerequisites
print_status "Checking prerequisites..."

if ! command -v docker &> /dev/null; then
    print_error "Docker is not installed"
    exit 1
fi
print_success "Docker is installed"

if ! command -v llama-server &> /dev/null && ! command -v llama-cli &> /dev/null; then
    print_warning "llama.cpp not found in PATH (will use full path from .env)"
fi

if ! docker info > /dev/null 2>&1; then
    print_error "Docker daemon is not running"
    exit 1
fi
print_success "Docker daemon is running"

echo ""

# Step 2: Stop any existing services
print_status "Stopping any existing services..."

# Stop Docker services
docker compose -f infra/compose/docker-compose.yml down > /dev/null 2>&1 || true

# Stop any llama.cpp processes on dual-model ports
Q4_PORT="${LLAMACPP_Q4_PORT:-8083}"
F16_PORT="${LLAMACPP_F16_PORT:-8082}"
SUMMARY_PORT="${LLAMACPP_SUMMARY_PORT:-8085}"
SUMMARY_ENABLED="${LLAMACPP_SUMMARY_ENABLED:-1}"
VISION_PORT="${LLAMACPP_VISION_PORT:-8086}"
VISION_ENABLED="${LLAMACPP_VISION_ENABLED:-1}"
VISION_PORT="${LLAMACPP_VISION_PORT:-8086}"
VISION_ENABLED="${LLAMACPP_VISION_ENABLED:-1}"

PORTS_TO_STOP=($Q4_PORT $F16_PORT)
if is_enabled "$SUMMARY_ENABLED"; then
    PORTS_TO_STOP+=($SUMMARY_PORT)
fi
if is_enabled "$VISION_ENABLED"; then
    PORTS_TO_STOP+=($VISION_PORT)
fi

for port in "${PORTS_TO_STOP[@]}"; do
    if lsof -i :$port > /dev/null 2>&1; then
        print_status "Stopping llama.cpp on port $port"
        lsof -ti :$port | xargs kill -9 2>/dev/null || true
    fi
done
sleep 2

print_success "Cleanup complete"
echo ""

# Step 3: Create logs directory
print_status "Preparing log directory..."
mkdir -p .logs
print_success "Log directory ready"
echo ""

# Step 4: Check for existing llama.cpp servers or start dual-model setup
Q4_PORT="${LLAMACPP_Q4_PORT:-8083}"
F16_PORT="${LLAMACPP_F16_PORT:-8082}"
SUMMARY_PORT="${LLAMACPP_SUMMARY_PORT:-8085}"
SUMMARY_ENABLED="${LLAMACPP_SUMMARY_ENABLED:-1}"

print_status "Checking for dual-model llama.cpp servers..."

# Check if servers are already running
Q4_RUNNING=false
F16_RUNNING=false
SUMMARY_RUNNING=false
VISION_RUNNING=false

if curl -sf "http://localhost:$Q4_PORT/health" > /dev/null 2>&1; then
    Q4_RUNNING=true
    print_success "Q4 server already running on port $Q4_PORT"
fi

if curl -sf "http://localhost:$F16_PORT/health" > /dev/null 2>&1; then
    F16_RUNNING=true
    print_success "F16 server already running on port $F16_PORT"
fi

if is_enabled "$SUMMARY_ENABLED"; then
    if curl -sf "http://localhost:$SUMMARY_PORT/health" > /dev/null 2>&1; then
        SUMMARY_RUNNING=true
        print_success "Hermes summary server already running on port $SUMMARY_PORT"
    fi
fi

if is_enabled "$VISION_ENABLED"; then
    if curl -sf "http://localhost:$VISION_PORT/health" > /dev/null 2>&1; then
        VISION_RUNNING=true
        print_success "Vision server already running on port $VISION_PORT"
    fi
fi

if [ "$Q4_RUNNING" = true ] && [ "$F16_RUNNING" = true ] \
   && { ! is_enabled "$SUMMARY_ENABLED" || [ "$SUMMARY_RUNNING" = true ]; } \
   && { ! is_enabled "$VISION_ENABLED" || [ "$VISION_RUNNING" = true ]; }; then
    print_status "Using existing dual-model servers"
else
    # At least one server is not running - check if models are configured
    if [ -z "$LLAMACPP_Q4_MODEL" ] || [ -z "$LLAMACPP_F16_MODEL" ] || [ -z "$LLAMACPP_MODELS_DIR" ]; then
        print_error "Dual-model servers not running and models not configured"
        echo ""
        print_warning "Configure dual-model setup in .env:"
        echo "  LLAMACPP_MODELS_DIR=/Users/Shared/Coding/models"
        echo "  LLAMACPP_Q4_MODEL=family/q4-model.gguf"
        echo "  LLAMACPP_F16_MODEL=family/f16-model.gguf"
        echo ""
        exit 1
    fi

    # Check if model files exist
    Q4_MODEL_PATH="${LLAMACPP_MODELS_DIR}/${LLAMACPP_Q4_MODEL}"
    F16_MODEL_PATH="${LLAMACPP_MODELS_DIR}/${LLAMACPP_F16_MODEL}"

    if [ ! -f "$Q4_MODEL_PATH" ]; then
        print_error "Q4 model not found: $Q4_MODEL_PATH"
        exit 1
    fi

    if [ ! -f "$F16_MODEL_PATH" ]; then
        print_error "F16 model not found: $F16_MODEL_PATH"
        exit 1
    fi

    # Start dual-model servers
    extra_components=""
    if is_enabled "$SUMMARY_ENABLED"; then
        extra_components="${extra_components}/Hermes"
    fi
    if is_enabled "$VISION_ENABLED"; then
        extra_components="${extra_components}/Vision"
    fi
    print_status "Starting llama.cpp servers (Q4/F16${extra_components})..."
    print_status "Q4 (Tool Orchestrator): ${LLAMACPP_Q4_MODEL}"
    print_status "F16 (Reasoning Engine): ${LLAMACPP_F16_MODEL}"
    if is_enabled "$SUMMARY_ENABLED"; then
        print_status "Hermes Summary (kitty-summary): ${LLAMACPP_SUMMARY_MODEL:-default Hermes 3 Q4}"
    fi
    if is_enabled "$VISION_ENABLED"; then
        print_status "Vision (kitty-vision): ${LLAMACPP_VISION_MODEL:-default Gemma 3 GGUF}"
        print_status "Vision mmproj: ${LLAMACPP_VISION_MMPROJ:-gemma-3-27b-it-mmproj-bf16.gguf}"
    fi

    "$SCRIPT_DIR/start-llamacpp-dual.sh" > .logs/llamacpp-dual.log 2>&1 &
    DUAL_PID=$!

    sleep 5

    # Check if PIDs exist
    if [ -f .logs/llamacpp-q4.pid ] && [ -f .logs/llamacpp-f16.pid ]; then
        Q4_PID=$(cat .logs/llamacpp-q4.pid)
        F16_PID=$(cat .logs/llamacpp-f16.pid)

        # Verify both processes are still running
        if ! kill -0 $Q4_PID 2>/dev/null; then
            print_error "Q4 server failed to start"
            echo "Last 20 lines of Q4 log:"
            tail -20 .logs/llamacpp-q4.log
            exit 1
        fi

        if ! kill -0 $F16_PID 2>/dev/null; then
            print_error "F16 server failed to start"
            echo "Last 20 lines of F16 log:"
            tail -20 .logs/llamacpp-f16.log
            exit 1
        fi

        if is_enabled "$SUMMARY_ENABLED" && [ -f .logs/llamacpp-summary.pid ]; then
            SUMMARY_PID=$(cat .logs/llamacpp-summary.pid)
            if ! kill -0 $SUMMARY_PID 2>/dev/null; then
                print_warning "Hermes summary server failed to start"
                echo "Last 20 lines of summary log:"
                tail -20 .logs/llamacpp-summary.log
            else
                print_success "Hermes summary server started (PID: $SUMMARY_PID)"
            fi
        fi

        if is_enabled "$VISION_ENABLED" && [ -f .logs/llamacpp-vision.pid ]; then
            VISION_PID=$(cat .logs/llamacpp-vision.pid)
            if ! kill -0 $VISION_PID 2>/dev/null; then
                print_error "Vision server failed to start"
                echo "Last 20 lines of vision log:"
                tail -20 .logs/llamacpp-vision.log
                exit 1
            else
                print_success "Vision server started (PID: $VISION_PID)"
            fi
        fi

        print_success "llama.cpp servers started (Q4 PID: $Q4_PID, F16 PID: $F16_PID)"
    else
        print_error "Failed to create PID files for dual-model servers"
        exit 1
    fi

    # Wait for both servers to be ready
    if ! wait_for_http "http://localhost:$Q4_PORT/health" "Q4 server" 60; then
        print_error "Q4 server did not become healthy"
        echo "Last 30 lines of Q4 log:"
        tail -30 .logs/llamacpp-q4.log
        exit 1
    fi

    if ! wait_for_http "http://localhost:$F16_PORT/health" "F16 server" 60; then
        print_error "F16 server did not become healthy"
        echo "Last 30 lines of F16 log:"
        tail -30 .logs/llamacpp-f16.log
        exit 1
    fi

    if is_enabled "$SUMMARY_ENABLED"; then
        if ! wait_for_http "http://localhost:$SUMMARY_PORT/health" "Hermes summary server" 60; then
            print_warning "Hermes summary server did not become healthy"
            if [ -f .logs/llamacpp-summary.log ]; then
                echo "Last 30 lines of summary log:"
                tail -30 .logs/llamacpp-summary.log
            fi
        fi
    fi

    if is_enabled "$VISION_ENABLED"; then
        if ! wait_for_http "http://localhost:$VISION_PORT/health" "Vision server" 60; then
            print_error "Vision server did not become healthy"
            if [ -f .logs/llamacpp-vision.log ]; then
                echo "Last 30 lines of vision log:"
                tail -30 .logs/llamacpp-vision.log
            fi
            exit 1
        fi
    fi
fi

echo ""

# Step 5: Start Docker services
print_status "Starting Docker services..."

docker compose -f infra/compose/docker-compose.yml up -d --build 2>&1 | grep -v "Pulling" | grep -v "Waiting" || true

print_success "Docker services started"
echo ""

# Step 6: Wait for critical services
print_status "Validating Docker services..."

# Give services a moment to initialize
sleep 5

# Check Brain service (port 8000)
if ! wait_for_http "http://localhost:8000/health" "Brain service" 30; then
    print_error "Brain service failed to start"
    docker compose -f infra/compose/docker-compose.yml logs brain | tail -20
    exit 1
fi

# Check Gateway service (port 8080)
if ! wait_for_http "http://localhost:8080/health" "Gateway service" 30; then
    print_warning "Gateway service is not responding (may not be critical)"
fi

# Check Redis
if docker compose -f infra/compose/docker-compose.yml ps redis | grep -q "Up"; then
    print_success "Redis is running"
else
    print_warning "Redis is not running"
fi

# Check PostgreSQL
if docker compose -f infra/compose/docker-compose.yml ps postgres | grep -q "Up"; then
    print_success "PostgreSQL is running"
else
    print_warning "PostgreSQL is not running"
fi

echo ""

# Step 7: Final validation
print_status "Running final validation..."

# Test CLI connectivity
print_status "Testing CLI connectivity..."
if curl -sf -X POST http://localhost:8000/api/query \
    -H "Content-Type: application/json" \
    -d '{"query": "test", "userId": "test"}' > /dev/null 2>&1; then
    print_success "CLI endpoint is functional"
else
    print_warning "CLI endpoint test failed (may need more time to initialize)"
fi

echo ""

# Step 8: Print summary
echo "╔═══════════════════════════════════════════════════════╗"
echo "║              KITTY Stack Status Summary               ║"
echo "╚═══════════════════════════════════════════════════════╝"
echo ""

# Check all services
check_process "$Q4_PORT" "Q4 server (Tool Orchestrator)" || true
check_process "$F16_PORT" "F16 server (Reasoning Engine)" || true
if is_enabled "$SUMMARY_ENABLED"; then
    check_process "$SUMMARY_PORT" "Hermes summary server" || true
fi
if is_enabled "$VISION_ENABLED"; then
    check_process "$VISION_PORT" "Vision server" || true
fi
check_process 8000 "Brain service" || true
check_process 8080 "Gateway service" || true
check_process 5432 "PostgreSQL" || true
check_process 6379 "Redis" || true

echo ""
echo "Access Points:"
echo "  - CLI: kitty-cli shell"
echo "  - Model Manager: kitty-model-manager tui"
echo "  - Brain API: http://localhost:8000/docs"
echo "  - Gateway API: http://localhost:8080/docs"
echo ""

echo "Logs:"
echo "  - Q4 server: tail -f .logs/llamacpp-q4.log"
echo "  - F16 server: tail -f .logs/llamacpp-f16.log"
echo "  - Dual startup: tail -f .logs/llamacpp-dual.log"
if is_enabled "$SUMMARY_ENABLED"; then
    echo "  - Hermes summary: tail -f .logs/llamacpp-summary.log"
fi
if is_enabled "$VISION_ENABLED"; then
    echo "  - Vision server: tail -f .logs/llamacpp-vision.log"
fi
echo "  - Docker: docker compose -f infra/compose/docker-compose.yml logs -f"
echo ""

echo "To stop everything:"
echo "  ./ops/scripts/stop-kitty.sh"
echo ""

print_success "KITTY stack is ready!"
echo ""
