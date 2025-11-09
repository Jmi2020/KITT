#!/usr/bin/env bash
# Dual-Model llama.cpp Server Startup
# Launches Q4 (tool orchestrator) and F16 (reasoning engine) on separate ports
set -euo pipefail

is_enabled() {
  local value="${1:-1}"
  value="$(printf '%s' "$value" | tr '[:upper:]' '[:lower:]')"
  case "$value" in
    1|true|yes|on) return 0 ;;
    *) return 1 ;;
  esac
}

LLAMACPP_BIN="${LLAMACPP_BIN:-llama-server}"
MODELS_DIR="${LLAMACPP_MODELS_DIR:-/Users/Shared/Coding/models}"

# Q4 Model Configuration (Athene V2 Agent - Port 8083)
Q4_MODEL="${LLAMACPP_Q4_MODEL:-athene-v2-agent/Athene-V2-Agent-Q4_K_M.gguf}"
Q4_ALIAS="${LLAMACPP_Q4_ALIAS:-kitty-q4}"
Q4_PORT="${LLAMACPP_Q4_PORT:-8083}"
Q4_CTX="${LLAMACPP_Q4_CTX:-16384}"
Q4_PARALLEL="${LLAMACPP_Q4_PARALLEL:-4}"
Q4_TEMPERATURE="${LLAMACPP_Q4_TEMPERATURE:-0.0}"
Q4_BATCH_SIZE="${LLAMACPP_Q4_BATCH_SIZE:-4096}"
Q4_UBATCH_SIZE="${LLAMACPP_Q4_UBATCH_SIZE:-1024}"
Q4_N_GPU_LAYERS="${LLAMACPP_Q4_N_GPU_LAYERS:-999}"
Q4_THREADS="${LLAMACPP_Q4_THREADS:-20}"
Q4_FLASH_ATTN="${LLAMACPP_Q4_FLASH_ATTN:-1}"

# F16 Model Configuration (Reasoning Engine - Port 8082)
F16_MODEL="${LLAMACPP_F16_MODEL:-llama-3-70b/Llama-3.3-70B-Instruct-F16/Llama-3.3-70B-Instruct-F16-00001-of-00004.gguf}"
F16_ALIAS="${LLAMACPP_F16_ALIAS:-kitty-f16}"
F16_PORT="${LLAMACPP_F16_PORT:-8082}"
F16_CTX="${LLAMACPP_F16_CTX:-16384}"
F16_PARALLEL="${LLAMACPP_F16_PARALLEL:-4}"
F16_TEMPERATURE="${LLAMACPP_F16_TEMPERATURE:-0.2}"
F16_BATCH_SIZE="${LLAMACPP_F16_BATCH_SIZE:-4096}"
F16_UBATCH_SIZE="${LLAMACPP_F16_UBATCH_SIZE:-1024}"
F16_N_GPU_LAYERS="${LLAMACPP_F16_N_GPU_LAYERS:-999}"
F16_THREADS="${LLAMACPP_F16_THREADS:-20}"
F16_FLASH_ATTN="${LLAMACPP_F16_FLASH_ATTN:-1}"

# Hermes Summarizer (Optional - Port 8085)
SUMMARY_ENABLED="${LLAMACPP_SUMMARY_ENABLED:-1}"
SUMMARY_MODEL="${LLAMACPP_SUMMARY_MODEL:-Hermes-3-8B/Hermes-3-Llama-3.1-8B.Q4_K_M.gguf}"
SUMMARY_ALIAS="${LLAMACPP_SUMMARY_ALIAS:-kitty-summary}"
SUMMARY_PORT="${LLAMACPP_SUMMARY_PORT:-8085}"
SUMMARY_CTX="${LLAMACPP_SUMMARY_CTX:-8192}"
SUMMARY_PARALLEL="${LLAMACPP_SUMMARY_PARALLEL:-2}"
SUMMARY_BATCH_SIZE="${LLAMACPP_SUMMARY_BATCH_SIZE:-1024}"
SUMMARY_UBATCH_SIZE="${LLAMACPP_SUMMARY_UBATCH_SIZE:-256}"
SUMMARY_N_GPU_LAYERS="${LLAMACPP_SUMMARY_N_GPU_LAYERS:-999}"
SUMMARY_THREADS="${LLAMACPP_SUMMARY_THREADS:-12}"
SUMMARY_FLASH_ATTN="${LLAMACPP_SUMMARY_FLASH_ATTN:-1}"

# Vision (Gemma 3) Server (Default ON - Port 8086)
VISION_ENABLED="${LLAMACPP_VISION_ENABLED:-1}"
VISION_MODEL="${LLAMACPP_VISION_MODEL:-gemma-3-27b-it-GGUF/gemma-3-27b-it-q4_k_m.gguf}"
VISION_MMPROJ="${LLAMACPP_VISION_MMPROJ:-gemma-3-27b-it-GGUF/gemma-3-27b-it-mmproj-bf16.gguf}"
VISION_ALIAS="${LLAMACPP_VISION_ALIAS:-kitty-vision}"
VISION_PORT="${LLAMACPP_VISION_PORT:-8086}"
VISION_CTX="${LLAMACPP_VISION_CTX:-8192}"
VISION_PARALLEL="${LLAMACPP_VISION_PARALLEL:-2}"
VISION_TEMPERATURE="${LLAMACPP_VISION_TEMPERATURE:-0.0}"
VISION_BATCH_SIZE="${LLAMACPP_VISION_BATCH_SIZE:-1024}"
VISION_UBATCH_SIZE="${LLAMACPP_VISION_UBATCH_SIZE:-256}"
VISION_N_GPU_LAYERS="${LLAMACPP_VISION_N_GPU_LAYERS:-999}"
VISION_THREADS="${LLAMACPP_VISION_THREADS:-16}"
VISION_FLASH_ATTN="${LLAMACPP_VISION_FLASH_ATTN:-1}"

# Shared Configuration
N_GPU_LAYERS="${LLAMACPP_N_GPU_LAYERS:-999}"
THREADS="${LLAMACPP_THREADS:-$(sysctl -n hw.logicalcpu)}"
FLASH_ATTN="${LLAMACPP_FLASH_ATTN:-1}"
TOOL_CALLING="${LLAMACPP_TOOL_CALLING:-1}"

# Validate binary
if ! command -v "$LLAMACPP_BIN" >/dev/null 2>&1; then
  echo "Error: llama-server binary not found (LLAMACPP_BIN=$LLAMACPP_BIN)." >&2
  exit 1
fi

# Validate Q4 model
q4_path="$MODELS_DIR/$Q4_MODEL"
if [[ ! -f "$q4_path" ]]; then
  echo "Error: Q4 model file not found at $q4_path" >&2
  exit 1
fi

# Validate F16 model
f16_path="$MODELS_DIR/$F16_MODEL"
if [[ ! -f "$f16_path" ]]; then
  echo "Error: F16 model file not found at $f16_path" >&2
  exit 1
fi

vision_enabled=false
summary_enabled=false

if is_enabled "$VISION_ENABLED"; then
  vision_enabled=true
  vision_path="$MODELS_DIR/$VISION_MODEL"
  vision_mmproj_path="$MODELS_DIR/$VISION_MMPROJ"
  if [[ ! -f "$vision_path" ]]; then
    echo "Error: Vision model file not found at $vision_path" >&2
    exit 1
  fi
  if [[ ! -f "$vision_mmproj_path" ]]; then
    echo "Error: Vision mmproj file not found at $vision_mmproj_path" >&2
    echo "Download the mmproj GGUF referenced in models/gemma-3-27b-it-GGUF/README.md or set LLAMACPP_VISION_MMPROJ." >&2
    exit 1
  fi
fi

if is_enabled "$SUMMARY_ENABLED"; then
  summary_enabled=true
fi

# Normalize flash-attn value
normalize_flash() {
  local input="${1:-}"
  local val
  val="$(printf '%s' "$input" | tr '[:upper:]' '[:lower:]')"
  case "$val" in
    1|true|on|yes) echo "on" ;;
    0|false|off|no) echo "off" ;;
    auto) echo "auto" ;;
    "" ) echo "" ;;
    *) echo "$1" ;; # pass through custom values
  esac
}

flash_value=$(normalize_flash "$FLASH_ATTN")
q4_flash_value=$(normalize_flash "$Q4_FLASH_ATTN")
f16_flash_value=$(normalize_flash "$F16_FLASH_ATTN")
summary_flash_value=$(normalize_flash "$SUMMARY_FLASH_ATTN")
vision_flash_value=$(normalize_flash "$VISION_FLASH_ATTN")

# Build Q4 command (Tool Orchestrator)
q4_cmd=(
  "$LLAMACPP_BIN"
  --port "$Q4_PORT"
  --n_gpu_layers "$Q4_N_GPU_LAYERS"
  --ctx-size "$Q4_CTX"
  --threads "$Q4_THREADS"
  --batch-size "$Q4_BATCH_SIZE"
  --ubatch-size "$Q4_UBATCH_SIZE"
  -np "$Q4_PARALLEL"
  --model "$q4_path"
  --alias "$Q4_ALIAS"
)

if [[ -n "$q4_flash_value" ]]; then
  q4_cmd+=(--flash-attn "$q4_flash_value")
fi

if [[ "$TOOL_CALLING" == "1" || "$TOOL_CALLING" == "true" ]]; then
  q4_cmd+=(--jinja)
fi

# Build F16 command (Reasoning Engine)
f16_cmd=(
  "$LLAMACPP_BIN"
  --port "$F16_PORT"
  --n_gpu_layers "$F16_N_GPU_LAYERS"
  --ctx-size "$F16_CTX"
  --threads "$F16_THREADS"
  --batch-size "$F16_BATCH_SIZE"
  --ubatch-size "$F16_UBATCH_SIZE"
  -np "$F16_PARALLEL"
  --model "$f16_path"
  --alias "$F16_ALIAS"
)

if [[ -n "$f16_flash_value" ]]; then
  f16_cmd+=(--flash-attn "$f16_flash_value")
fi

if [[ "$TOOL_CALLING" == "1" || "$TOOL_CALLING" == "true" ]]; then
  f16_cmd+=(--jinja)
fi

# Create logs directory
mkdir -p .logs

# Start Q4 server in background
echo "Starting Q4 (Tool Orchestrator) server on port $Q4_PORT:"
printf '  %q' "${q4_cmd[@]}"
echo
"${q4_cmd[@]}" > .logs/llamacpp-q4.log 2>&1 &
q4_pid=$!
echo "$q4_pid" > .logs/llamacpp-q4.pid
echo "Q4 server started (PID: $q4_pid)"

# Give Q4 a moment to bind to port
sleep 2

# Start F16 server in background
echo "Starting F16 (Reasoning Engine) server on port $F16_PORT:"
printf '  %q' "${f16_cmd[@]}"
echo
"${f16_cmd[@]}" > .logs/llamacpp-f16.log 2>&1 &
f16_pid=$!
echo "$f16_pid" > .logs/llamacpp-f16.pid
echo "F16 server started (PID: $f16_pid)"

summary_pid=""
summary_path="$MODELS_DIR/$SUMMARY_MODEL"
if $summary_enabled; then
  if [[ -f "$summary_path" ]]; then
    summary_cmd=(
      "$LLAMACPP_BIN"
      --port "$SUMMARY_PORT"
      --n_gpu_layers "$SUMMARY_N_GPU_LAYERS"
      --ctx-size "$SUMMARY_CTX"
      --threads "$SUMMARY_THREADS"
      --batch-size "$SUMMARY_BATCH_SIZE"
      --ubatch-size "$SUMMARY_UBATCH_SIZE"
      -np "$SUMMARY_PARALLEL"
      --model "$summary_path"
      --alias "$SUMMARY_ALIAS"
    )

    if [[ -n "$summary_flash_value" ]]; then
      summary_cmd+=(--flash-attn "$summary_flash_value")
    fi

    echo "Starting Hermes summarizer on port $SUMMARY_PORT:"
    printf '  %q' "${summary_cmd[@]}"
    echo
    "${summary_cmd[@]}" > .logs/llamacpp-summary.log 2>&1 &
    summary_pid=$!
    echo "$summary_pid" > .logs/llamacpp-summary.pid
    echo "Summary server started (PID: $summary_pid)"
  else
    echo "Warning: Hermes summary model not found at $summary_path (summary disabled)"
    summary_enabled=false
  fi
fi

# Start Gemma vision server if enabled
vision_pid=""
if $vision_enabled; then
  vision_cmd=(
    "$LLAMACPP_BIN"
    --port "$VISION_PORT"
    --n_gpu_layers "$VISION_N_GPU_LAYERS"
    --ctx-size "$VISION_CTX"
    --threads "$VISION_THREADS"
    --batch-size "$VISION_BATCH_SIZE"
    --ubatch-size "$VISION_UBATCH_SIZE"
    -np "$VISION_PARALLEL"
    --model "$vision_path"
    --mmproj "$vision_mmproj_path"
    --alias "$VISION_ALIAS"
  )

  if [[ -n "$vision_flash_value" ]]; then
    vision_cmd+=(--flash-attn "$vision_flash_value")
  fi

  echo "Starting Gemma vision server on port $VISION_PORT:"
  printf '  %q' "${vision_cmd[@]}"
  echo
  "${vision_cmd[@]}" > .logs/llamacpp-vision.log 2>&1 &
  vision_pid=$!
  echo "$vision_pid" > .logs/llamacpp-vision.pid
  echo "Vision server started (PID: $vision_pid)"
fi

# Setup cleanup handler
cleanup() {
  echo "Stopping llama.cpp servers..."
  if [[ -n "${q4_pid:-}" ]]; then
    kill "$q4_pid" 2>/dev/null || true
  fi
  if [[ -n "${f16_pid:-}" ]]; then
    kill "$f16_pid" 2>/dev/null || true
  fi
  if [[ -n "${summary_pid:-}" ]]; then
    kill "$summary_pid" 2>/dev/null || true
  fi
  if [[ -n "${vision_pid:-}" ]]; then
    kill "$vision_pid" 2>/dev/null || true
  fi
  rm -f .logs/llamacpp-q4.pid .logs/llamacpp-f16.pid .logs/llamacpp-summary.pid .logs/llamacpp-vision.pid
  echo "Servers stopped"
}

trap cleanup EXIT INT TERM

# Wait for processes
echo "Servers running. Press Ctrl+C to stop."
log_paths=(".logs/llamacpp-q4.log" ".logs/llamacpp-f16.log")
if [[ -n "$summary_pid" ]]; then
  log_paths+=(".logs/llamacpp-summary.log")
fi
if [[ -n "$vision_pid" ]]; then
  log_paths+=(".logs/llamacpp-vision.log")
fi
echo "Logs: ${log_paths[*]}"

pids=("$q4_pid" "$f16_pid")
if [[ -n "$summary_pid" ]]; then
  pids+=("$summary_pid")
fi
if [[ -n "$vision_pid" ]]; then
  pids+=("$vision_pid")
fi

wait "${pids[@]}"
