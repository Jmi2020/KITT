#!/usr/bin/env bash
set -euo pipefail

# Source the environment
set -a
source /Users/Shared/Coding/KITT/.env
set +a

# Export port
export LLAMACPP_PORT=8082

# Start llama.cpp
exec ./ops/scripts/start-llamacpp.sh
