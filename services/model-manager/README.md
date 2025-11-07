# KITTY Model Manager

Terminal TUI for managing llama.cpp models with intelligent discovery, health monitoring, and hot-swapping.

## Features

- **Model Discovery**: Auto-scan `/Users/Shared/Coding/models` for GGUF files with metadata parsing
- **Health Monitoring**: Poll llama.cpp server until ready with real-time status
- **Hot-Swapping**: Restart llama-server with new models without Docker restart
- **Auto-Restart**: Automatic restart on crash with exponential backoff (configurable retry limit)
- **Interactive TUI**: Textual-based interface with keyboard-driven navigation
- **Configuration Management**: Read/write .env with validation and command generation

## Installation

```bash
cd services/model-manager
pip install -e .
```

## Quick Start

```bash
# Install the model manager
cd services/model-manager
pip install -e .

# Launch the TUI
python -m model_manager.main tui

# Or use the CLI for specific operations
python -m model_manager.main start     # Start server
python -m model_manager.main status    # Check status
python -m model_manager.main scan      # Scan for models
```

## Usage

### TUI Interface (Interactive Mode)

The TUI provides a real-time dashboard for managing llama.cpp models:

```bash
# Launch TUI with default .env
python -m model_manager.main tui

# Launch TUI with custom .env
python -m model_manager.main tui --env /path/to/.env
```

**TUI Layout:**

```
┌─────────────────────────────────────────────────────────────┐
│                  KITTY Model Manager                         │
├──────────────────────┬──────────────────────────────────────┤
│  Status Panel        │  Model Browser                       │
│  ┌────────────────┐  │  ┌────────────────────────────────┐  │
│  │ Status: READY  │  │  │ Available Models               │  │
│  │ PID: 12345     │  │  │                                │  │
│  │ Model: Qwen... │  │  │ Found 15 models in 3 families  │  │
│  │ Alias: kitty-  │  │  │ Total size: 245.3 GB           │  │
│  │ Endpoint: :8080│  │  │                                │  │
│  │ Uptime: 00:15:32│ │  │ ▶ 1. Qwen2.5-72B (4 models)   │  │
│  │ Latency: 45ms  │  │  │   ✓ qwen2.5-72b-fp16          │  │
│  │ Slots: 4 idle  │  │  │   ✓ qwen2.5-72b-q4_k_m        │  │
│  └────────────────┘  │  │                                │  │
│  ┌────────────────┐  │  │   2. Qwen2.5-Coder (3 models) │  │
│  │ Log Panel      │  │  │   3. Mistral-7B (2 models)    │  │
│  │ 12:34:56 Started│ │  │                                │  │
│  │ 12:35:10 Ready │  │  │                                │  │
│  │ 12:35:15 Health│  │  │                                │  │
│  └────────────────┘  │  └────────────────────────────────┘  │
└──────────────────────┴──────────────────────────────────────┘
│ q:Quit r:Refresh s:Start x:Stop t:Restart h:Health m:Scan  │
└─────────────────────────────────────────────────────────────┘
```

**Keyboard Shortcuts:**

| Key | Action | Description |
|-----|--------|-------------|
| `q` | Quit | Exit the application |
| `r` | Refresh | Refresh server status |
| `s` | Start | Start llama.cpp server |
| `x` | Stop | Stop running server |
| `t` | Restart | Restart server with current model |
| `h` | Health | Run health check |
| `m` | Scan | Scan for available models |

**Status Indicators:**

- 🟢 **READY** - Server running and healthy
- 🟡 **LOADING** - Model loading in progress
- 🟡 **STARTING** - Server starting up
- 🔴 **FAILED** - Server failed or unhealthy
- 🔴 **CRASHED** - Server process crashed
- ⚫ **STOPPED** - Server not running

### Command-Line Interface

For scripting and automation, use the CLI commands:

```bash
# Server Control
python -m model_manager.main start              # Start server (waits for ready)
python -m model_manager.main start --no-wait    # Start without waiting
python -m model_manager.main stop               # Graceful stop
python -m model_manager.main stop --force       # Force kill
python -m model_manager.main restart            # Restart server
python -m model_manager.main status             # Show detailed status

# Model Management
python -m model_manager.main scan               # Scan for models
python -m model_manager.main scan --dir /path   # Scan custom directory
python -m model_manager.main switch MODEL_PATH  # Hot-swap model
python -m model_manager.main switch MODEL_PATH --alias custom-name

# Examples
python -m model_manager.main switch "Qwen2.5-Coder-32B-Instruct-GGUF/qwen2.5-coder-32b-instruct-q4_k_m.gguf" --alias kitty-coder
```

**CLI Output Examples:**

```bash
$ python -m model_manager.main status

Server Status
─────────────────────────────
Status         READY
PID            12345
Model          Qwen2.5-Coder-32B-Instruct-GGUF/qwen2.5-coder-32b-instruct-q4_k_m.gguf
Alias          kitty-coder
Endpoint       http://localhost:8080
Uptime         00:15:32

Health: 45ms latency
Slots: 4 idle, 0 processing
```

```bash
$ python -m model_manager.main scan

Scanning /Users/Shared/Coding/models...

Found 15 models in 3 families
Total size: 245.3 GB
Scan time: 1.23s

Qwen2.5-72B-Instruct-GGUF (4 models)
  ✓ qwen2.5-72b-instruct-fp16 (fp16, 144.5GB, 42/42 shards, ~72B params)
  ✓ qwen2.5-72b-instruct-q8_0 (q8_0, 76.8GB, ~72B params)
  ✓ qwen2.5-72b-instruct-q4_k_m (q4_k_m, 42.1GB, ~72B params)
  ⚠ qwen2.5-72b-instruct-q2_k (q2_k, 25.3GB, 38/42 shards)

Qwen2.5-Coder-32B-Instruct-GGUF (3 models)
  ✓ qwen2.5-coder-32b-instruct-fp16 (fp16, 64.2GB, 9/9 shards, ~32B params)
  ✓ qwen2.5-coder-32b-instruct-q4_k_m (q4_k_m, 18.7GB, ~32B params)
  ✓ qwen2.5-coder-32b-instruct-q3_k_m (q3_k_m, 14.2GB, ~32B params)
```

## Common Workflows

### First-Time Setup

```bash
# 1. Install the model manager
cd services/model-manager
pip install -e .

# 2. Ensure .env is configured with model paths
# Edit /Users/Shared/Coding/KITT/.env:
#   LLAMACPP_MODELS_DIR=/Users/Shared/Coding/models
#   LLAMACPP_PRIMARY_MODEL=Qwen2.5-72B-Instruct-GGUF/qwen2.5-72b-instruct-q4_k_m.gguf
#   LLAMACPP_PORT=8080

# 3. Scan for available models
python -m model_manager.main scan

# 4. Start the server
python -m model_manager.main start

# 5. Verify it's running
python -m model_manager.main status
```

### Switching Models (Hot-Swap)

```bash
# 1. Check what's currently running
python -m model_manager.main status

# 2. Scan to see available models
python -m model_manager.main scan

# 3. Switch to a different model (this restarts the server)
python -m model_manager.main switch "Qwen2.5-Coder-32B-Instruct-GGUF/qwen2.5-coder-32b-instruct-q3_k_m.gguf" --alias kitty-coder

# 4. Verify the switch
python -m model_manager.main status
```

**Note:** Model switching restarts the llama-server process (NOT Docker). Any in-progress requests will be interrupted.

### Monitoring Server Health

```bash
# TUI mode - continuous monitoring
python -m model_manager.main tui
# Press 'h' to run health checks
# Status panel updates every 5 seconds automatically

# CLI mode - one-time check
python -m model_manager.main status
```

### Troubleshooting Server Issues

```bash
# 1. Check if server is running
python -m model_manager.main status

# 2. If crashed, check logs
tail -50 ~/.kitty/logs/llamacpp.log

# 3. Force stop and restart
python -m model_manager.main stop --force
python -m model_manager.main start

# 4. If port is in use, check for zombie processes
lsof -i :8080
kill -9 <PID>
```

## Architecture

### Component Overview

```
model-manager/
├── main.py          # CLI entry point with Typer commands
├── app.py           # Textual TUI application with reactive widgets
├── scanner.py       # GGUF discovery and metadata parsing
├── config.py        # .env management and command generation
├── process.py       # llama-server lifecycle management (PID tracking)
├── health.py        # Health check polling with exponential backoff
├── supervisor.py    # Orchestrator with auto-restart and callbacks
└── models.py        # Pydantic data models and enums
```

### Layered Architecture

```
┌─────────────────────────────────────────────────┐
│               TUI Layer (app.py)                │
│  ┌──────────────┐  ┌──────────────────────────┐ │
│  │ StatusPanel  │  │ ModelListPanel           │ │
│  │ LogPanel     │  │ (reactive widgets)       │ │
│  └──────────────┘  └──────────────────────────┘ │
├─────────────────────────────────────────────────┤
│          CLI Layer (main.py + Typer)            │
│  start, stop, restart, status, scan, switch     │
├─────────────────────────────────────────────────┤
│     Orchestration Layer (supervisor.py)         │
│  - Auto-restart with exponential backoff        │
│  - Status callbacks for UI updates              │
│  - Model switching (hot-swap)                   │
├─────────────────────────────────────────────────┤
│      Core Services Layer                        │
│  ┌──────────────┐  ┌──────────────────────────┐ │
│  │ ProcessMgr   │  │ HealthChecker            │ │
│  │ - PID file   │  │ - /health polling        │ │
│  │ - Signals    │  │ - Backoff retry          │ │
│  │ - Logs       │  │ - Status detection       │ │
│  └──────────────┘  └──────────────────────────┘ │
│  ┌──────────────┐  ┌──────────────────────────┐ │
│  │ ConfigMgr    │  │ ModelScanner             │ │
│  │ - .env I/O   │  │ - GGUF discovery         │ │
│  │ - Validation │  │ - Shard validation       │ │
│  └──────────────┘  └──────────────────────────┘ │
├─────────────────────────────────────────────────┤
│         Data Layer (models.py)                  │
│  ServerConfig, ServerStatus, ModelInfo, etc.    │
└─────────────────────────────────────────────────┘
         ▼                            ▼
┌─────────────────┐          ┌──────────────────┐
│ llama-server    │ ◄──HTTP──┤ Health Endpoint  │
│ (native process)│          │ /health          │
└─────────────────┘          └──────────────────┘
```

### Key Design Patterns

**Process Lifecycle Management:**
- PID file: `~/.kitty/llamacpp.pid`
- Log file: `~/.kitty/logs/llamacpp.log`
- Graceful shutdown: SIGTERM → 10s wait → SIGKILL
- Detached process: `start_new_session=True`

**Health Checking:**
- Exponential backoff: 1s × 1.1^n (max 10s between attempts)
- Max retries: 120 (configurable)
- Status detection:
  - Connection refused → STARTING
  - HTTP 503 → LOADING
  - HTTP 200 → READY
  - Timeout → LOADING
  - Other errors → FAILED

**Auto-Restart:**
- Exponential backoff: 5s × 2^(n-1) (max 60s)
- Max attempts: 3 (configurable)
- Restart counter resets on successful health check

**Model Discovery:**
- Recursive GGUF file scanning
- Shard pattern detection: `.*-(\d+)-of-(\d+)\.gguf`
- Completeness validation: all shards 1 to N present
- Quantization detection from filename patterns
- Parameter estimation from file size

## Health Monitoring

The health checker replaces fixed sleep delays with intelligent polling:

**Old approach:**
```bash
llama-server &
sleep 2  # Hope it's ready?
```

**New approach:**
```bash
python -m model_manager.main start  # Waits until actually ready
```

### Health Check Flow

```
1. Start llama-server process
2. Wait 1 second
3. Poll http://localhost:8080/health
   ├─ Connection refused → STARTING (retry with backoff)
   ├─ HTTP 503 → LOADING (model loading, retry)
   ├─ HTTP 200 → READY (success!)
   ├─ Timeout → LOADING (retry with backoff)
   └─ Other → FAILED (error)
4. If READY: return success
5. If max retries exceeded: raise error
6. Otherwise: exponential backoff and retry
```

### Health Check Response

When server is ready, `/health` returns:
```json
{
  "status": "ok",
  "slots_idle": 4,
  "slots_processing": 0,
  "model_loaded": true
}
```

## Troubleshooting

### Server Won't Start

**Symptom:** `python -m model_manager.main start` fails or times out

**Checks:**
1. Is the binary installed?
   ```bash
   which llama-server
   # Should return: /opt/homebrew/bin/llama-server or similar
   ```

2. Is the model path valid?
   ```bash
   ls -la /Users/Shared/Coding/models/Qwen2.5-72B-Instruct-GGUF/
   # Should show GGUF files
   ```

3. Is the port already in use?
   ```bash
   lsof -i :8080
   # If something is there, kill it or change LLAMACPP_PORT
   ```

4. Check the logs:
   ```bash
   tail -100 ~/.kitty/logs/llamacpp.log
   ```

### Model Not Found During Scan

**Symptom:** `scan` command doesn't find your models

**Checks:**
1. Verify models directory:
   ```bash
   ls /Users/Shared/Coding/models/
   # Should list model family directories
   ```

2. Check .env configuration:
   ```bash
   grep LLAMACPP_MODELS_DIR /Users/Shared/Coding/KITT/.env
   ```

3. Ensure GGUF files exist:
   ```bash
   find /Users/Shared/Coding/models -name "*.gguf" | head -5
   ```

### Server Crashes Immediately

**Symptom:** Status shows CRASHED or PID disappears

**Common Causes:**
1. **Out of memory:** Model too large for available RAM/GPU
   - Solution: Use smaller quantization (q4_k_m instead of fp16)

2. **Invalid model file:** Corrupted download
   - Solution: Re-download the GGUF file

3. **Wrong model format:** Not a llama.cpp-compatible GGUF
   - Solution: Verify model is from Hugging Face with GGUF format

4. **GPU layer mismatch:** `n_gpu_layers` too high
   - Solution: Reduce `LLAMACPP_N_GPU_LAYERS` in .env

**Check logs:**
```bash
tail -50 ~/.kitty/logs/llamacpp.log
```

### Health Check Times Out

**Symptom:** Start command hangs for 2+ minutes then fails

**Checks:**
1. Is the model loading? (Large models take time)
   ```bash
   # Watch the log in real-time
   tail -f ~/.kitty/logs/llamacpp.log
   ```

2. Is Metal GPU available?
   ```bash
   # Should show Metal info in logs
   grep -i metal ~/.kitty/logs/llamacpp.log
   ```

3. Increase timeout:
   ```bash
   # Wait up to 5 minutes for large models
   python -m model_manager.main start  # Default: 120s
   ```

### Switch Command Fails

**Symptom:** `switch` command errors or leaves server in bad state

**Checks:**
1. Is model path relative to models_dir?
   ```bash
   # Correct:
   python -m model_manager.main switch "Qwen2.5-Coder-32B-Instruct-GGUF/qwen2.5-coder-32b-instruct-q4_k_m.gguf"

   # Wrong (absolute path):
   python -m model_manager.main switch "/Users/Shared/Coding/models/Qwen2.5-Coder-32B-Instruct-GGUF/..."
   ```

2. Does the model exist?
   ```bash
   python -m model_manager.main scan | grep -i coder
   ```

3. Force stop first if stuck:
   ```bash
   python -m model_manager.main stop --force
   python -m model_manager.main switch "MODEL_PATH"
   ```

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run with coverage
pytest --cov=model_manager --cov-report=html

# Format code
ruff format src/

# Lint
ruff check src/ --fix

# Type check
mypy src/
```

## Integration with start-kitty.sh

The model manager provides health check polling to replace the hard-coded 2-second sleep:

```bash
# Before
sleep 2

# After
if command -v kitty-model-manager &> /dev/null; then
  kitty-model-manager wait-ready --timeout 60
else
  sleep 2  # Fallback
fi
```

## Model Discovery

The scanner automatically finds all GGUF files and:
- Detects split models (`-00001-of-00042` patterns)
- Validates completeness (all shards present)
- Parses quantization levels (fp16, q8_0, q4_k_m, etc.)
- Estimates memory requirements
- Detects model format for tool calling (Qwen XML, Mistral JSON, Gemma Function)

## Configuration

Model configuration is stored in:
- `.env` - Primary configuration (read/write by manager)
- `models.yaml` - Model registry with metadata and favorites
- Environment variables - Runtime overrides

## License

MIT
