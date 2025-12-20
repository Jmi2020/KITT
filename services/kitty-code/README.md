# kitty-code

Local-first AI coding assistant for KITTY fabrication lab. A fork of [mistral-vibe](https://github.com/mistralai/mistral-vibe) optimized for offline operation with Devstral 2.

## Features

- **Local-First**: Runs entirely on local hardware using llama.cpp or Ollama
- **Devstral 2 123B**: Mistral's agentic coding model optimized for software development
- **MCP Integration**: Auto-discovers KITTY services (brain, cad, fab, discovery) as MCP servers
- **Textual TUI**: Rich terminal interface with syntax highlighting and streaming output
- **No API Key Required**: Default operation requires no cloud credentials

## Quick Start

```bash
# Install (from services/kitty-code directory)
pip install -e .

# Run with default local model
kitty-code "Write a Python function to calculate fibonacci numbers"

# With explicit model
kitty-code --model devstral:123b "Create a REST API with FastAPI"
```

## Architecture

```
kitty-code (Textual TUI)
        │
        │  HTTP/SSE
        ▼
┌─────────────────────────────────────────┐
│     llama.cpp Server (port 8087)        │
│     Devstral 2 123B Q5_K_M              │
│     ~82GB sharded GGUF                  │
└─────────────────────────────────────────┘
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LLAMACPP_CODER_HOST` | `http://localhost:8087` | llama.cpp coder server URL |
| `LLAMACPP_CODER_MODEL` | (path) | Path to Devstral GGUF model |
| `LLAMACPP_CODER_CTX` | `16384` | Context window size |
| `LLAMACPP_CODER_TEMPERATURE` | `0.2` | Sampling temperature |
| `MISTRAL_API_KEY` | (optional) | For cloud fallback |

### User Config File

Create `~/.kitty-code/config.toml`:

```toml
# Default model
default_model = "devstral:123b"

# Enabled built-in tools
enabled_tools = ["bash", "grep", "read_file", "write_file", "search_replace"]

# Disable specific integrations
disabled_tools = ["kitty_fab"]

# Custom MCP servers
[[mcp_servers]]
name = "filesystem"
transport = "stdio"
command = "npx"
args = ["-y", "@anthropic/mcp-filesystem", "/path/to/allowed"]

[[mcp_servers]]
name = "github"
transport = "http"
url = "http://localhost:3000/mcp"
prompt = "GitHub API access"
```

## MCP Server Integration

kitty-code auto-discovers KITTY services when running in the KITTY environment:

| Server | URL | Capabilities |
|--------|-----|--------------|
| `kitty_brain` | http://localhost:8000/mcp | Query routing, research, memory |
| `kitty_cad` | http://localhost:8200/mcp | 3D model generation |
| `kitty_fab` | http://localhost:8300/mcp | Printer control, slicing |
| `kitty_discovery` | http://localhost:8500/mcp | Network device scanning |

Test discovery:
```bash
python3 -c "from kitty_code.integrations import get_kitty_mcp_servers; print(get_kitty_mcp_servers())"
```

## Model Setup

### Devstral 2 123B via llama.cpp (Recommended)

llama.cpp natively handles sharded GGUF files:

```bash
# Download model (~82GB total)
huggingface-cli download bartowski/mistralai_Devstral-2-123B-Instruct-2512-GGUF \
  --include "mistralai_Devstral-2-123B-Instruct-2512-Q5_K_M/*" \
  --local-dir ~/models/devstral2/Q5_K_M

# Start llama.cpp server
./ops/scripts/llama/start.sh
```

### Alternative: Ollama

For single-file GGUF models only (Ollama doesn't support sharded files):

```bash
ollama run devstral:123b "Hello"
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Lint
ruff check src/
ruff format src/
```

## Directory Structure

```
services/kitty-code/
├── pyproject.toml
├── src/kitty_code/
│   ├── cli/
│   │   ├── entrypoint.py          # Main entry
│   │   └── textual_ui/
│   │       └── app.py             # KittyCodeApp (TUI)
│   ├── core/
│   │   ├── config.py              # KittyCodeConfig (local-first)
│   │   ├── agent.py               # Agent loop
│   │   └── tools/
│   │       ├── manager.py         # MCP tool discovery
│   │       └── builtins/          # bash, grep, read_file, etc.
│   ├── integrations/
│   │   └── mcp_kitty.py           # KITTY service MCP discovery
│   └── setup/onboarding/          # First-run experience
└── tests/
```

## Commands

| Command | Description |
|---------|-------------|
| `kitty-code` | Interactive TUI mode |
| `kitty-code "prompt"` | Single-shot code generation |
| `kitty-code --model MODEL` | Use specific model |
| `kitty-code --mcp-server URL` | Add external MCP server |
| `kitty-code-acp` | Agent Client Protocol mode |

## Requirements

- Python 3.12+
- llama.cpp with Devstral 2 123B (or Ollama)
- ~82GB disk space for model
- 256GB unified memory recommended (Mac Studio M3 Ultra)

## License

Apache-2.0
