#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Stop Ollama daemon gracefully

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

log() {
    echo -e "${GREEN}[Ollama]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[Ollama]${NC} $1"
}

error() {
    echo -e "${RED}[Ollama]${NC} $1"
}

# Load environment for host/model hints
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

# Ollama host (for CLI)
export OLLAMA_HOST="${OLLAMA_HOST:-http://localhost:11434}"

# Default models to stop (GPT-OSS stacks)
DEFAULT_MODELS=("gpt-oss:120b" "gpt-oss-120b-judge:latest" "gpt-oss-120b-judge")

ensure_ollama() {
    if ! command -v ollama >/dev/null 2>&1; then
        warn "Ollama CLI not found; nothing to stop"
        exit 0
    fi
}

running_models() {
    # Returns unique list of running model names
    OLLAMA_HOST="$OLLAMA_HOST" ollama ps 2>/dev/null | awk 'NR>1 && $1 != "" {print $1}' | sort -u
}

stop_model() {
    local model="$1"
    log "Stopping model: $model"
    if ! OLLAMA_HOST="$OLLAMA_HOST" ollama stop "$model" >/dev/null 2>&1; then
        warn "Could not stop $model (may already be stopped)"
    fi
}

ensure_ollama

# Build target list: running models + known GPT-OSS defaults + env override
targets=()
running_models_list=$(running_models || true)
for m in $running_models_list; do
    targets+=("$m")
done

if [ -n "${OLLAMA_MODEL:-}" ]; then
    targets+=("$OLLAMA_MODEL")
fi

if [ -n "${OLLAMA_MODELS_TO_STOP:-}" ]; then
    # Space-separated list from env
    for m in $OLLAMA_MODELS_TO_STOP; do
        targets+=("$m")
    done
fi

targets+=("${DEFAULT_MODELS[@]}")

# Deduplicate
unique_targets=()
seen=""
for m in "${targets[@]}"; do
    [ -z "$m" ] && continue
    case " $seen " in
        *" $m "*) ;;
        *)
            seen="$seen $m"
            unique_targets+=("$m")
            ;;
    esac
done

if [ ${#unique_targets[@]} -eq 0 ]; then
    log "No running Ollama models found"
    exit 0
fi

for model in "${unique_targets[@]}"; do
    stop_model "$model"
done

# Final check
remaining_list=$(running_models || true)
if [ -n "$remaining_list" ]; then
    warn "Some Ollama models are still running: $remaining_list"
    exit 1
fi

log "✓ Ollama models stopped (daemon remains available)"
