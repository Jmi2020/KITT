# Idle Shutdown & Auto-Restart for llama.cpp Servers

## Overview

KITTY's parallel agent orchestration system now includes automatic memory management for local LLM servers. This feature:

1. **Monitors idle time** for each llama.cpp server endpoint
2. **Automatically shuts down** servers that have been idle beyond their configured threshold
3. **Auto-restarts** servers on-demand when a new inference request arrives

This frees unified memory on the Mac Studio M3 Ultra when models are not actively being used, while maintaining sub-30-second restart capability.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Brain Service                            │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐   ┌──────────────┐   ┌───────────────────┐    │
│  │ SlotManager │──▶│  IdleReaper  │──▶│  ProcessManager   │    │
│  │             │   │  (background)│   │  (subprocess ctl) │    │
│  │ last_used   │   │  every 60s   │   │  start/stop       │    │
│  └─────────────┘   └──────────────┘   └───────────────────┘    │
│         │                                      │                │
│         │ acquire_slot()                       │ stop_server()  │
│         │ release_slot()                       │ start_server() │
│         ▼                                      ▼                │
│  ┌─────────────────────────────────────────────────────────────┤
│  │                    llama.cpp Servers                        │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │
│  │  │ Q4:8083  │ │Coder:8087│ │Vision:   │ │Summary:  │       │
│  │  │ 15m idle │ │ 15m idle │ │ 8086     │ │ 8084     │       │
│  │  │ shutdown │ │ shutdown │ │ 30m idle │ │ 30m idle │       │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘       │
│  └─────────────────────────────────────────────────────────────┤
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Ollama (GPTOSS 120B)                         │
│            Self-managed via OLLAMA_KEEP_ALIVE=30m               │
│                   (excluded from IdleReaper)                    │
└─────────────────────────────────────────────────────────────────┘
```

## Components

### 1. SlotManager (`slot_manager.py`)

Extended with idle tracking capabilities:

```python
# Track when each tier was last used
_last_used: Dict[ModelTier, datetime]

# Methods
await slot_manager.get_idle_seconds(tier)      # How long idle
await slot_manager.is_tier_idle(tier, 900)     # Idle > 15 min?
await slot_manager.mark_tier_active(tier)      # Reset timer
```

When `release_slot()` is called, it records the current UTC timestamp. This timestamp is used by the IdleReaper to determine how long a server has been inactive.

### 2. IdleReaper (`idle_reaper.py`)

Background asyncio task that periodically checks for idle endpoints:

```python
class IdleReaper:
    async def start(self, interval: float = 60.0)  # Start background loop
    async def stop()                                # Stop background loop
    async def check_and_shutdown_idle()             # Manual check
    def get_status() -> Dict                        # Monitoring
```

**Logic:**
1. Every 60 seconds (configurable), iterate through all endpoints
2. Skip endpoints with `idle_shutdown_seconds = 0` (like Ollama)
3. Skip endpoints with active slots (`endpoint.active_slots > 0`)
4. If idle time > threshold, call `shutdown_callback(tier)`

### 3. ProcessManager (`process_manager.py`)

Python subprocess control for llama.cpp servers:

```python
class ProcessManager:
    async def start_server(tier: ModelTier) -> Optional[int]   # Returns PID
    async def stop_server(tier: ModelTier, graceful_timeout=5.0) -> bool
    async def restart_server(tier: ModelTier) -> Optional[int]
    def is_running(tier: ModelTier) -> bool
    def get_status() -> Dict[str, Dict]
```

**Server Configuration:**
- Builds `llama-server` command from environment variables
- Matches `ops/scripts/llama/start.sh` configuration
- Logs to `.logs/llamacpp-{tier}.log`
- Creates PID files for compatibility with bash scripts

**Graceful Shutdown:**
1. Send SIGTERM to process group
2. Wait up to 5 seconds for graceful exit
3. If timeout, send SIGKILL

### 4. Auto-Restart on Acquire

When `SlotManager.acquire_slot()` is called for a stopped server:

```python
# In acquire_slot()
if self._auto_restart and not endpoint._is_running:
    await self._ensure_server_running(tier, endpoint)
```

This starts the server via ProcessManager and waits up to 30 seconds for it to become healthy before proceeding.

## Configuration

### Environment Variables

```bash
# Idle shutdown thresholds (seconds, 0 = never shutdown)
LLAMACPP_Q4_IDLE_SHUTDOWN_SECONDS=900       # 15 minutes
LLAMACPP_CODER_IDLE_SHUTDOWN_SECONDS=900    # 15 minutes
LLAMACPP_VISION_IDLE_SHUTDOWN_SECONDS=1800  # 30 minutes
LLAMACPP_SUMMARY_IDLE_SHUTDOWN_SECONDS=1800 # 30 minutes

# IdleReaper check interval (default: 60 seconds)
IDLE_REAPER_INTERVAL_SECONDS=60

# Enable/disable the feature
ENABLE_PARALLEL_AGENTS=true  # IdleReaper only runs when parallel agents enabled
```

### Per-Endpoint Settings

| Endpoint | Default Idle Timeout | Rationale |
|----------|---------------------|-----------|
| Q4 (Tool Orchestrator) | 15 min | Primary agent endpoint, frequent use |
| Coder (Qwen 32B) | 15 min | Code generation, bursty workload |
| Vision (Gemma 27B) | 30 min | Less frequent, image analysis |
| Summary (Hermes 8B) | 30 min | Low memory footprint, less urgent |
| GPTOSS (Ollama) | Never | Ollama manages its own `keep_alive` |

## Service Integration

The IdleReaper is started automatically in `brain/app.py` during the lifespan startup:

```python
# In lifespan()
if parallel_enabled:
    slot_manager = get_slot_manager()
    process_manager = get_process_manager()

    app.state.idle_reaper = IdleReaper(
        slot_manager=slot_manager,
        shutdown_callback=process_manager.stop_server,
    )

    await app.state.idle_reaper.start(interval=60)
```

And gracefully stopped during shutdown:

```python
# In lifespan() shutdown
if app.state.idle_reaper:
    await app.state.idle_reaper.stop()
```

## Monitoring

### Logs

The feature logs at INFO level:

```
INFO  IdleReaper started: checking every 60s, monitoring 4 endpoints
INFO  Tier q4_tools has been idle for 920s (threshold: 900s), shutting down
INFO  Successfully shut down q4_tools
INFO  Auto-starting q4_tools server...
INFO  Server q4_tools is ready
```

### Status Endpoint

The IdleReaper status is available via:

```python
app.state.idle_reaper.get_status()
# Returns:
# {
#     "running": True,
#     "check_interval": 60.0,
#     "endpoints_monitored": 4
# }
```

### ProcessManager Status

```python
from brain.agents.parallel import get_process_manager
pm = get_process_manager()
pm.get_status()
# Returns per-tier:
# {
#     "q4_tools": {"running": True, "pid": 12345, "port": 8083, "alias": "kitty-q4"},
#     "coder": {"running": False, "pid": None, "port": 8087, "alias": "kitty-coder"},
#     ...
# }
```

## Memory Impact

### Mac Studio M3 Ultra (192GB Unified Memory)

| Model | VRAM Usage | Idle Timeout |
|-------|------------|--------------|
| Athene V2 Q4 (72B params) | ~45GB | 15 min |
| Qwen 32B Coder Q8 | ~35GB | 15 min |
| Gemma 27B Vision Q4 | ~20GB | 30 min |
| Hermes 8B Q4 | ~6GB | 30 min |
| **Total if all loaded** | **~106GB** | - |

With idle shutdown, memory is freed progressively as models become inactive, leaving more headroom for other applications or larger context windows.

## Comparison with Ollama

| Feature | IdleReaper (llama.cpp) | Ollama |
|---------|------------------------|--------|
| Idle tracking | Via SlotManager | Built-in |
| Config | `*_IDLE_SHUTDOWN_SECONDS` env vars | `OLLAMA_KEEP_ALIVE` |
| Shutdown method | SIGTERM → SIGKILL subprocess | Internal unload |
| Auto-restart | Yes, on acquire_slot() | Yes, on API request |
| Integration | Brain service lifespan | Standalone daemon |

**Why not use Ollama for everything?**

- llama.cpp offers more control over quantization, context length, and batching
- Athene V2 Agent Q4 model is specifically tuned for tool calling
- Parallel slots (`-np 6`) for concurrent inference not well supported in Ollama

## Troubleshooting

### Servers Not Shutting Down

1. **Check if IdleReaper is running:**
   ```python
   app.state.idle_reaper.get_status()
   ```

2. **Check idle time:**
   ```python
   from brain.agents.parallel import get_slot_manager
   sm = get_slot_manager()
   await sm.get_idle_tiers()
   ```

3. **Check if slots are still active:**
   ```python
   sm.get_status()  # Shows active/max per tier
   ```

### Servers Not Restarting

1. **Check ProcessManager status:**
   ```python
   from brain.agents.parallel import get_process_manager
   pm = get_process_manager()
   pm.get_status()
   ```

2. **Check logs:**
   ```bash
   tail -f .logs/llamacpp-q4-tools.log
   ```

3. **Verify model paths:**
   ```bash
   ls -la $MODEL_BASE/athene-v2-agent/
   ```

### Manual Override

To manually stop/start servers:

```python
from brain.agents.parallel import get_process_manager, ModelTier

pm = get_process_manager()

# Stop
await pm.stop_server(ModelTier.Q4_TOOLS)

# Start
await pm.start_server(ModelTier.Q4_TOOLS)

# Or use bash scripts
# ./ops/scripts/llama/stop.sh
# ./ops/scripts/llama/start.sh
```

## Future Enhancements

1. **Prometheus Metrics**: Export idle time, shutdown count, restart count
2. **Smart Preloading**: Predict which models will be needed based on time of day
3. **Memory Pressure Detection**: Trigger early shutdown when system memory is low
4. **Warm Standby**: Keep models partially loaded for faster restart
