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
        echo "  - llama.cpp logs: tail -f .logs/llamacpp.log"
        echo "  - Docker logs: docker compose -f infra/compose/docker-compose.yml logs"
        echo "  - Check ports: lsof -i :8082,8000,8080"
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

# Stop any llama.cpp processes on our ports
if [ -n "$LLAMACPP_PORT" ]; then
    if lsof -i :$LLAMACPP_PORT > /dev/null 2>&1; then
        print_status "Stopping llama.cpp on port $LLAMACPP_PORT"
        lsof -ti :$LLAMACPP_PORT | xargs kill -9 2>/dev/null || true
        sleep 2
    fi
fi

print_success "Cleanup complete"
echo ""

# Step 3: Create logs directory
print_status "Preparing log directory..."
mkdir -p .logs
print_success "Log directory ready"
echo ""

# Step 4: Check for existing llama.cpp server or start new one
LLAMACPP_PORT="${LLAMACPP_PORT:-8082}"
print_status "Checking for llama.cpp server on port $LLAMACPP_PORT..."

if curl -sf "http://localhost:$LLAMACPP_PORT/health" > /dev/null 2>&1; then
    # Server already running - get model info
    MODEL_INFO=$(curl -sf "http://localhost:$LLAMACPP_PORT/v1/models" 2>/dev/null)
    MODEL_NAME=$(echo "$MODEL_INFO" | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4)

    print_success "llama.cpp server already running"
    print_status "Current model: $MODEL_NAME"
    print_status "Using existing server on port $LLAMACPP_PORT"
else
    # No server running - check if model is configured
    if [ -z "$LLAMACPP_PRIMARY_MODEL" ] || [ -z "$LLAMACPP_MODELS_DIR" ]; then
        print_error "No llama.cpp server running and no model configured"
        echo ""
        print_warning "Start a model first using Model Manager TUI:"
        echo "  ${GREEN}kitty-model-manager tui${NC}"
        echo ""
        print_warning "Or configure a model in .env for automatic bootstrap:"
        echo "  LLAMACPP_MODELS_DIR=/Users/Shared/Coding/models"
        echo "  LLAMACPP_PRIMARY_MODEL=family/model.gguf"
        echo ""
        exit 1
    fi

    # Model is configured - start server
    print_status "Starting llama.cpp server..."

    LLAMACPP_HOST="${LLAMACPP_HOST:-0.0.0.0}"
    LLAMACPP_CTX="${LLAMACPP_CTX:-8192}"
    LLAMACPP_N_GPU_LAYERS="${LLAMACPP_N_GPU_LAYERS:-999}"
    LLAMACPP_THREADS="${LLAMACPP_THREADS:-20}"
    LLAMACPP_BATCH_SIZE="${LLAMACPP_BATCH_SIZE:-4096}"
    LLAMACPP_UBATCH_SIZE="${LLAMACPP_UBATCH_SIZE:-1024}"
    LLAMACPP_PARALLEL="${LLAMACPP_PARALLEL:-6}"
    LLAMACPP_FLASH_ATTN="${LLAMACPP_FLASH_ATTN:-1}"

    # Determine model to load
    MODEL_PATH="${LLAMACPP_MODELS_DIR}/${LLAMACPP_PRIMARY_MODEL}"
    if [ ! -f "$MODEL_PATH" ]; then
        print_error "Model not found: $MODEL_PATH"
        print_warning "Check your .env configuration or use Model Manager TUI:"
        echo "  ${GREEN}kitty-model-manager tui${NC}"
        exit 1
    fi

    print_status "Model: $LLAMACPP_PRIMARY_MODEL"
    print_status "Port: $LLAMACPP_PORT"
    print_status "GPU Layers: $LLAMACPP_N_GPU_LAYERS"

    normalize_flash_attn() {
        local input="${1:-}"
        local val
        val="$(printf '%s' "$input" | tr '[:upper:]' '[:lower:]')"
        case "$val" in
            1|true|on|yes) echo "on" ;;
            0|false|off|no) echo "off" ;;
            auto) echo "auto" ;;
            "" ) echo "" ;;
            *) echo "$1" ;;
        esac
    }

    FLASH_ATTN_VALUE=$(normalize_flash_attn "${LLAMACPP_FLASH_ATTN:-auto}")
    FLASH_ARGS=()
    if [ -n "$FLASH_ATTN_VALUE" ]; then
        FLASH_ARGS=(--flash-attn "$FLASH_ATTN_VALUE")
    fi

    # Start llama.cpp server
    llama-server \
        --model "$MODEL_PATH" \
        --host "$LLAMACPP_HOST" \
        --port "$LLAMACPP_PORT" \
        --ctx-size "$LLAMACPP_CTX" \
        --n-gpu-layers "$LLAMACPP_N_GPU_LAYERS" \
        --threads "$LLAMACPP_THREADS" \
        --batch-size "$LLAMACPP_BATCH_SIZE" \
        --ubatch-size "$LLAMACPP_UBATCH_SIZE" \
        -np "$LLAMACPP_PARALLEL" \
        "${FLASH_ARGS[@]}" \
        --log-disable \
        > .logs/llamacpp.log 2>&1 &

    LLAMA_PID=$!
    echo "$LLAMA_PID" > .logs/llamacpp.pid

    sleep 3

    # Check if llama-server is still running
    if ! kill -0 $LLAMA_PID 2>/dev/null; then
        print_error "llama-server failed to start"
        echo "Last 20 lines of log:"
        tail -20 .logs/llamacpp.log
        exit 1
    fi

    print_success "llama-server started (PID: $LLAMA_PID)"

    # Wait for llama.cpp to be ready
    if ! wait_for_http "http://localhost:$LLAMACPP_PORT/health" "llama.cpp server" 60; then
        print_error "llama.cpp server did not become healthy"
        echo "Last 30 lines of log:"
        tail -30 .logs/llamacpp.log
        exit 1
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
check_process "$LLAMACPP_PORT" "llama.cpp" || true
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
echo "  - llama.cpp: tail -f .logs/llamacpp.log"
echo "  - Docker: docker compose -f infra/compose/docker-compose.yml logs -f"
echo ""

echo "To stop everything:"
echo "  ./ops/scripts/stop-kitty.sh"
echo ""

print_success "KITTY stack is ready!"
echo ""
