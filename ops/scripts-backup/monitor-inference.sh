#!/bin/bash
# Monitor llama.cpp inference activity on Mac M3 Ultra
# Usage: ./ops/scripts/monitor-inference.sh [interval_seconds]

INTERVAL=${1:-5}  # Default 5 second intervals
LOG_FILE=".logs/inference-monitor-$(date +%Y%m%d-%H%M%S).log"

echo "🔍 Starting llama.cpp inference monitoring (interval: ${INTERVAL}s)"
echo "📊 Log file: $LOG_FILE"
echo "Press Ctrl+C to stop"
echo ""

# Create logs directory if needed
mkdir -p .logs

# Header
{
    echo "==================================================="
    echo "llama.cpp Inference Activity Monitor"
    echo "Started: $(date)"
    echo "==================================================="
    echo ""
} | tee -a "$LOG_FILE"

while true; do
    TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

    # ===== GPU Monitoring (Metal on Apple Silicon) =====
    echo "[$TIMESTAMP] GPU & CPU Activity:" | tee -a "$LOG_FILE"

    # Get GPU power metrics (requires sudo on some systems)
    GPU_STATS=$(sudo powermetrics --samplers gpu_power -i 1000 -n 1 2>/dev/null | grep -A 5 "GPU Power")
    if [ -n "$GPU_STATS" ]; then
        echo "  Metal GPU:" | tee -a "$LOG_FILE"
        echo "$GPU_STATS" | sed 's/^/    /' | tee -a "$LOG_FILE"
    else
        # Fallback: basic GPU activity detection
        GPU_ACTIVE=$(ps aux | grep llama-server | grep -v grep | wc -l)
        echo "  llama-server processes active: $GPU_ACTIVE" | tee -a "$LOG_FILE"
    fi

    # ===== CPU Monitoring =====
    # Find llama-server processes
    Q4_PID=$(pgrep -f "llama-server.*8083" | head -1)
    F16_PID=$(pgrep -f "llama-server.*8082" | head -1)

    if [ -n "$Q4_PID" ]; then
        Q4_CPU=$(ps -p $Q4_PID -o %cpu= 2>/dev/null | xargs)
        Q4_MEM=$(ps -p $Q4_PID -o %mem= 2>/dev/null | xargs)
        Q4_THREADS=$(ps -p $Q4_PID -o nlwp= 2>/dev/null | xargs)
        echo "  Q4 Server (PID $Q4_PID): CPU=${Q4_CPU}%, MEM=${Q4_MEM}%, Threads=${Q4_THREADS}" | tee -a "$LOG_FILE"
    else
        echo "  Q4 Server: NOT RUNNING" | tee -a "$LOG_FILE"
    fi

    if [ -n "$F16_PID" ]; then
        F16_CPU=$(ps -p $F16_PID -o %cpu= 2>/dev/null | xargs)
        F16_MEM=$(ps -p $F16_PID -o %mem= 2>/dev/null | xargs)
        F16_THREADS=$(ps -p $F16_PID -o nlwp= 2>/dev/null | xargs)
        echo "  F16 Server (PID $F16_PID): CPU=${F16_CPU}%, MEM=${F16_MEM}%, Threads=${F16_THREADS}" | tee -a "$LOG_FILE"
    else
        echo "  F16 Server: NOT RUNNING" | tee -a "$LOG_FILE"
    fi

    # ===== Network Activity (inference in progress) =====
    # Check for active connections on llama.cpp ports
    Q4_CONNECTIONS=$(lsof -i :8083 -sTCP:ESTABLISHED 2>/dev/null | grep -v COMMAND | wc -l)
    F16_CONNECTIONS=$(lsof -i :8082 -sTCP:ESTABLISHED 2>/dev/null | grep -v COMMAND | wc -l)

    echo "  Active connections: Q4=${Q4_CONNECTIONS}, F16=${F16_CONNECTIONS}" | tee -a "$LOG_FILE"

    # ===== Inference Detection (heuristic) =====
    # High CPU + active connection = inference in progress
    Q4_INFERRING=false
    F16_INFERRING=false

    if [ -n "$Q4_CPU" ] && [ "$Q4_CONNECTIONS" -gt 0 ]; then
        Q4_CPU_INT=$(echo "$Q4_CPU" | cut -d. -f1)
        if [ "$Q4_CPU_INT" -gt 50 ]; then
            Q4_INFERRING=true
        fi
    fi

    if [ -n "$F16_CPU" ] && [ "$F16_CONNECTIONS" -gt 0 ]; then
        F16_CPU_INT=$(echo "$F16_CPU" | cut -d. -f1)
        if [ "$F16_CPU_INT" -gt 50 ]; then
            F16_INFERRING=true
        fi
    fi

    if [ "$Q4_INFERRING" = true ]; then
        echo "  ⚡ Q4 INFERENCE IN PROGRESS" | tee -a "$LOG_FILE"
    fi

    if [ "$F16_INFERRING" = true ]; then
        echo "  ⚡ F16 INFERENCE IN PROGRESS" | tee -a "$LOG_FILE"
    fi

    # ===== Recent llama.cpp Log Activity =====
    if [ -f ".logs/llamacpp-q4.log" ]; then
        Q4_LOG_LINES=$(tail -1 .logs/llamacpp-q4.log 2>/dev/null)
        if [ -n "$Q4_LOG_LINES" ]; then
            echo "  Q4 latest log: ${Q4_LOG_LINES:0:80}..." | tee -a "$LOG_FILE"
        fi
    fi

    if [ -f ".logs/llamacpp-f16.log" ]; then
        F16_LOG_LINES=$(tail -1 .logs/llamacpp-f16.log 2>/dev/null)
        if [ -n "$F16_LOG_LINES" ]; then
            echo "  F16 latest log: ${F16_LOG_LINES:0:80}..." | tee -a "$LOG_FILE"
        fi
    fi

    echo "" | tee -a "$LOG_FILE"

    # Wait for next interval
    sleep "$INTERVAL"
done
