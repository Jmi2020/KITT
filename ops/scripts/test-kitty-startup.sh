#!/usr/bin/env bash
# Test script for dual-model KITTY startup
# This script tests the dual-model llama.cpp server startup

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Source the environment
set -a
source "$REPO_ROOT/.env"
set +a

echo "Testing dual-model llama.cpp startup..."
echo "Q4 (Tool Orchestrator): Port ${LLAMACPP_Q4_PORT:-8083}"
echo "F16 (Reasoning Engine): Port ${LLAMACPP_F16_PORT:-8082}"

# Start dual-model servers
exec "$SCRIPT_DIR/start-llamacpp-dual.sh"
