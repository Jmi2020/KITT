# KITTY Operations Scripts

Organized collection of scripts for managing KITTY services, llama.cpp servers, monitoring, and utilities.

**Last Updated**: 2025-11-12
**Backup Location**: `ops/scripts-backup/` (all original scripts preserved)

---

## Directory Structure

```
ops/scripts/
├── start-all.sh                # ⭐ Start all services (llama.cpp + Docker)
├── stop-all.sh                 # ⭐ Stop all services
├── start-images-service.sh     # Start Stable Diffusion service
├── stop-images-service.sh      # Stop Stable Diffusion service
├── llama/
│   ├── start.sh               # Start all llama.cpp servers (Q4, F16, Summary, Vision)
│   └── stop.sh                # Stop all llama.cpp servers
├── monitor/
│   ├── inference.sh           # Real-time GPU/CPU/network monitoring
│   └── check-active.sh        # Check if inference is active (not stuck)
├── utils/
│   ├── benchmark-llamacpp.sh  # Benchmark llama.cpp performance
│   ├── memory-snapshot.sh     # Capture system memory snapshot
│   ├── test-startup.sh        # Test KITTY startup procedure
│   ├── watchdog-llama.sh      # Auto-restart llama.cpp on failure
│   ├── metrics-dashboard.sh   # Display metrics dashboard
│   ├── notify.sh              # Send notifications (Slack/email)
│   └── generate-kb-content.py # Generate knowledge base content
└── setup/
    └── artifacts-dir.sh       # Setup artifacts directory structure
```

---

## Quick Start

### Start Everything

```bash
# Start all KITTY services with validation
./ops/scripts/start-all.sh

# What it does:
# 1. Starts llama.cpp servers (Q4, F16, Summary, Vision)
# 2. Waits for models to load (~5 minutes)
# 3. Starts Docker Compose services
# 4. Validates all services are healthy
# 5. Displays access URLs and monitoring instructions
```

### Stop Everything

```bash
# Stop all services gracefully
./ops/scripts/stop-all.sh

# What it does:
# 1. Stops Docker Compose services
# 2. Stops all llama.cpp servers gracefully
# 3. Verifies all processes terminated
```

---

## Core Scripts

### start-all.sh

**Purpose**: Unified startup script with comprehensive validation

**Features**:
- Sequential startup: llama.cpp → Docker → validation
- Health checks for all critical services
- Logs startup progress to `.logs/startup-YYYYMMDD-HHMMSS.log`
- Waits for llama.cpp models to load (up to 10 minutes)
- Validates LangGraph initialization
- Displays service URLs and monitoring commands
- Keeps running if interactive (Ctrl+C to stop)

**Usage**:
```bash
# Interactive mode (stays running)
./ops/scripts/start-all.sh

# Detached mode (via cron/systemd)
./ops/scripts/start-all.sh > /dev/null 2>&1 &
```

**Troubleshooting**:
```bash
# Check startup logs
tail -f .logs/startup-*.log

# If llama.cpp fails to start
cat .logs/llamacpp-*.log | grep -i error
```

### stop-all.sh

**Purpose**: Gracefully stop all KITTY services

**Features**:
- Stops Docker services first (safer)
- Gracefully terminates llama.cpp servers (SIGTERM → SIGKILL)
- Cleans up PID files
- Verifies all processes stopped

**Usage**:
```bash
./ops/scripts/stop-all.sh

# Force stop if graceful fails
./ops/scripts/stop-all.sh
pkill -9 -f llama-server  # Nuclear option
```

---

## llama.cpp Management

### llama/start.sh

**Purpose**: Start all llama.cpp inference servers

**Servers Started**:
1. **Q4 (Port 8083)**: Tool orchestrator - Athene-V2-Agent Q4_K_M
2. **F16 / Ollama**: Deep reasoner - GPT-OSS 120B via Ollama (when LOCAL_REASONER_PROVIDER=ollama) or Llama-3.3-70B F16 via llama.cpp (Port 8082)
3. **Summary (Port 8084)**: Text summarization - Llama-3.2-3B Q4_K_M
4. **Vision (Port 8085)**: Multimodal - Llama-3.2-11B-Vision Q4_K_M

**Configuration**:
- Reads from `.env` for model paths, ports, aliases
- Logs to `.logs/llamacpp-*.log`
- PID files in `.logs/llamacpp-*.pid`
- Skips servers already running on target ports

**Usage**:
```bash
# Start all servers
./ops/scripts/llama/start.sh

# Monitor loading progress
tail -f .logs/llamacpp-q4.log   # Q4 server
tail -f .logs/llamacpp-f16.log  # F16 server

# Verify health
curl http://localhost:8083/health  # Q4
curl http://localhost:8082/health  # F16
```

**Customization** (via .env):
```bash
# Reasoner provider selection
LOCAL_REASONER_PROVIDER=ollama     # Use Ollama for F16 reasoner (default)
                                   # Set to "llamacpp" to use llama.cpp F16 server instead

# Ollama configuration (when LOCAL_REASONER_PROVIDER=ollama)
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=gpt-oss:120b          # GPT-OSS 120B with thinking mode
OLLAMA_THINK=high                  # Thinking effort level (low/medium/high)

# Model paths (llama.cpp)
LLAMACPP_Q4_MODEL=athene-v2-agent/Athene-V2-Agent-Q4_K_M.gguf
LLAMACPP_F16_MODEL=llama-3.3-70b/Llama-3.3-70B-Instruct-F16.gguf  # Fallback when LOCAL_REASONER_PROVIDER=llamacpp

# Performance tuning
LLAMACPP_Q4_N_PARALLEL=4          # Concurrent requests
LLAMACPP_F16_N_PARALLEL=2         # Lower for quality mode
LLAMACPP_Q4_CTX_SIZE=8192         # Context window
LLAMACPP_F16_CTX_SIZE=16384       # Larger for deep reasoning
```

### llama/stop.sh

**Purpose**: Stop all llama.cpp servers gracefully

**Features**:
- Stops by PID file (graceful)
- SIGTERM → wait 10s → SIGKILL (if needed)
- Fallback: kills all llama-server processes
- Cleans up PID files

**Usage**:
```bash
# Stop all llama.cpp servers
./ops/scripts/llama/stop.sh

# Check if stopped
ps aux | grep llama-server
```

---

## Monitoring Scripts

### monitor/inference.sh

**Purpose**: Real-time monitoring of llama.cpp inference activity

**Monitors**:
- Metal GPU power usage (Apple Silicon)
- Per-process CPU, memory, thread count (Q4/F16)
- Active network connections on llama.cpp ports
- Recent log activity
- **"⚡ INFERENCE IN PROGRESS"** indicator when models actively working

**Usage**:
```bash
# Monitor every 5 seconds
./ops/scripts/monitor/inference.sh 5

# Monitor every 2 seconds (more responsive)
./ops/scripts/monitor/inference.sh 2

# Save to log file
./ops/scripts/monitor/inference.sh 5 > /tmp/inference-monitor.log

# Run in background
nohup ./ops/scripts/monitor/inference.sh 5 > .logs/monitor.log 2>&1 &
```

**Output Example**:
```
[2025-11-12 19:30:45] GPU & CPU Activity:
  Metal GPU:
    GPU Power: 45.2W (active)
  Q4 Server (PID 12345): CPU=78%, MEM=12%, Threads=24
  F16 Server (PID 12346): CPU=156%, MEM=45%, Threads=48
  Active connections: Q4=1, F16=1
  ⚡ Q4 INFERENCE IN PROGRESS
  ⚡ F16 INFERENCE IN PROGRESS
  Q4 latest log: llama_perf_context_print: eval time...
```

**Use Cases**:
- Verify models are working during long queries
- Detect stuck/idle inference
- Monitor GPU utilization
- Debug timeout issues

### monitor/check-active.sh

**Purpose**: Check if llama.cpp inference is actively processing (not stuck)

**Usage**:
```bash
# Check Q4 server
./ops/scripts/monitor/check-active.sh q4
# Exit 0 = active, Exit 1 = idle/stuck

# Check F16 server
./ops/scripts/monitor/check-active.sh f16

# Use in scripts
if ./ops/scripts/monitor/check-active.sh f16; then
    echo "Still working, don't timeout yet"
else
    echo "Model is idle, safe to timeout"
fi
```

**Detection Logic**:
- CPU usage > 30% → active
- Active connection + recent log activity → active
- Otherwise → idle/stuck

**Integration with Timeouts** (future feature):
```bash
# Pseudo-code for adaptive timeout
while true; do
    if ./ops/scripts/monitor/check-active.sh f16; then
        # Extend timeout, model still working
        continue
    else
        # Model idle, timeout is safe
        break
    fi
    sleep 30
done
```

---

## Utility Scripts

### utils/benchmark-llamacpp.sh

**Purpose**: Benchmark llama.cpp server performance

**Usage**:
```bash
./ops/scripts/utils/benchmark-llamacpp.sh
```

### utils/memory-snapshot.sh

**Purpose**: Capture system memory usage snapshot

**Usage**:
```bash
./ops/scripts/utils/memory-snapshot.sh
```

### utils/test-startup.sh

**Purpose**: Test KITTY startup procedure without actually starting

**Usage**:
```bash
./ops/scripts/utils/test-startup.sh
```

### utils/watchdog-llama.sh

**Purpose**: Auto-restart llama.cpp servers on failure

**Usage**:
```bash
# Run watchdog in background
nohup ./ops/scripts/utils/watchdog-llama.sh > .logs/watchdog.log 2>&1 &
```

### utils/metrics-dashboard.sh

**Purpose**: Display live metrics dashboard in terminal

**Usage**:
```bash
./ops/scripts/utils/metrics-dashboard.sh
```

### utils/notify.sh

**Purpose**: Send notifications via Slack/email

**Usage**:
```bash
./ops/scripts/utils/notify.sh "Message here"
```

---

## Setup Scripts

### setup/artifacts-dir.sh

**Purpose**: Initialize artifacts directory structure

**Usage**:
```bash
./ops/scripts/setup/artifacts-dir.sh
```

**Creates**:
```
artifacts/
├── cad/
├── stl/
├── gcode/
└── images/
```

---

## Migration from Old Scripts

### What Changed

**Old Structure** (redundant):
```
ops/scripts/
├── start-kitty.sh              # Basic startup
├── start-kitty-validated.sh   # Validated startup (better)
├── start-llamacpp.sh           # Single llama.cpp
├── start-llamacpp-dual.sh      # Dual llama.cpp (better)
├── stop-kitty.sh
├── stop-llamacpp.sh
├── stop-llamacpp-dual.sh
└── ... (20+ scripts)
```

**New Structure** (organized):
```
ops/scripts/
├── start-all.sh                # ⭐ Replaces start-kitty-validated.sh
├── stop-all.sh                 # ⭐ Replaces stop-kitty.sh
├── llama/
│   ├── start.sh               # ⭐ Replaces start-llamacpp-dual.sh
│   └── stop.sh                # ⭐ Replaces stop-llamacpp-dual.sh
├── monitor/                    # New: monitoring tools
├── utils/                      # Consolidated utilities
└── setup/                      # One-time setup scripts
```

### Updating Your Workflows

**Old command** → **New command**:
```bash
# Starting services
./ops/scripts/start-kitty-validated.sh → ./ops/scripts/start-all.sh
./ops/scripts/start-llamacpp-dual.sh   → ./ops/scripts/llama/start.sh

# Stopping services
./ops/scripts/stop-kitty.sh           → ./ops/scripts/stop-all.sh
./ops/scripts/stop-llamacpp-dual.sh   → ./ops/scripts/llama/stop.sh

# Monitoring (new functionality)
# None before                          → ./ops/scripts/monitor/inference.sh
```

**All old scripts preserved in**: `ops/scripts-backup/`

---

## Best Practices

### Starting KITTY

**Recommended** (complete stack):
```bash
./ops/scripts/start-all.sh
```

**Advanced** (manual control):
```bash
# 1. Start llama.cpp servers
./ops/scripts/llama/start.sh

# 2. Wait for models (~5 minutes)
sleep 300

# 3. Verify health
curl http://localhost:8083/health
curl http://localhost:8082/health

# 4. Start Docker services
docker compose up -d

# 5. Start monitoring
./ops/scripts/monitor/inference.sh 5
```

### Stopping KITTY

**Recommended**:
```bash
./ops/scripts/stop-all.sh
```

**Emergency** (if scripts fail):
```bash
# Stop Docker
docker compose down

# Force kill llama.cpp
pkill -9 -f llama-server

# Verify
ps aux | grep -E "llama-server|docker"
```

### Monitoring Long-Running Queries

```bash
# Terminal 1: Start monitoring
./ops/scripts/monitor/inference.sh 2

# Terminal 2: Submit query
kitty-cli say "Your complex query here..."

# Watch Terminal 1 for:
# - ⚡ INFERENCE IN PROGRESS
# - High CPU (> 50%)
# - Active connections
# - Recent log activity
```

---

## Troubleshooting

### llama.cpp Won't Start

**Check**:
```bash
# Port already in use?
lsof -i :8082
lsof -i :8083

# Model files exist?
ls -lh /Users/Shared/Coding/models/*.gguf

# Logs show errors?
tail -100 .logs/llamacpp-*.log | grep -i error
```

**Fix**:
```bash
# Kill stuck processes
./ops/scripts/llama/stop.sh
pkill -9 -f llama-server

# Restart
./ops/scripts/llama/start.sh
```

### Services Not Stopping

**Check**:
```bash
# See what's still running
ps aux | grep -E "llama-server|docker"
docker ps
```

**Fix**:
```bash
# Force stop Docker
docker compose kill
docker compose down -v

# Force kill llama.cpp
pkill -9 -f llama-server

# Clean up
rm -f .logs/*.pid
```

### Monitoring Shows No Activity

**Check**:
```bash
# Servers actually running?
curl http://localhost:8083/health
curl http://localhost:8082/health

# Logs recent?
ls -lht .logs/llamacpp-*.log
```

**Fix**:
```bash
# Restart monitoring
./ops/scripts/monitor/inference.sh 5

# If servers not responding, restart
./ops/scripts/stop-all.sh
./ops/scripts/start-all.sh
```

---

## Development & Customization

### Adding a New Script

1. **Choose directory**:
   - Core lifecycle: `ops/scripts/`
   - llama.cpp: `ops/scripts/llama/`
   - Monitoring: `ops/scripts/monitor/`
   - Utility: `ops/scripts/utils/`
   - Setup: `ops/scripts/setup/`

2. **Create script**:
   ```bash
   nano ops/scripts/utils/my-script.sh
   chmod +x ops/scripts/utils/my-script.sh
   ```

3. **Follow conventions**:
   ```bash
   #!/bin/bash
   set -e  # Exit on error

   SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
   PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"  # Adjust depth
   cd "$PROJECT_ROOT"

   # Your script here
   ```

4. **Update this README**:
   - Add to Directory Structure
   - Add to relevant section
   - Document usage

### Modifying Existing Scripts

All original scripts are in `ops/scripts-backup/` if you need to reference them.

To restore an old script:
```bash
cp ops/scripts-backup/old-script.sh ops/scripts/utils/
chmod +x ops/scripts/utils/old-script.sh
```

---

## Related Documentation

- **Deployment Plan**: `docs/WORKSTATION_DEPLOYMENT_PLAN.md`
- **Quality-First Mode**: `docs/QUALITY_FIRST_MODE.md`
- **Runbook**: `ops/runbooks/langgraph-troubleshooting.md`

---

**Backup Location**: All original scripts preserved in `ops/scripts-backup/`
**Contact**: For issues or questions, see `ops/runbooks/`
