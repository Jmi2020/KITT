# KITTY CLI Architecture & Usage

## Question: Can the KITTY TUI/CLI do what the direct API test did?

**Short Answer**: The CLI can have conversations with KITTY, but it doesn't load models directly. Model loading is handled separately by the model manager or startup scripts.

## Architecture Comparison

### My Direct Test (Bypassed Full Stack)
```
Test Script → llama.cpp (port 8082) → Direct /v1/chat/completions call
```
This was a low-level test that bypassed all KITTY services and talked directly to the llama.cpp inference server.

### KITTY CLI (Full Stack)
```
kitty-cli → Brain Service (port 8000) → llama.cpp (port 8082)
             ↓
          Intelligent Routing (local/MCP/frontier)
          Semantic Cache (Redis)
          Permission Manager
          Safety Workflows
```

The CLI is designed as a **high-level conversational interface** that uses the full KITTY orchestration layer.

## What Each Component Does

### Model Manager TUI (`model-manager` or 'm' key in launcher)
- **Purpose**: Manage llama.cpp server lifecycle
- **Capabilities**:
  - Start/stop llama.cpp server
  - Switch between models (primary/coder)
  - Monitor server health
  - View startup logs with progress feedback
- **Does NOT**: Have conversations or generate responses

### KITTY CLI (`kitty-cli`)
- **Purpose**: Conversational interface for KITTY
- **Capabilities**:
  - Chat with KITTY via natural language
  - Generate CAD models
  - Queue prints to fabrication devices
  - Control verbosity (1-5 scale)
  - Maintain conversation context
- **Does NOT**: Load models (expects brain service to be running)

### Start Scripts (`ops/scripts/start-kitty.sh`)
- **Purpose**: Launch the complete KITTY stack
- **What it does**:
  1. Loads environment from `.env`
  2. Starts llama.cpp server with configured model
  3. Starts all Docker services (brain, gateway, CAD, etc.)
  4. Ensures everything is running and healthy

## The Proper KITTY Workflow

### Complete Startup Sequence

```bash
# 1. Start the full KITTY stack (llama.cpp + all services)
./ops/scripts/start-kitty.sh

# This will:
# - Load model into memory (30-120 seconds with progress feedback)
# - Start brain service on port 8000
# - Start gateway, CAD, fabrication, safety services
# - Start infrastructure (redis, postgres, MQTT, etc.)
```

### Using the CLI

```bash
# 2. Use the CLI for conversations (after stack is running)
kitty-cli shell

# Inside the shell:
you> Hey KITTY, what printers are online?
KITTY> [Response using brain service → local model]

you> /cad design a bracket for mounting
KITTY> [Generates CAD via Zoo/Tripo]

you> /queue 1 printer_01
KITTY> [Queues artifact to printer]

you> /remember Operator prefers PLA on Voron 2.4
KITTY> [Long-term note saved via memory MCP]

you> /memories PLA
KITTY> [Displays previously stored notes]

you> omega what's the latest NYC build-code update?
KITTY> [Paid providers unlocked; Perplexity lookup runs]

you> /reset
KITTY> [Generates a fresh conversation ID; llama.cpp context cleared]

you> /exit
```

### One-Off Commands

```bash
# Send single message
kitty-cli say "What's the status of printer_01?"

# Generate CAD
kitty-cli cad "design a wall mount"

# List available models
kitty-cli models

# Store/recall long-term notes without keeping a giant prompt
kitty-cli shell <<'EOF'
/remember Filament stock low on CF-PLA
/memories PLA
/reset
EOF

# Unlock paid MCP/frontier providers (Perplexity, OpenAI/Anthropic)
kitty-cli say "omega give me the latest CPI reading with sources"
```

## Configuration

The CLI reads from your `.env` file to determine endpoints:

```bash
# CLI looks for these (in order of priority):
KITTY_API_BASE=http://localhost:8000       # Primary
KITTY_CLI_API_BASE=http://localhost:8000   # CLI-specific
GATEWAY_API=http://localhost:8080          # Gateway
BRAIN_API_BASE=http://localhost:8000       # Brain direct

# Defaults to: http://localhost:8000 (brain service)
```

## Why This Architecture?

### Benefits of Going Through Brain Service

1. **Intelligent Routing**: Brain decides whether to use local model, MCP (Perplexity search), or frontier (GPT/Claude) based on confidence and query complexity

2. **Semantic Caching**: Repeated similar questions get instant responses from Redis cache

3. **Safety Integration**: Hazardous operations (unlock doors, enable power) require confirmation workflows

4. **Permission Management**: Cloud API calls require budget approval

5. **Tool Execution**: Brain can use MCP servers (CAD generation, Home Assistant control, memory storage)

6. **Observability**: All conversations logged with routing decisions, costs, and latency

### When to Use Direct llama.cpp Access

Direct API access (like my test) is useful for:
- Low-level debugging
- Benchmarking inference performance
- Testing model quality without KITTY overhead
- Development/testing of new features

## Troubleshooting

### CLI says "Connection refused"

**Problem**: Brain service isn't running

**Solution**:
```bash
# Check if brain is running
docker compose -f infra/compose/docker-compose.yml ps brain

# Check brain logs
docker compose -f infra/compose/docker-compose.yml logs brain

# Restart full stack
./ops/scripts/start-kitty.sh
```

### Model Manager shows "No model running"

**Problem**: llama.cpp server isn't running

**Solution**:
```bash
# Check if llama.cpp is running
lsof -i :8082

# Check startup logs
tail -f .logs/llamacpp.log

# Start llama.cpp manually
source .env && ./ops/scripts/start-llamacpp.sh
```

### Brain service can't reach llama.cpp

**Problem**: Networking issue between Docker and host

**Solution**:
```bash
# Brain service expects llama.cpp on host network
# Check .env has:
LLAMACPP_HOST=http://host.docker.internal:8082  # For Docker on Mac
# OR
LLAMACPP_HOST=http://172.17.0.1:8082  # For Docker on Linux
```

## Summary

**Can the TUI/CLI do what the test did?**

| Capability | Direct API Test | Model Manager TUI | KITTY CLI |
|-----------|----------------|-------------------|-----------|
| Load models into memory | ❌ (manual script) | ✅ Yes | ❌ No |
| Have conversations | ✅ Yes (raw) | ❌ No | ✅ Yes (full features) |
| Show progress during model loading | ❌ No | ✅ Yes | ❌ No |
| Use intelligent routing | ❌ No | ❌ No | ✅ Yes |
| Generate CAD | ❌ No | ❌ No | ✅ Yes |
| Control devices | ❌ No | ❌ No | ✅ Yes |
| Safety workflows | ❌ No | ❌ No | ✅ Yes |

**The complete workflow**:
1. **Start**: Use `./ops/scripts/start-kitty.sh` or Model Manager TUI to load models
2. **Interact**: Use `kitty-cli shell` for conversations and fabrication control
3. **Monitor**: Use Model Manager TUI to check server health and switch models

Each component has a specific role - they work together as a system.
