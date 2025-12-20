# MCP Server Configuration Guide

This guide explains how to add, configure, and manage MCP (Model Context Protocol) servers in kitty-code.

## Overview

MCP servers extend kitty-code's capabilities by providing additional tools for:
- File system access
- Web search and research
- Browser automation
- Memory/knowledge graphs
- Custom integrations

kitty-code supports two MCP transport types:
- **HTTP/Streamable-HTTP**: For remote servers accessible via URL
- **STDIO**: For local processes that communicate via stdin/stdout

## Quick Start

### Using the /mcp Command

The easiest way to manage MCP servers is through the TUI:

```bash
# List all configured MCP servers
/mcp

# Add an HTTP server
/mcp add my-server http://localhost:3000/mcp

# Add a STDIO server (using --)
/mcp add filesystem -- npx -y @modelcontextprotocol/server-filesystem /path/to/dir

# Remove a server
/mcp remove my-server
```

### Scope Options

When adding servers, you can specify where the configuration is saved:

```bash
# User scope (default) - saved to ~/.kitty-code/config.toml
/mcp add my-server --scope user http://localhost:3000/mcp

# Project scope - saved to .kitty-code/config.toml in current directory
/mcp add my-server --scope project http://localhost:3000/mcp
```

## Configuration File Format

MCP servers are configured in `~/.kitty-code/config.toml` (user scope) or `.kitty-code/config.toml` (project scope).

### HTTP Servers

```toml
[[mcp_servers]]
name = "my-api"
transport = "http"
url = "http://localhost:3000/mcp"
prompt = "Description of what this server provides"

# Optional: API key authentication
api_key_env = "MY_API_KEY"
api_key_header = "Authorization"
api_key_format = "Bearer {token}"

# Optional: Custom headers
[mcp_servers.headers]
X-Custom-Header = "value"
```

### STDIO Servers

```toml
[[mcp_servers]]
name = "filesystem"
transport = "stdio"
command = "npx"
args = ["-y", "@modelcontextprotocol/server-filesystem", "/Users/me/Desktop"]
prompt = "File system access for Desktop"

# Optional: Environment variables
[mcp_servers.env]
MY_VAR = "value"
# Reference system env vars with ${VAR} syntax
API_KEY = "${MY_API_KEY}"
```

## Common MCP Servers

### File System Access

```toml
[[mcp_servers]]
name = "filesystem"
transport = "stdio"
command = "npx"
args = ["-y", "@modelcontextprotocol/server-filesystem", "/Users/me/Desktop", "/Users/me/Downloads"]
prompt = "File system access for Desktop and Downloads"
```

### Persistent Memory (Knowledge Graph)

```toml
[[mcp_servers]]
name = "memory"
transport = "stdio"
command = "npx"
args = ["-y", "@modelcontextprotocol/server-memory"]
prompt = "Persistent memory and knowledge graph"
```

### Chrome Browser Automation

```toml
[[mcp_servers]]
name = "chrome-devtools"
transport = "stdio"
command = "npx"
args = ["chrome-devtools-mcp@latest"]
prompt = "Chrome browser automation and DevTools access"
```

### Perplexity AI Search

```toml
[[mcp_servers]]
name = "perplexity-ask"
transport = "stdio"
command = "docker"
args = ["run", "-i", "--rm", "-e", "PERPLEXITY_API_KEY", "mcp/perplexity-ask"]
prompt = "Perplexity AI search and research"

[mcp_servers.env]
PERPLEXITY_API_KEY = "${PERPLEXITY_API_KEY}"
```

**Note**: The `PERPLEXITY_API_KEY` must be set in your KITTY `.env` file or system environment.

### GitHub API

```toml
[[mcp_servers]]
name = "github"
transport = "stdio"
command = "npx"
args = ["-y", "@modelcontextprotocol/server-github"]
prompt = "GitHub repository access"

[mcp_servers.env]
GITHUB_TOKEN = "${GITHUB_TOKEN}"
```

### Supabase Database

```toml
[[mcp_servers]]
name = "supabase"
transport = "stdio"
command = "npx"
args = ["-y", "@supabase/mcp-server-supabase", "--supabase-url", "https://xxx.supabase.co"]
prompt = "Supabase database access"

[mcp_servers.env]
SUPABASE_SERVICE_ROLE_KEY = "${SUPABASE_SERVICE_ROLE_KEY}"
```

## KITTY Auto-Discovery

When running in the KITTY environment, kitty-code automatically discovers and connects to these MCP servers:

| Server | URL | Capabilities |
|--------|-----|--------------|
| `kitty_brain` | http://localhost:8000/mcp | Query routing, research, orchestration |
| `kitty_cad` | http://localhost:8200/mcp | 3D model generation (Zoo, Tripo, CadQuery) |
| `kitty_fab` | http://localhost:8300/mcp | Printer control, slicing, queue management |
| `kitty_discovery` | http://localhost:8500/mcp | Network device scanning |

These are configured automatically based on service health checks.

## Environment Variable Handling

### Secure API Key Management

API keys should never be committed to version control. Use environment variable references:

```toml
[mcp_servers.env]
API_KEY = "${MY_API_KEY}"  # Resolved from system environment at runtime
```

kitty-code automatically loads API keys from:
1. `~/.kitty-code/.env` (kitty-code's own env file)
2. `/Users/Shared/Coding/KITT/.env` (KITTY project env file)

Supported prefixes that are auto-loaded from KITTY's .env:
- `OLLAMA_*`
- `MISTRAL_*`
- `OPENAI_*`
- `ANTHROPIC_*`
- `PERPLEXITY_*`
- `GOOGLE_*`

### Adding New API Keys

1. Add the key to your `.env` file (gitignored):
   ```bash
   echo "MY_API_KEY=your-key-here" >> /Users/Shared/Coding/KITT/.env
   ```

2. Reference it in your MCP config:
   ```toml
   [mcp_servers.env]
   MY_API_KEY = "${MY_API_KEY}"
   ```

## Semantic Tool Selection

kitty-code uses semantic tool selection to reduce context usage and improve response quality. Tools are selected based on query keywords:

| Query Type | Included Tools | Excluded |
|------------|----------------|----------|
| Search/Research | perplexity, kitty_brain | bash |
| Browser | chrome-devtools | bash |
| File Operations | filesystem, read_file, write_file | - |
| Code/Development | bash, grep, all file tools | - |
| Memory | memory, kitty_mem | - |

This means when you ask a search question, kitty-code won't offer bash (preventing curl workarounds) and will prioritize dedicated search tools.

## Troubleshooting

### Server Not Loading

1. Check server connectivity:
   ```bash
   # For HTTP servers
   curl -X POST http://localhost:3000/mcp -H "Content-Type: application/json"

   # For STDIO servers, test manually
   npx -y @modelcontextprotocol/server-memory
   ```

2. Verify API keys are set:
   ```bash
   echo $PERPLEXITY_API_KEY
   ```

3. Check logs in kitty-code TUI (Ctrl+L for log panel)

### Tools Not Available

1. Use `/mcp` to verify server is listed
2. Check that the server name matches expected tool prefixes
3. Restart kitty-code after config changes

### Docker-based Servers

For Docker-based MCP servers like perplexity-ask:

1. Ensure Docker is running
2. Pull the image first: `docker pull mcp/perplexity-ask`
3. Verify the container can start: `docker run --rm mcp/perplexity-ask --help`

## Creating Custom MCP Servers

See the [MCP Specification](https://modelcontextprotocol.io/) for creating your own servers.

Basic Python server example:
```python
from mcp.server import Server
from mcp.server.stdio import stdio_server

server = Server("my-server")

@server.tool()
async def my_tool(param: str) -> str:
    """My custom tool description."""
    return f"Result: {param}"

async def main():
    async with stdio_server() as (read, write):
        await server.run(read, write)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

## See Also

- [kitty-code README](../README.md)
- [KITTY Project Documentation](../../../README.md)
- [MCP Specification](https://modelcontextprotocol.io/)
