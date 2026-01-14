# Kitty-Code Feature Specification

**Version**: 1.0
**Status**: Active Development
**Last Updated**: January 2026

---

## 1. Overview

### 1.1 Purpose

**kitty-code** is a local-first AI coding assistant designed for the KITTY fabrication lab ecosystem. It provides an interactive terminal user interface (TUI) for AI-assisted development, with deep integration into KITTY's services and tools.

### 1.2 Design Philosophy

| Principle | Description |
|-----------|-------------|
| **Local-First** | Prioritizes local LLM inference (Ollama, llama.cpp) over cloud APIs |
| **Airgap-Compliant** | Operates fully offline; network features are optional |
| **Context-Aware** | Semantic tool selection reduces prompt bloat |
| **Approval-Driven** | Granular permission controls for tool execution |
| **KITTY-Native** | Auto-discovers and integrates with KITTY services |

### 1.3 Target Users

- KITTY fabrication lab operators
- Developers working on KITTY services
- Users requiring offline AI coding assistance
- Security-conscious environments with network restrictions

---

## 2. Architecture

### 2.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        kitty-code TUI                           │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────────┐  │
│  │  VibeApp    │  │ EventHandler │  │ Widget System          │  │
│  │  (Textual)  │──│              │──│ Messages, Input, etc.  │  │
│  └─────────────┘  └──────────────┘  └────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                         Agent Core                              │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────────┐  │
│  │ Agent Loop  │  │ Middleware   │  │ Mode Manager           │  │
│  │             │──│ Pipeline     │──│ (DEFAULT/PLAN/RESEARCH)│  │
│  └─────────────┘  └──────────────┘  └────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
            ┌─────────────────┼─────────────────┐
            ▼                 ▼                 ▼
┌───────────────────┐ ┌──────────────┐ ┌───────────────────┐
│   Tool System     │ │ LLM Backend  │ │  MCP Servers      │
│ ┌───────────────┐ │ │              │ │ ┌───────────────┐ │
│ │ ToolManager   │ │ │ Ollama       │ │ │ HTTP Servers  │ │
│ │ ToolSelector  │ │ │ llama.cpp    │ │ │ STDIO Servers │ │
│ │ Embeddings    │ │ │ Cloud (opt)  │ │ │ KITTY Auto    │ │
│ └───────────────┘ │ │              │ │ └───────────────┘ │
└───────────────────┘ └──────────────┘ └───────────────────┘
```

### 2.2 Module Structure

```
src/kitty_code/
├── cli/                    # User interface layer
│   ├── entrypoint.py       # Main CLI entry point
│   └── textual_ui/         # Textual TUI application
│       ├── app.py          # VibeApp main class
│       ├── handlers/       # Event routing
│       ├── renderers/      # Tool output rendering
│       └── widgets/        # UI components
├── core/                   # Business logic layer
│   ├── agent.py            # Agent orchestration loop
│   ├── config.py           # Configuration management
│   ├── middleware.py       # Request/response pipeline
│   ├── modes.py            # Agent mode definitions
│   ├── llm/                # LLM abstraction
│   │   ├── backend/        # Provider implementations
│   │   ├── format.py       # Tool call formatting
│   │   └── types.py        # Data types
│   ├── tools/              # Tool system
│   │   ├── manager.py      # Discovery and lifecycle
│   │   ├── selector.py     # Intelligent selection
│   │   ├── embeddings.py   # Semantic search
│   │   ├── mcp.py          # MCP client integration
│   │   └── builtins/       # Built-in tools
│   └── prompts/            # System prompt templates
├── integrations/           # External integrations
│   └── mcp_kitty.py        # KITTY service auto-discovery
├── acp/                    # Agent Client Protocol mode
└── setup/                  # Onboarding and trust UI
```

---

## 3. Core Features

### 3.1 Local LLM Integration

**Primary**: Ollama with `devstral:123b` (default model)

| Provider | Port | Use Case |
|----------|------|----------|
| Ollama | 11434 | Primary reasoning (GPT-OSS 120B) |
| llama.cpp | 8083 | Tool orchestration (Athene V2) |
| llama.cpp | 8087 | Code generation (Qwen 2.5 Coder) |

**Cloud Fallback** (when API keys configured):
- Mistral AI
- OpenAI
- Anthropic
- Google (Gemini)
- Perplexity

### 3.2 Semantic Tool Selection

**Problem**: LLMs have limited context windows. Sending 150+ tool definitions wastes tokens.

**Solution**: Two-stage intelligent filtering:

```
┌──────────────────┐     ┌───────────────────┐     ┌──────────────┐
│ User Query       │────▶│ Embedding Search  │────▶│ Top-K Tools  │
│ "search the web" │     │ (all-MiniLM-L6)   │     │ (semantic)   │
└──────────────────┘     └───────────────────┘     └──────────────┘
                                  │
                                  ▼
                         ┌───────────────────┐     ┌──────────────┐
                         │ Category Boost    │────▶│ Final Tools  │
                         │ (keyword match)   │     │ (MAX_TOOLS)  │
                         └───────────────────┘     └──────────────┘
```

**Categories** (keyword-based boost):
- `search`: perplexity, kitty_brain
- `browser`: chrome-devtools
- `filesystem`: read_file, write_file, grep
- `code`: bash, grep, file operations
- `security`: hexstrike, nmap, vulnerability scanning
- `cad`: KITTY CAD service tools
- `fabrication`: KITTY printer/slicer tools

**Configuration**:
- `MAX_TOOLS = 10` (prevents llama.cpp 400 errors)
- Embeddings cached at `~/.kitty-code/cache/tool_embeddings.pkl`
- Cache invalidation via SHA256 hash of tool names

### 3.3 Interactive TUI

Built with **Textual** framework for rich terminal interfaces.

**Key Components**:

| Widget | Purpose |
|--------|---------|
| `VibeApp` | Main application container |
| `UserMessage` | User input display |
| `AssistantMessage` | Streaming AI responses |
| `ToolCallMessage` | Tool invocation display |
| `ToolResultMessage` | Tool output display |
| `LoadingWidget` | Spinner during execution |
| `QueueIndicator` | Pending message count |
| `DirectoryBrowserApp` | Interactive `/cd` navigation |

**Input Queue Behavior**:
- User can submit prompts while agent is executing
- Prompts queue (FIFO) instead of interrupting
- Queue indicator shows count: "Queued: N message(s)"
- Escape key clears queue and interrupts agent

### 3.4 MCP (Model Context Protocol) Integration

Supports both transport types:

**HTTP/Streamable-HTTP**:
```toml
[[mcp_servers]]
name = "supabase"
transport = "http"
url = "http://localhost:5000"
```

**STDIO**:
```toml
[[mcp_servers]]
name = "filesystem"
transport = "stdio"
command = "npx"
args = ["-y", "@anthropic/mcp-server-filesystem", "/path"]
```

**Tool Naming Convention**: `{server_alias}_{tool_name}`
- Example: `supabase_execute_sql`, `chrome_devtools_click`

### 3.5 KITTY Service Auto-Discovery

Automatically detects running KITTY services:

| Service | Port | Tools Provided |
|---------|------|----------------|
| brain | 8000 | Query, research, prompt suggestions |
| CAD | 8200 | 3D model generation |
| fabrication | 8300 | Printer control, slicing |
| mem0-mcp | 8765 | Semantic memory |
| discovery | 8500 | Network device scanning |
| HexStrike | 8889 | Security assessment (151+ tools) |

**Detection Logic**:
1. Check `KITTY_USER_ID` environment variable
2. Verify working directory is under KITT project
3. Health-check service endpoints (`/healthz`)
4. Register discovered MCP servers dynamically

---

## 4. Configuration

### 4.1 Configuration Files

| Location | Scope | Priority |
|----------|-------|----------|
| `~/.kitty-code/config.toml` | Global | 2 |
| `.kitty-code/config.toml` | Project | 1 (highest) |
| Environment variables | Session | 3 |

### 4.2 Key Settings

```toml
# Model Selection
active_model = "local"  # Uses Ollama Devstral by default

# UI Preferences
vim_keybindings = false
textual_theme = "monokai"

# Context Management
auto_compact_threshold = 200000  # tokens

# Session Logging
[session_logging]
enabled = true
save_dir = ".logs"
prefix = "session"

# Provider Configuration
[[providers]]
id = "ollama"
api_backend = "ollama"
api_base = "http://localhost:11434/v1"

# Model Definition
[[models]]
id = "local"
provider = "ollama"
name = "devstral:123b"
```

### 4.3 Tool Configuration

```toml
[tools.bash]
permission = "ask"  # ALWAYS, NEVER, ASK
allowlist = ["git *", "npm *", "python *"]
denylist = ["rm -rf /", "sudo *"]
```

### 4.4 MCP Server Configuration

```toml
[[mcp_servers]]
name = "hexstrike"
transport = "http"
url = "http://localhost:8889"
require_approval = true  # Forces user approval for ALL tools

[[mcp_servers]]
name = "filesystem"
transport = "stdio"
command = "npx"
args = ["-y", "@anthropic/mcp-server-filesystem", "."]
```

---

## 5. Security Model

### 5.1 Approval Levels

```
┌─────────────────────────────────────────────────────┐
│                 Approval Hierarchy                  │
├─────────────────────────────────────────────────────┤
│ 1. Mode-Level     │ Research mode = auto-approve    │
│ 2. Server-Level   │ require_approval = true         │
│ 3. Tool-Level     │ permission = "ask"              │
│ 4. Pattern-Level  │ allowlist / denylist patterns   │
└─────────────────────────────────────────────────────┘
```

### 5.2 Tool Permissions

| Permission | Behavior |
|------------|----------|
| `ALWAYS` | Execute without prompting |
| `NEVER` | Block execution entirely |
| `ASK` | Prompt user for approval |

### 5.3 Allowlist/Denylist Patterns

```toml
[tools.bash]
# Glob patterns
allowlist = ["git *", "npm run *"]
denylist = ["rm -rf *", "sudo *"]
```

### 5.4 Server-Level Approval

For sensitive MCP servers (e.g., security scanning):

```toml
[[mcp_servers]]
name = "hexstrike"
require_approval = true  # All 151+ tools require explicit approval
```

---

## 6. Agent Modes

### 6.1 Available Modes

| Mode | Description | Auto-Approve |
|------|-------------|--------------|
| `DEFAULT` | Standard interactive mode | No |
| `RESEARCH` | Web research optimization | Yes |
| `PLAN` | Task decomposition | No |
| `COMPACT` | Minimal UI | No |

### 6.2 Mode Switching

```
/mode research    # Switch to research mode
/mode default     # Return to default mode
```

---

## 7. Middleware Pipeline

Request/response processing chain:

```
Request → TurnLimit → PriceLimit → AutoCompact → ContextWarning → Agent
                                                                    │
Response ← TurnLimit ← PriceLimit ← AutoCompact ← ContextWarning ←──┘
```

### 7.1 Middleware Components

| Middleware | Purpose |
|------------|---------|
| `TurnLimitMiddleware` | Stops after N agent turns |
| `PriceLimitMiddleware` | Stops when cost threshold reached |
| `AutoCompactMiddleware` | Summarizes history at token threshold |
| `ContextWarningMiddleware` | Warns before compaction |
| `PlanModeMiddleware` | Adjusts behavior for planning |

---

## 8. TUI Commands

### 8.1 Slash Commands

| Command | Description |
|---------|-------------|
| `/help` | Show available commands |
| `/status` | Display agent statistics |
| `/config` | Open configuration panel |
| `/clear` | Clear conversation history |
| `/compact` | Manually compact conversation |
| `/cd [path]` | Change working directory |
| `/mcp list` | List MCP servers |
| `/mcp add <name>` | Add MCP server |
| `/mcp remove <name>` | Remove MCP server |
| `/log` | Show log file path |
| `/setup-terminal` | Configure Shift+Enter keybind |

### 8.2 Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Enter` | Submit prompt |
| `Shift+Enter` | Newline in prompt |
| `Escape` | Cancel/interrupt agent |
| `Ctrl+C` | Exit application |
| `Ctrl+O` | Toggle tool output collapse |
| `Up/Down` | History navigation |

---

## 9. Built-in Tools

### 9.1 File Operations

| Tool | Purpose |
|------|---------|
| `read_file` | Read file contents |
| `write_file` | Create/overwrite files |
| `search_replace` | Find and replace in files |
| `grep` | Search files with regex |

### 9.2 System Operations

| Tool | Purpose |
|------|---------|
| `bash` | Execute shell commands |
| `todo` | Manage task lists |

---

## 10. Performance Considerations

### 10.1 Embedding Cache

- Model: `all-MiniLM-L6-v2` (~80MB)
- First load: ~2 seconds
- Subsequent loads: ~100ms (cached)
- Cache location: `~/.kitty-code/cache/tool_embeddings.pkl`
- Invalidation: Tool set hash changes

### 10.2 Context Management

| Setting | Default | Purpose |
|---------|---------|---------|
| `auto_compact_threshold` | 200,000 tokens | Trigger compaction |
| `MAX_TOOLS` | 10 | Prevent context overflow |

### 10.3 Streaming

- Chunks aggregated by index
- Reasoning content batched (BATCH_SIZE=5)
- Tool calls streamed separately from content

---

## 11. Dependencies

### 11.1 Core Dependencies

```
mcp>=1.14.0                 # Model Context Protocol
textual>=1.0.0              # TUI framework
pydantic>=2.12.4            # Data validation
httpx>=0.28.1               # HTTP client
watchfiles>=1.1.1           # File monitoring
rich>=14.0.0                # Terminal output
```

### 11.2 Optional Dependencies

```
# Cloud providers
pip install kitty-code[cloud]
  → mistralai>=1.9.11

# Semantic tool selection
pip install kitty-code[semantic]
  → sentence-transformers>=2.2.0
  → numpy>=1.24.0
```

### 11.3 Python Version

- **Minimum**: Python 3.12
- **Recommended**: Python 3.12+

---

## 12. Entry Points

| Command | Description |
|---------|-------------|
| `kitty-code` | Interactive TUI mode |
| `kitty-code "prompt"` | Single-shot execution |
| `kitty-code-acp` | Agent Client Protocol mode |

---

## 13. Integration Points

### 13.1 KITTY Ecosystem

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│ kitty-code  │────▶│ brain       │────▶│ LLM servers │
│             │     │ (port 8000) │     │ (8083-8087) │
└─────────────┘     └─────────────┘     └─────────────┘
       │
       ├───────────▶ CAD (8200)
       ├───────────▶ Fabrication (8300)
       ├───────────▶ Memory (8765)
       ├───────────▶ Discovery (8500)
       └───────────▶ HexStrike (8889)
```

### 13.2 Environment Variables

Loaded from `/Users/Shared/Coding/KITT/.env`:

| Variable | Purpose |
|----------|---------|
| `OLLAMA_*` | Ollama configuration |
| `MISTRAL_API_KEY` | Mistral cloud access |
| `OPENAI_API_KEY` | OpenAI cloud access |
| `ANTHROPIC_API_KEY` | Anthropic cloud access |
| `PERPLEXITY_API_KEY` | Perplexity search |
| `GOOGLE_API_KEY` | Google Gemini access |
| `HEXSTRIKE_ENABLED` | Enable security tools |

---

## 14. Future Considerations

### 14.1 Planned Enhancements

- [ ] Multi-agent collaboration support
- [ ] Enhanced streaming with progress indicators
- [ ] Plugin architecture for custom tools
- [ ] Integration with KITTY voice service
- [ ] Persistent conversation sessions

### 14.2 Known Limitations

1. **Context Window**: Large tool sets can exceed context limits
2. **Embeddings**: Optional dependency; degrades to keyword matching
3. **STDIO MCP**: Stderr suppression may hide useful debug info
4. **Airgap Mode**: Update notifiers stubbed; no version checking

---

## 15. Glossary

| Term | Definition |
|------|------------|
| **MCP** | Model Context Protocol - standardized tool/resource interface |
| **TUI** | Terminal User Interface |
| **Airgap** | Network-isolated operation mode |
| **Compaction** | Summarizing conversation history to reduce context |
| **Semantic Selection** | Using embeddings to match queries to tools |

---

## Appendix A: Configuration Reference

See [Configuration Documentation](./CONFIG.md) for complete reference.

## Appendix B: MCP Server Setup

See [MCP Servers Documentation](./MCP_SERVERS.md) for setup guides.

---

*This specification is maintained as part of the KITTY project.*
