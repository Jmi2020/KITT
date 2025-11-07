#!/usr/bin/env bash
# Dual-Model llama.cpp Server Startup
# Launches Q4 (tool orchestrator) and F16 (reasoning engine) on separate ports
set -euo pipefail

LLAMACPP_BIN="${LLAMACPP_BIN:-llama-server}"
MODELS_DIR="${LLAMACPP_MODELS_DIR:-/Users/Shared/Coding/models}"

# Q4 Model Configuration (Tool Orchestrator - Port 8083)
Q4_MODEL="${LLAMACPP_Q4_MODEL:-llama-3-70b/Llama-3.3-70B-Instruct-UD-Q4_K_XL.gguf}"
Q4_ALIAS="${LLAMACPP_Q4_ALIAS:-kitty-q4}"
Q4_PORT="${LLAMACPP_Q4_PORT:-8083}"
Q4_CTX="${LLAMACPP_Q4_CTX:-8192}"
Q4_PARALLEL="${LLAMACPP_Q4_PARALLEL:-4}"
Q4_TEMPERATURE="${LLAMACPP_Q4_TEMPERATURE:-0.1}"
Q4_BATCH_SIZE="${LLAMACPP_Q4_BATCH_SIZE:-4096}"
Q4_UBATCH_SIZE="${LLAMACPP_Q4_UBATCH_SIZE:-1024}"

# F16 Model Configuration (Reasoning Engine - Port 8082)
F16_MODEL="${LLAMACPP_F16_MODEL:-llama-3-70b/Llama-3.3-70B-Instruct-F16/Llama-3.3-70B-Instruct-F16-00001-of-00004.gguf}"
F16_ALIAS="${LLAMACPP_F16_ALIAS:-kitty-f16}"
F16_PORT="${LLAMACPP_F16_PORT:-8082}"
F16_CTX="${LLAMACPP_F16_CTX:-16384}"
F16_PARALLEL="${LLAMACPP_F16_PARALLEL:-2}"
F16_TEMPERATURE="${LLAMACPP_F16_TEMPERATURE:-0.2}"
F16_BATCH_SIZE="${LLAMACPP_F16_BATCH_SIZE:-2048}"
F16_UBATCH_SIZE="${LLAMACPP_F16_UBATCH_SIZE:-512}"

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

# Build Q4 command (Tool Orchestrator)
q4_cmd=(
  "$LLAMACPP_BIN"
  --port "$Q4_PORT"
  --n_gpu_layers "$N_GPU_LAYERS"
  --ctx-size "$Q4_CTX"
  --threads "$THREADS"
  --batch-size "$Q4_BATCH_SIZE"
  --ubatch-size "$Q4_UBATCH_SIZE"
  -np "$Q4_PARALLEL"
  --model "$q4_path"
  --alias "$Q4_ALIAS"
)

if [[ -n "$flash_value" ]]; then
  q4_cmd+=(--flash-attn "$flash_value")
fi

if [[ "$TOOL_CALLING" == "1" || "$TOOL_CALLING" == "true" ]]; then
  q4_cmd+=(--jinja)
fi

# Build F16 command (Reasoning Engine)
f16_cmd=(
  "$LLAMACPP_BIN"
  --port "$F16_PORT"
  --n_gpu_layers "$N_GPU_LAYERS"
  --ctx-size "$F16_CTX"
  --threads "$THREADS"
  --batch-size "$F16_BATCH_SIZE"
  --ubatch-size "$F16_UBATCH_SIZE"
  -np "$F16_PARALLEL"
  --model "$f16_path"
  --alias "$F16_ALIAS"
)

if [[ -n "$flash_value" ]]; then
  f16_cmd+=(--flash-attn "$flash_value")
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

# Setup cleanup handler
cleanup() {
  echo "Stopping llama.cpp servers..."
  if [[ -n "${q4_pid:-}" ]]; then
    kill "$q4_pid" 2>/dev/null || true
  fi
  if [[ -n "${f16_pid:-}" ]]; then
    kill "$f16_pid" 2>/dev/null || true
  fi
  rm -f .logs/llamacpp-q4.pid .logs/llamacpp-f16.pid
  echo "Servers stopped"
}

trap cleanup EXIT INT TERM

# Wait for both processes
echo "Dual-model servers running. Press Ctrl+C to stop."
echo "Logs: .logs/llamacpp-q4.log and .logs/llamacpp-f16.log"

# Wait for both PIDs
wait "$q4_pid" "$f16_pid"
