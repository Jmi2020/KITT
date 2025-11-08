# Integration Guide: Web Search Tools for llama.cpp with Athene V2 Agent

## Overview

This guide covers integrating web search capabilities into **llama.cpp** running **Athene V2 Agent** and **Llama 3.3 70B**. You'll find setup instructions for both free and paid options.  

> KITTY Status (Nov 2025): Search queries now route through **SearXNG → Brave → DuckDuckGo** and full article extraction is handled by **Jina Reader** with a BeautifulSoup fallback. Configure `SEARXNG_BASE_URL`, `BRAVE_SEARCH_API_KEY`, and `JINA_API_KEY` in `.env` to mirror this setup.

> **KITTY integration (2025-11-06)**  
> The brain service now routes `web_search` through a three-tier cascade:
> 1. **SearXNG (self-hosted, free)** — point `SEARXNG_BASE_URL` to your Docker instance and KITTY will use it first.  
> 2. **Brave Search API (free tier + paid expansion)** — set `BRAVE_SEARCH_API_KEY` to unlock a higher-quality index before spending Perplexity credits.  
> 3. **DuckDuckGo** — retained as a safe fallback when both of the above are unavailable.  
>  
> Configure the env vars in `.env`, restart the `research`/`brain` services, and the MCP `web_search` tool will automatically respect this order.

---

## Prerequisites

- **llama.cpp** running with `llama-server` or `llama-cli`
- **Athene V2 Agent GGUF model** (function-calling enabled)
- **Python 3.10+** with pip
- **Docker** (for SearXNG and containerized solutions)
- **Mac Studio M3 Ultra** (or similar system with sufficient VRAM for 70B model)

### Start llama-server

```bash
# Load Athene V2 Agent for function calling
./llama-server -m athene-v2-agent-q4_k_m.gguf \
  --host 0.0.0.0 --port 8080 \
  -n 2048 --ctx-size 8096 \
  -ngl 100  # Adjust GPU layers for your hardware
```

For Llama 3.3 70B (if using for context):
```bash
./llama-server -m llama-3.3-70b-q4_k_m.gguf \
  --host 0.0.0.0 --port 8081 \
  -n 2048 --ctx-size 8096 \
  -ngl 100
```

---

# Option 1: SearXNG (Free, Self-Hosted)

## Setup SearXNG with Docker

### Step 1: Create Docker Compose File

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  searxng:
    image: searxng/searxng:latest
    container_name: searxng
    networks:
      - search-network
    ports:
      - "8888:8080"
    environment:
      - SEARXNG_BASE_URL=http://localhost:8888/
    volumes:
      - ./searxng/settings.yml:/etc/searxng/settings.yml:ro
      - ./searxng/limiter.toml:/etc/searxng/limiter.toml:ro
    restart: unless-stopped

networks:
  search-network:
    driver: bridge
```

### Step 2: Launch SearXNG

```bash
mkdir -p searxng
docker-compose up -d
# Verify at http://localhost:8888
```

### Step 3: Create llama-cpp-agent Integration

Install dependencies:

```bash
pip install llama-cpp-agent requests
```

Create `search_agent_searxng.py`:

```python
import requests
from llama_cpp_agent import FunctionCallingAgent, MessagesFormatterType
from llama_cpp_agent.providers import LlamaCppServerProvider
from llama_cpp_agent import LlamaCppFunctionTool
from pydantic import BaseModel, Field
from typing import Optional

# Define search tool
class SearchQuery(BaseModel):
    """Perform a web search using SearXNG"""
    query: str = Field(..., description="Search query string")
    language: str = Field(default="en", description="Language code (e.g., 'en', 'de')")
    
    def run(self):
        """Execute search against local SearXNG instance"""
        try:
            response = requests.get(
                "http://localhost:8888/search",
                params={
                    "q": self.query,
                    "format": "json",
                    "language": self.language,
                    "pageno": 1
                },
                timeout=10
            )
            response.raise_for_status()
            results = response.json()
            
            # Format results
            formatted_results = []
            for result in results.get("results", [])[:5]:  # Top 5 results
                formatted_results.append({
                    "title": result.get("title"),
                    "url": result.get("url"),
                    "snippet": result.get("content")
                })
            return formatted_results
        except Exception as e:
            return {"error": str(e)}

# Set up provider
provider = LlamaCppServerProvider("http://localhost:8080")

# Create search tool
search_tool = LlamaCppFunctionTool(SearchQuery)

# System prompt for agent
system_prompt = """You are a helpful AI assistant with access to real-time web search.
When users ask questions that require current information, use the search tool to find relevant results.
Always cite sources when providing information from search results."""

# Create agent
def send_message_callback(message: str):
    print(f"Agent: {message}")

agent = FunctionCallingAgent(
    provider,
    llama_cpp_function_tools=[search_tool],
    send_message_to_user_callback=send_message_callback,
    messages_formatter_type=MessagesFormatterType.CHATML,
    system_prompt=system_prompt
)

# Test agent
if __name__ == "__main__":
    user_query = "What are the latest developments in AI for 2025?"
    print(f"User: {user_query}")
    agent.generate_response(user_query)
```

Run the agent:

```bash
python search_agent_searxng.py
```

### Cost: **FREE** âœ“
### Effort: **Medium** (Docker + Python)
### Privacy: **Excellent** (Self-hosted)

---

# Option 2: Tavily Search API (Paid, Optimized for AI)

## Setup Tavily Integration

### Step 1: Get API Key

1. Visit [tavily.com](https://tavily.com)
2. Sign up and get your free tier (1,000 searches/month) or paid tier
3. Copy your API key

### Step 2: Install Tavily SDK

```bash
pip install tavily-python llama-cpp-agent
```

### Step 3: Create Integration Script

Create `search_agent_tavily.py`:

```python
from tavily import TavilyClient
from llama_cpp_agent import FunctionCallingAgent, MessagesFormatterType
from llama_cpp_agent.providers import LlamaCppServerProvider
from llama_cpp_agent import LlamaCppFunctionTool
from pydantic import BaseModel, Field
from typing import Optional
import os

# Define Tavily search tool
class TavilySearch(BaseModel):
    """Search the web using Tavily (AI-optimized results)"""
    query: str = Field(..., description="Search query string")
    include_answer: bool = Field(default=True, description="Include AI-generated answer")
    
    def run(self):
        """Execute search using Tavily API"""
        try:
            api_key = os.environ.get("TAVILY_API_KEY")
            if not api_key:
                return {"error": "TAVILY_API_KEY environment variable not set"}
            
            client = TavilyClient(api_key=api_key)
            response = client.search(
                query=self.query,
                include_answer=self.include_answer,
                max_results=5
            )
            
            # Format results
            results = {
                "answer": response.get("answer"),
                "sources": []
            }
            
            for result in response.get("results", []):
                results["sources"].append({
                    "title": result.get("title"),
                    "url": result.get("url"),
                    "content": result.get("content")
                })
            
            return results
        except Exception as e:
            return {"error": str(e)}

# Set up provider
provider = LlamaCppServerProvider("http://localhost:8080")

# Create search tool
tavily_tool = LlamaCppFunctionTool(TavilySearch)

system_prompt = """You are an advanced AI assistant with real-time web search capabilities.
Use Tavily search to answer current questions with the most recent information.
Always cite sources from the search results."""

def send_message_callback(message: str):
    print(f"Agent: {message}")

# Create agent
agent = FunctionCallingAgent(
    provider,
    llama_cpp_function_tools=[tavily_tool],
    send_message_to_user_callback=send_message_callback,
    messages_formatter_type=MessagesFormatterType.CHATML,
    system_prompt=system_prompt
)

if __name__ == "__main__":
    user_query = "What are the latest breakthroughs in quantum computing?"
    print(f"User: {user_query}")
    agent.generate_response(user_query)
```

### Step 3: Run Agent

```bash
export TAVILY_API_KEY="your-api-key-here"
python search_agent_tavily.py
```

### Cost: **$8-10 per 1,000 searches** (or free tier 1,000/month)
### Effort: **Easy** (Simple API)
### Quality: **Excellent** (AI-optimized results)

---

# Option 3: Brave Search API (Paid, Privacy-Focused)

## Setup Brave Search Integration

### Step 1: Get API Key

1. Visit [api.search.brave.com](https://api.search.brave.com)
2. Create account and API key
3. Free tier: 2,000 calls/month

### Step 2: Install Dependencies

```bash
pip install requests llama-cpp-agent
```

### Step 3: Create Integration

Create `search_agent_brave.py`:

```python
import requests
from llama_cpp_agent import FunctionCallingAgent, MessagesFormatterType
from llama_cpp_agent.providers import LlamaCppServerProvider
from llama_cpp_agent import LlamaCppFunctionTool
from pydantic import BaseModel, Field
import os

class BraveSearch(BaseModel):
    """Search using Brave Search API (privacy-focused)"""
    query: str = Field(..., description="Search query")
    
    def run(self):
        """Execute search using Brave API"""
        try:
            api_key = os.environ.get("BRAVE_API_KEY")
            if not api_key:
                return {"error": "BRAVE_API_KEY environment variable not set"}
            
            headers = {
                "Accept": "application/json",
                "X-Subscription-Token": api_key
            }
            
            response = requests.get(
                "https://api.search.brave.com/res/v1/web/search",
                params={"q": self.query, "count": 5},
                headers=headers,
                timeout=10
            )
            response.raise_for_status()
            results = response.json()
            
            formatted_results = []
            for result in results.get("web", []):
                formatted_results.append({
                    "title": result.get("title"),
                    "url": result.get("url"),
                    "description": result.get("description")
                })
            
            return formatted_results
        except Exception as e:
            return {"error": str(e)}

provider = LlamaCppServerProvider("http://localhost:8080")
brave_tool = LlamaCppFunctionTool(BraveSearch)

def send_message_callback(message: str):
    print(f"Agent: {message}")

agent = FunctionCallingAgent(
    provider,
    llama_cpp_function_tools=[brave_tool],
    send_message_to_user_callback=send_message_callback,
    messages_formatter_type=MessagesFormatterType.CHATML
)

if __name__ == "__main__":
    user_query = "Recent developments in renewable energy"
    print(f"User: {user_query}")
    agent.generate_response(user_query)
```

Run it:

```bash
export BRAVE_API_KEY="your-api-key-here"
python search_agent_brave.py
```

### Cost: **Free tier 2,000/month, then $3-5 per 1,000**
### Effort: **Easy** (Simple API)
### Privacy: **Excellent** (No tracking)

---

# Option 4: MCP Server Integration (Advanced)

## Setup with SearXNG MCP

### Step 1: Install MCP Server for SearXNG

```bash
npm install -g @mmind-ai/mcp-searxng-server
# Or
pip install mcp-searxng-server
```

### Step 2: Configure MCP Server Config

Create `~/.config/mcp-servers/searxng.json`:

```json
{
  "command": "mcp-server-searxng",
  "args": [
    "--base-url", "http://localhost:8888"
  ],
  "env": {
    "SEARXNG_API_KEY": ""
  }
}
```

### Step 3: Create llama-cpp-agent MCP Bridge

Install MCPHost:

```bash
go install github.com/mark3labs/mcphost@latest
# Or use Docker
docker run -p 3000:3000 -v ~/.config/mcp-servers:/etc/mcp-servers mcphost
```

### Step 4: Use MCP with Athene

Create `agent_with_mcp.py`:

```python
import json
import requests
from llama_cpp_agent import FunctionCallingAgent, MessagesFormatterType
from llama_cpp_agent.providers import LlamaCppServerProvider

# Simulate MCP tool calls through HTTP
def call_mcp_tool(tool_name: str, args: dict):
    """Call MCP server tool"""
    try:
        response = requests.post(
            "http://localhost:3000/tools/call",
            json={
                "tool": tool_name,
                "arguments": args
            }
        )
        return response.json()
    except Exception as e:
        return {"error": str(e)}

# This approach requires custom integration
# Athene V2 supports tool calling via llama-server
provider = LlamaCppServerProvider("http://localhost:8080")

# Define tools as OpenAI-style functions
tools_definition = [
    {
        "type": "function",
        "function": {
            "name": "searxng_search",
            "description": "Search the web using SearXNG",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query"
                    }
                },
                "required": ["query"]
            }
        }
    }
]

# Note: Direct MCP integration with llama.cpp requires custom wrapper
# Recommend using llama-cpp-agent for function calling instead
```

### Cost: **FREE** (SearXNG) or **API costs** (other MCP servers)
### Effort: **High** (MCP setup complex)
### Best for: **Production, multiple tool ecosystems**

---

# Option 5: Combined Setup (Recommended)

## Multi-Tool Fallback Architecture

Create `search_agent_combined.py`:

```python
import requests
import os
from llama_cpp_agent import FunctionCallingAgent, MessagesFormatterType
from llama_cpp_agent.providers import LlamaCppServerProvider
from llama_cpp_agent import LlamaCppFunctionTool
from pydantic import BaseModel, Field
from typing import Union
from enum import Enum

class SearchProvider(str, Enum):
    SEARXNG = "searxng"
    TAVILY = "tavily"
    BRAVE = "brave"

class UniversalSearch(BaseModel):
    """Universal search with fallback support"""
    query: str = Field(..., description="Search query")
    provider: SearchProvider = Field(default=SearchProvider.SEARXNG, description="Search provider")
    
    def run(self):
        """Execute search with fallback chain"""
        results = None
        errors = []
        
        # Try primary provider
        if self.provider == SearchProvider.SEARXNG:
            results = self._searxng_search()
        elif self.provider == SearchProvider.TAVILY:
            results = self._tavily_search()
        elif self.provider == SearchProvider.BRAVE:
            results = self._brave_search()
        
        # Fallback chain
        if not results:
            for fallback in [SearchProvider.BRAVE, SearchProvider.TAVILY, SearchProvider.SEARXNG]:
                if fallback == self.provider:
                    continue
                if fallback == SearchProvider.SEARXNG:
                    results = self._searxng_search()
                elif fallback == SearchProvider.TAVILY:
                    results = self._tavily_search()
                elif fallback == SearchProvider.BRAVE:
                    results = self._brave_search()
                if results:
                    break
        
        return results or {"error": "All search providers failed"}
    
    def _searxng_search(self):
        try:
            response = requests.get(
                "http://localhost:8888/search",
                params={"q": self.query, "format": "json"},
                timeout=10
            )
            results = response.json()
            return [{"title": r["title"], "url": r["url"], "snippet": r["content"]} 
                    for r in results.get("results", [])[:5]]
        except:
            return None
    
    def _tavily_search(self):
        try:
            from tavily import TavilyClient
            client = TavilyClient(api_key=os.environ.get("TAVILY_API_KEY"))
            response = client.search(self.query, max_results=5)
            return response.get("results")
        except:
            return None
    
    def _brave_search(self):
        try:
            headers = {"X-Subscription-Token": os.environ.get("BRAVE_API_KEY")}
            response = requests.get(
                "https://api.search.brave.com/res/v1/web/search",
                params={"q": self.query, "count": 5},
                headers=headers,
                timeout=10
            )
            return response.json().get("web", [])
        except:
            return None

provider = LlamaCppServerProvider("http://localhost:8080")
search_tool = LlamaCppFunctionTool(UniversalSearch)

def send_message_callback(message: str):
    print(f"Agent: {message}")

agent = FunctionCallingAgent(
    provider,
    llama_cpp_function_tools=[search_tool],
    send_message_to_user_callback=send_message_callback,
    messages_formatter_type=MessagesFormatterType.CHATML
)

if __name__ == "__main__":
    query = "What's new in machine learning 2025?"
    print(f"User: {query}")
    agent.generate_response(query)
```

---

# Troubleshooting

## Issue: llama-server won't load model

**Solution:**
```bash
# Check VRAM
nvidia-smi  # or similar for your GPU

# Reduce GPU layers
./llama-server -m model.gguf -ngl 60  # Reduce from 100
```

## Issue: Tool calling not working

**Check:**
1. Model supports function calling (Athene V2 does)
2. llama-server running with correct parameters
3. Tool definitions are valid JSON/Pydantic

```bash
# Test llama-server directly
curl -X POST http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "model",
    "messages": [{"role": "user", "content": "test"}],
    "tools": [{"type": "function", "function": {"name": "test", "description": "test"}}]
  }'
```

## Issue: Search tool not responding

**Debug:**
```python
# Test search directly
import requests
response = requests.get("http://localhost:8888/search", params={"q": "test", "format": "json"})
print(response.status_code, response.json())
```

---

# Performance Optimization

## Mac Studio M3 Ultra (Your Setup)

### Recommended Configuration

```bash
./llama-server \
  -m athene-v2-agent-q4_k_m.gguf \
  --host 0.0.0.0 --port 8080 \
  -n 2048 --ctx-size 8096 \
  -ngl 100 \
  --metal              # Use Metal acceleration
  -t 16                # 16 CPU threads
  -b 512               # Batch size
  --repeat-penalty 1.1 \
  --temp 0.7
```

### Monitor Performance

```bash
# Watch resource usage
watch -n 1 'top -l 1 | head -20'
```

---

# Summary & Recommendation

| Option | Cost | Setup Time | Privacy | Quality | Best For |
|--------|------|-----------|---------|---------|----------|
| SearXNG | FREE | 15 min | Excellent | Good | Privacy-first, hobbyists |
| Tavily | $8-10/1K | 5 min | Good | Excellent | Production, AI-optimized |
| Brave | Free/paid | 5 min | Excellent | Good | Privacy + quality balance |
| Combined | Varies | 20 min | Excellent | Excellent | Production, reliability |

### My Recommendation for Your Setup:

**Start with SearXNG** â†’ Use locally, free, privacy-focused
**Upgrade to Tavily** â†’ When you need production reliability
**Add Brave as fallback** â†’ For 99.9% uptime

---

# Next Steps

1. Start llama-server with Athene V2
2. Choose one integration above
3. Test with sample queries
4. Scale to production with combined setup

For issues or questions, test individual components:
```bash
# Test llama-server
curl http://localhost:8080/health

# Test SearXNG
curl "http://localhost:8888/search?q=test&format=json"

# Test Python agent
python search_agent_searxng.py
```
