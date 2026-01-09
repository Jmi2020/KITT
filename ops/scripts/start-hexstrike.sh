#!/bin/bash
# Start HexStrike AI Security Assessment Server
# This script starts the Flask REST API backend that the MCP client connects to

set -e

HEXSTRIKE_DIR="/Users/Shared/Coding/KITT/Reference/hexstrike-ai"
HEXSTRIKE_VENV="$HEXSTRIKE_DIR/hexstrike-env"
HEXSTRIKE_PORT="${HEXSTRIKE_PORT:-8889}"
PID_FILE="/tmp/hexstrike_server.pid"
LOG_FILE="/Users/Shared/Coding/KITT/.logs/hexstrike_server.log"

# Ensure log directory exists
mkdir -p "$(dirname "$LOG_FILE")"

# Check if already running
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if ps -p "$PID" > /dev/null 2>&1; then
        echo "HexStrike server already running (PID: $PID)"
        exit 0
    else
        rm -f "$PID_FILE"
    fi
fi

# Check if hexstrike directory exists
if [ ! -d "$HEXSTRIKE_DIR" ]; then
    echo "Error: HexStrike directory not found at $HEXSTRIKE_DIR"
    exit 1
fi

cd "$HEXSTRIKE_DIR"

# Create virtual environment if it doesn't exist
if [ ! -d "$HEXSTRIKE_VENV" ]; then
    echo "Creating HexStrike virtual environment..."
    python3 -m venv "$HEXSTRIKE_VENV"
fi

# Activate virtual environment
source "$HEXSTRIKE_VENV/bin/activate"

# Install core dependencies (skip pwntools/angr/unicorn which have build issues on macOS)
DEPS_MARKER="$HEXSTRIKE_VENV/.deps_installed"
if [ ! -f "$DEPS_MARKER" ]; then
    echo "Installing HexStrike core dependencies..."
    pip install flask requests psutil fastmcp beautifulsoup4 selenium webdriver-manager aiohttp mitmproxy Pillow lxml -q
    touch "$DEPS_MARKER"
fi

# Start the server in background
echo "Starting HexStrike server on port $HEXSTRIKE_PORT..."
nohup python3 hexstrike_server.py --port "$HEXSTRIKE_PORT" > "$LOG_FILE" 2>&1 &
SERVER_PID=$!

# Wait a moment for server to start
sleep 2

# Verify it's running
if ps -p "$SERVER_PID" > /dev/null 2>&1; then
    echo "$SERVER_PID" > "$PID_FILE"
    echo "HexStrike server started successfully (PID: $SERVER_PID)"
    echo "Log file: $LOG_FILE"

    # Try to verify the server is responding
    if curl -s "http://localhost:$HEXSTRIKE_PORT/health" > /dev/null 2>&1; then
        echo "Server health check passed"
    else
        echo "Warning: Server started but health check not responding yet"
    fi
else
    echo "Error: HexStrike server failed to start. Check $LOG_FILE for details."
    exit 1
fi
