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
N_GPU_LAYERS="${LLAMACPP_N_GPU_LAYERS:-1}"
THREADS="${LLAMACPP_THREADS:-$(sysctl -n hw.logicalcpu)}"
FLASH_ATTN="${LLAMACPP_FLASH_ATTN:-1}"
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

if [[ "$FLASH_ATTN" == "1" || "$FLASH_ATTN" == "true" ]]; then
  cmd+=(--flash-attn)
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
