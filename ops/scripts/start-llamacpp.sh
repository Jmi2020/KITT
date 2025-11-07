#!/usr/bin/env bash
set -euo pipefail

LLAMACPP_BIN="${LLAMACPP_BIN:-llama-server}"
MODELS_DIR="${LLAMACPP_MODELS_DIR:-/Users/Shared/Coding/models}"
PRIMARY_MODEL="${LLAMACPP_PRIMARY_MODEL:-}"
PRIMARY_ALIAS="${LLAMACPP_PRIMARY_ALIAS:-kitty-primary}"
CODER_MODEL="${LLAMACPP_CODER_MODEL:-}"
CODER_ALIAS="${LLAMACPP_CODER_ALIAS:-kitty-coder}"
PORT="${LLAMACPP_PORT:-8080}"
CTX_SIZE="${LLAMACPP_CTX:-8192}"
N_GPU_LAYERS="${LLAMACPP_N_GPU_LAYERS:-999}"
THREADS="${LLAMACPP_THREADS:-$(sysctl -n hw.logicalcpu)}"
FLASH_ATTN="${LLAMACPP_FLASH_ATTN:-1}"
TOOL_CALLING="${LLAMACPP_TOOL_CALLING:-1}"
BATCH_SIZE="${LLAMACPP_BATCH_SIZE:-4096}"
UBATCH_SIZE="${LLAMACPP_UBATCH_SIZE:-1024}"
PARALLEL="${LLAMACPP_PARALLEL:-6}"
EXTRA_ARGS="${LLAMACPP_EXTRA_ARGS:-}"

if ! command -v "$LLAMACPP_BIN" >/dev/null 2>&1; then
  echo "Error: llama-server binary not found (LLAMACPP_BIN=$LLAMACPP_BIN)." >&2
  exit 1
fi

if [[ -z "$PRIMARY_MODEL" ]]; then
  echo "Error: LLAMACPP_PRIMARY_MODEL is required (relative path under $MODELS_DIR)." >&2
  exit 1
fi

primary_path="$MODELS_DIR/$PRIMARY_MODEL"
if [[ ! -f "$primary_path" ]]; then
  echo "Error: primary model file not found at $primary_path" >&2
  exit 1
fi

cmd=(
  "$LLAMACPP_BIN"
  --port "$PORT"
  --n_gpu_layers "$N_GPU_LAYERS"
  --ctx-size "$CTX_SIZE"
  --threads "$THREADS"
  --batch-size "$BATCH_SIZE"
  --ubatch-size "$UBATCH_SIZE"
  -np "$PARALLEL"
  --model "$primary_path"
  --alias "$PRIMARY_ALIAS"
)

if [[ -n "$CODER_MODEL" ]]; then
  coder_path="$MODELS_DIR/$CODER_MODEL"
  if [[ ! -f "$coder_path" ]]; then
    echo "Error: coder model file not found at $coder_path" >&2
    exit 1
  fi
  cmd+=(--model "$coder_path" --alias "$CODER_ALIAS")
fi

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
if [[ -n "$flash_value" ]]; then
  cmd+=(--flash-attn "$flash_value")
fi

if [[ "$TOOL_CALLING" == "1" || "$TOOL_CALLING" == "true" ]]; then
  cmd+=(--jinja -fa)
  echo "Tool calling enabled: --jinja -fa"
fi

if [[ -n "$EXTRA_ARGS" ]]; then
  # shellcheck disable=SC2206
  extra_parts=($EXTRA_ARGS)
  cmd+=("${extra_parts[@]}")
fi

echo "Starting llama.cpp server:"
printf '  %q' "${cmd[@]}"
echo

exec "${cmd[@]}"
