#!/usr/bin/env bash
# GPU performance benchmark for llama.cpp (dual-model architecture)
# Tests throughput with various prompt sizes and measures GPU utilization
# Usage: ./benchmark-llamacpp.sh [q4|f16|both] [model-alias]

set -euo pipefail

# Default to benchmarking both models
MODE="${1:-both}"
MODEL_ALIAS="${2:-}"

# Determine which hosts to benchmark based on mode
case "$MODE" in
  q4)
    HOSTS=("http://localhost:8083")
    ALIASES=("${MODEL_ALIAS:-kitty-q4}")
    NAMES=("Q4 (Tool Orchestrator)")
    ;;
  f16)
    HOSTS=("http://localhost:8082")
    ALIASES=("${MODEL_ALIAS:-kitty-f16}")
    NAMES=("F16 (Reasoning Engine)")
    ;;
  both)
    HOSTS=("http://localhost:8083" "http://localhost:8082")
    ALIASES=("${MODEL_ALIAS:-kitty-q4}" "${MODEL_ALIAS:-kitty-f16}")
    NAMES=("Q4 (Tool Orchestrator)" "F16 (Reasoning Engine)")
    ;;
  *)
    echo "Usage: $0 [q4|f16|both] [model-alias]" >&2
    echo "  q4:   Benchmark Q4 server only (port 8083)" >&2
    echo "  f16:  Benchmark F16 server only (port 8082)" >&2
    echo "  both: Benchmark both servers (default)" >&2
    exit 1
    ;;
esac

OUTPUT_FILE="benchmark-results-$(date +%Y%m%d-%H%M%S).txt"

echo "===========================================" | tee "$OUTPUT_FILE"
echo "llama.cpp Dual-Model GPU Benchmark" | tee -a "$OUTPUT_FILE"
echo "===========================================" | tee -a "$OUTPUT_FILE"
echo "Mode: $MODE" | tee -a "$OUTPUT_FILE"
echo "Date: $(date)" | tee -a "$OUTPUT_FILE"
echo "" | tee -a "$OUTPUT_FILE"

# Function to run a benchmark test
benchmark_test() {
  local host="$1"
  local model_alias="$2"
  local name="$3"
  local prompt="$4"
  local n_predict="${5:-128}"

  echo "Test: $name" | tee -a "$OUTPUT_FILE"
  echo "Host: $host" | tee -a "$OUTPUT_FILE"
  echo "Model: $model_alias" | tee -a "$OUTPUT_FILE"
  echo "Prompt length: ${#prompt} chars" | tee -a "$OUTPUT_FILE"
  echo "Generating $n_predict tokens..." | tee -a "$OUTPUT_FILE"

  # Start GPU monitoring in background
  if command -v powermetrics >/dev/null 2>&1; then
    sudo powermetrics -i 1000 -n 15 --samplers gpu_power 2>/dev/null | grep -E "GPU Power|GPU Active" > "gpu-metrics-$name.txt" &
    METRICS_PID=$!
  fi

  # Run the completion request
  start_time=$(date +%s.%N)

  response=$(curl -s -X POST "$host/v1/completions" \
    -H "Content-Type: application/json" \
    -d "{
      \"model\": \"$model_alias\",
      \"prompt\": \"$prompt\",
      \"max_tokens\": $n_predict,
      \"temperature\": 0.7,
      \"stream\": false
    }")

  end_time=$(date +%s.%N)

  # Stop GPU monitoring
  if [ -n "${METRICS_PID:-}" ]; then
    sleep 2
    sudo kill -TERM "$METRICS_PID" 2>/dev/null || true
    wait "$METRICS_PID" 2>/dev/null || true
  fi

  # Calculate metrics
  elapsed=$(echo "$end_time - $start_time" | bc)

  # Extract token count from response
  tokens=$(echo "$response" | python3 -c "import json,sys; data=json.load(sys.stdin); print(data.get('usage',{}).get('completion_tokens', 0))" 2>/dev/null || echo "0")

  if [ "$tokens" -gt 0 ]; then
    tokens_per_sec=$(echo "scale=2; $tokens / $elapsed" | bc)
    echo "Tokens generated: $tokens" | tee -a "$OUTPUT_FILE"
    echo "Time elapsed: ${elapsed}s" | tee -a "$OUTPUT_FILE"
    echo "Throughput: ${tokens_per_sec} tokens/sec" | tee -a "$OUTPUT_FILE"
  else
    echo "ERROR: Failed to generate tokens" | tee -a "$OUTPUT_FILE"
    echo "Response: $response" | tee -a "$OUTPUT_FILE"
  fi

  echo "" | tee -a "$OUTPUT_FILE"
}

# Benchmark all configured servers
for i in "${!HOSTS[@]}"; do
  host="${HOSTS[$i]}"
  alias="${ALIASES[$i]}"
  name="${NAMES[$i]}"

  echo "=========================================" | tee -a "$OUTPUT_FILE"
  echo "Benchmarking: $name" | tee -a "$OUTPUT_FILE"
  echo "=========================================" | tee -a "$OUTPUT_FILE"

  # Check if server is running
  if ! curl -s "$host/health" >/dev/null 2>&1; then
    echo "ERROR: Server not responding at $host" | tee -a "$OUTPUT_FILE"
    echo "Skipping $name..." | tee -a "$OUTPUT_FILE"
    echo "" | tee -a "$OUTPUT_FILE"
    continue
  fi

  echo "Server is responding. Starting benchmark tests..." | tee -a "$OUTPUT_FILE"
  echo "" | tee -a "$OUTPUT_FILE"

  # Test 1: Short prompt (prefill test)
  benchmark_test "$host" "$alias" "short-prompt-${alias}" \
    "What is the capital of France?" \
    64

  # Test 2: Medium prompt (balanced test)
  benchmark_test "$host" "$alias" "medium-prompt-${alias}" \
    "Explain the concept of GPU offloading in machine learning models. Include details about memory transfer, compute efficiency, and the differences between CPU and GPU execution." \
    128

  # Test 3: Long prompt (prefill stress test)
  long_prompt="Context: $(printf 'This is background information about a complex topic. %.0s' {1..50}) Question: Based on this context, provide a detailed analysis."
  benchmark_test "$host" "$alias" "long-prompt-${alias}" \
    "$long_prompt" \
    128

  # Test 4: Generation test (decode stress test)
  benchmark_test "$host" "$alias" "generation-test-${alias}" \
    "Write a detailed technical explanation of neural network inference:" \
    256

  echo "" | tee -a "$OUTPUT_FILE"
done

echo "===========================================" | tee -a "$OUTPUT_FILE"
echo "Benchmark Complete" | tee -a "$OUTPUT_FILE"
echo "Results saved to: $OUTPUT_FILE" | tee -a "$OUTPUT_FILE"
echo "===========================================" | tee -a "$OUTPUT_FILE"

# Display GPU metrics summary if available
if ls gpu-metrics-*.txt >/dev/null 2>&1; then
  echo "" | tee -a "$OUTPUT_FILE"
  echo "GPU Metrics Summary:" | tee -a "$OUTPUT_FILE"
  for metrics_file in gpu-metrics-*.txt; do
    test_name=$(basename "$metrics_file" .txt | sed 's/gpu-metrics-//')
    echo "  $test_name:" | tee -a "$OUTPUT_FILE"
    if [ -s "$metrics_file" ]; then
      grep "GPU Active" "$metrics_file" | tail -5 | tee -a "$OUTPUT_FILE" || echo "    No GPU metrics captured" | tee -a "$OUTPUT_FILE"
    else
      echo "    No GPU metrics captured" | tee -a "$OUTPUT_FILE"
    fi
  done
fi

echo ""
echo "To compare before/after results:"
echo "  1. Run this benchmark with old configuration"
echo "  2. Restart llama.cpp with new GPU-optimized configuration"
echo "  3. Run this benchmark again"
echo "  4. Compare tokens/sec metrics between runs"
echo ""
echo "Expected improvements with GPU optimization:"
echo "  - 10-30x faster throughput"
echo "  - 70-85% GPU utilization (vs 5% before)"
echo "  - 5-10ms/token prefill latency (vs 200-500ms)"
