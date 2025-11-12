#!/bin/bash
# Check if llama.cpp inference is actively processing (not stuck)
# Returns: 0 if active, 1 if idle/stuck
# Usage: ./ops/scripts/check-inference-active.sh [q4|f16]

MODEL=${1:-q4}
THRESHOLD_CPU=30  # Consider "active" if CPU > 30%

if [ "$MODEL" = "q4" ]; then
    PORT=8083
    PID=$(pgrep -f "llama-server.*8083" | head -1)
elif [ "$MODEL" = "f16" ]; then
    PORT=8082
    PID=$(pgrep -f "llama-server.*8082" | head -1)
else
    echo "Usage: $0 [q4|f16]"
    exit 2
fi

if [ -z "$PID" ]; then
    echo "❌ $MODEL server not running"
    exit 1
fi

# Check CPU usage
CPU=$(ps -p $PID -o %cpu= 2>/dev/null | xargs | cut -d. -f1)

# Check active connections
CONNECTIONS=$(lsof -i :$PORT -sTCP:ESTABLISHED 2>/dev/null | grep -v COMMAND | wc -l)

# Check recent log activity (last 10 seconds)
if [ "$MODEL" = "q4" ]; then
    LOG_FILE=".logs/llamacpp-q4.log"
else
    LOG_FILE=".logs/llamacpp-f16.log"
fi

LOG_RECENT=0
if [ -f "$LOG_FILE" ]; then
    # Check if log was modified in last 10 seconds
    if [ "$(find "$LOG_FILE" -mtime -10s 2>/dev/null)" ]; then
        LOG_RECENT=1
    fi
fi

# Decision logic
ACTIVE=false

# High CPU = definitely active
if [ "$CPU" -gt "$THRESHOLD_CPU" ]; then
    ACTIVE=true
    REASON="High CPU usage: ${CPU}%"
fi

# Active connection + recent log = likely active
if [ "$CONNECTIONS" -gt 0 ] && [ "$LOG_RECENT" -eq 1 ]; then
    ACTIVE=true
    REASON="Active connection + recent log activity"
fi

# Output result
if [ "$ACTIVE" = true ]; then
    echo "✅ $MODEL inference ACTIVE: $REASON"
    echo "   CPU: ${CPU}%, Connections: $CONNECTIONS, Recent logs: $LOG_RECENT"
    exit 0
else
    echo "⚠️  $MODEL inference IDLE"
    echo "   CPU: ${CPU}%, Connections: $CONNECTIONS, Recent logs: $LOG_RECENT"
    exit 1
fi
