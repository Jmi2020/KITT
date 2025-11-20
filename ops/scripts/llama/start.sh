#!/bin/bash
# Start all llama.cpp servers (Q4, F16, Summary, Vision)
# Based on start-llamacpp-dual.sh with enhancements

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
cd "$PROJECT_ROOT"

# Load environment
if [ ! -f .env ]; then
    echo "Error: .env file not found"
    exit 1
fi

set -a
source .env
set +a

# Logging
LOG_DIR="$PROJECT_ROOT/.logs"
mkdir -p "$LOG_DIR"

# Color output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

log() {
    echo -e "${BLUE}[$(date '+%H:%M:%S')]${NC} $1"
}

success() {
    echo -e "${GREEN}✓${NC} $1"
}

# ========================================
# Server Configuration
# ========================================

# Q4 Server (Fast Tool Orchestrator)
Q4_MODEL="${LLAMACPP_Q4_MODEL:-athene-v2-agent/Athene-V2-Agent-Q4_K_M.gguf}"
Q4_PORT="${LLAMACPP_Q4_PORT:-8083}"
Q4_ALIAS="${LLAMACPP_Q4_ALIAS:-kitty-q4}"
Q4_CTX_SIZE="${LLAMACPP_Q4_CTX:-8192}"
Q4_N_PARALLEL="${LLAMACPP_Q4_PARALLEL:-4}"
Q4_LOG="$LOG_DIR/llamacpp-q4.log"
Q4_PID="$LOG_DIR/llamacpp-q4.pid"

# F16 Server (Deep Reasoning Engine)
F16_MODEL="${LLAMACPP_F16_MODEL:-llama-3.3-70b/Llama-3.3-70B-Instruct-F16.gguf}"
F16_PORT="${LLAMACPP_F16_PORT:-8082}"
F16_ALIAS="${LLAMACPP_F16_ALIAS:-kitty-f16}"
F16_CTX_SIZE="${LLAMACPP_F16_CTX:-8192}"
F16_N_PARALLEL="${LLAMACPP_F16_PARALLEL:-2}"
F16_LOG="$LOG_DIR/llamacpp-f16.log"
F16_PID="$LOG_DIR/llamacpp-f16.pid"

# Summary Server (Text Summarization - Hermes 3)
SUMMARY_MODEL="${LLAMACPP_SUMMARY_MODEL:-Hermes-3-8B/Hermes-3-Llama-3.1-8B.Q4_K_M.gguf}"
SUMMARY_PORT="${LLAMACPP_SUMMARY_PORT:-8084}"
SUMMARY_ALIAS="${LLAMACPP_SUMMARY_ALIAS:-kitty-summary}"
SUMMARY_LOG="$LOG_DIR/llamacpp-summary.log"
SUMMARY_PID="$LOG_DIR/llamacpp-summary.pid"

# Vision Server (Multimodal)
VISION_MODEL="${LLAMACPP_VISION_MODEL:-llama-3.2-11b-vision/Llama-3.2-11B-Vision-Instruct-Q4_K_M.gguf}"
VISION_MMPROJ="${LLAMACPP_VISION_MMPROJ:-llama-3.2-11b-vision/mmproj-model-f16.gguf}"
VISION_PORT="${LLAMACPP_VISION_PORT:-8085}"
VISION_ALIAS="${LLAMACPP_VISION_ALIAS:-kitty-vision}"
VISION_LOG="$LOG_DIR/llamacpp-vision.log"
VISION_PID="$LOG_DIR/llamacpp-vision.pid"

# Model base directory
MODEL_BASE="${MODEL_BASE:-/Users/Shared/Coding/models}"

# ========================================
# Check if already running
# ========================================

check_running() {
    local port=$1
    if lsof -Pi :$port -sTCP:LISTEN -t > /dev/null 2>&1; then
        return 0  # Running
    else
        return 1  # Not running
    fi
}

if check_running $Q4_PORT; then
    log "Q4 server already running on port $Q4_PORT"
else
    log "Starting Q4 server (Tool Orchestrator) on port $Q4_PORT"

    llama-server \
        --model "$MODEL_BASE/$Q4_MODEL" \
        --host 0.0.0.0 \
        --port $Q4_PORT \
        --n-gpu-layers 999 \
        --ctx-size $Q4_CTX_SIZE \
        -np $Q4_N_PARALLEL \
        --batch-size 512 \
        --threads 8 \
        --alias "$Q4_ALIAS" \
        --jinja \
        --flash-attn on \
        > "$Q4_LOG" 2>&1 &

    echo $! > "$Q4_PID"
    success "Q4 server starting (PID $(cat $Q4_PID))"
    log "  Logs: $Q4_LOG"
fi

# Skip F16 if using Ollama as the reasoner provider
LOCAL_REASONER_PROVIDER="${LOCAL_REASONER_PROVIDER:-llamacpp}"

if [ "$LOCAL_REASONER_PROVIDER" == "ollama" ]; then
    log "Skipping F16 server (using Ollama as reasoner provider)"
else
    if check_running $F16_PORT; then
        log "F16 server already running on port $F16_PORT"
    else
        log "Starting F16 server (Deep Reasoner) on port $F16_PORT"

        llama-server \
            --model "$MODEL_BASE/$F16_MODEL" \
            --host 0.0.0.0 \
            --port $F16_PORT \
            --n-gpu-layers 999 \
            --ctx-size $F16_CTX_SIZE \
            -np $F16_N_PARALLEL \
            --batch-size 512 \
            --threads 12 \
            --alias "$F16_ALIAS" \
            --jinja \
            --flash-attn on \
            > "$F16_LOG" 2>&1 &

        echo $! > "$F16_PID"
        success "F16 server starting (PID $(cat $F16_PID))"
        log "  Logs: $F16_LOG"
    fi
fi

if check_running $SUMMARY_PORT; then
    log "Summary server already running on port $SUMMARY_PORT"
else
    log "Starting Summary server on port $SUMMARY_PORT"

    llama-server \
        --model "$MODEL_BASE/$SUMMARY_MODEL" \
        --host 0.0.0.0 \
        --port $SUMMARY_PORT \
        --n-gpu-layers 999 \
        --ctx-size 4096 \
        -np 4 \
        --batch-size 512 \
        --threads 4 \
        --alias "$SUMMARY_ALIAS" \
        > "$SUMMARY_LOG" 2>&1 &

    echo $! > "$SUMMARY_PID"
    success "Summary server starting (PID $(cat $SUMMARY_PID))"
    log "  Logs: $SUMMARY_LOG"
fi

if check_running $VISION_PORT; then
    log "Vision server already running on port $VISION_PORT"
else
    log "Starting Vision server on port $VISION_PORT"

    llama-server \
        --model "$MODEL_BASE/$VISION_MODEL" \
        --mmproj "$MODEL_BASE/$VISION_MMPROJ" \
        --host 0.0.0.0 \
        --port $VISION_PORT \
        --n-gpu-layers 999 \
        --ctx-size 4096 \
        -np 2 \
        --batch-size 256 \
        --threads 6 \
        --alias "$VISION_ALIAS" \
        > "$VISION_LOG" 2>&1 &

    echo $! > "$VISION_PID"
    success "Vision server starting (PID $(cat $VISION_PID))"
    log "  Logs: $VISION_LOG"
fi

echo ""
log "All llama.cpp servers starting (models loading, ~5 minutes)"
log "Monitor progress: tail -f $LOG_DIR/llamacpp-*.log"
echo ""

exit 0
