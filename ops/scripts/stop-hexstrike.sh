#!/bin/bash
# Stop HexStrike AI Security Assessment Server

set -e

PID_FILE="/tmp/hexstrike_server.pid"

if [ ! -f "$PID_FILE" ]; then
    echo "HexStrike server is not running (no PID file found)"
    exit 0
fi

PID=$(cat "$PID_FILE")

if ps -p "$PID" > /dev/null 2>&1; then
    echo "Stopping HexStrike server (PID: $PID)..."
    kill "$PID"

    # Wait for graceful shutdown
    TIMEOUT=10
    while [ $TIMEOUT -gt 0 ] && ps -p "$PID" > /dev/null 2>&1; do
        sleep 1
        TIMEOUT=$((TIMEOUT - 1))
    done

    # Force kill if still running
    if ps -p "$PID" > /dev/null 2>&1; then
        echo "Server not responding, force killing..."
        kill -9 "$PID" 2>/dev/null || true
    fi

    rm -f "$PID_FILE"
    echo "HexStrike server stopped"
else
    echo "HexStrike server is not running (stale PID file)"
    rm -f "$PID_FILE"
fi
