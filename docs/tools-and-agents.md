# KITTY Tools and Agents

Complete guide to KITTY's tool-aware agentic system, including MCP servers, ReAct agent, and safety integration.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [MCP Servers](#mcp-servers)
- [ReAct Agent](#react-agent)
- [Safety and Permissions](#safety-and-permissions)
- [Configuration](#configuration)
- [Usage Examples](#usage-examples)
- [Testing](#testing)
- [Implementation Details](#implementation-details)

## Overview

KITTY's agentic system enables autonomous tool use through:

1. **MCP (Model Context Protocol) Servers** - Standardized tool interfaces for CAD generation, Home Assistant control, and semantic memory
2. **ReAct Agent** - Reasoning + Acting pattern for iterative problem-solving with tools
3. **Safety Layer** - Hazard workflow integration and permission management
4. **Agentic Routing** - Smart routing that automatically engages agent when tools would help

### Key Benefits

- **Offline-First**: Uses local llama.cpp with Qwen2.5 for tool calling
- **Safe by Default**: Hazard workflow integration prevents dangerous operations
- **Cost-Aware**: Permission checks for cloud tools with budget tracking
- **Extensible**: Easy to add new MCP servers and tools

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         User Request                             │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                      BrainOrchestrator                           │
│  • Retrieves relevant memories                                   │
│  • Enriches prompt with context                                  │
│  • Calls generate_response(use_agent=True)                       │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                        BrainRouter                               │
│  • Decides routing tier (local vs cloud)                         │
│  • If use_agent=True → invoke ReAct agent                        │
│  • Otherwise → standard LLM call                                 │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                         ReAct Agent                              │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ Iteration Loop (max 10):                                  │  │
│  │  1. Thought: Reason about what to do next                 │  │
│  │  2. Action: Call tool via SafeToolExecutor (if needed)    │  │
│  │  3. Observation: Process tool results                     │  │
│  │  4. Repeat until answer found                             │  │
│  └───────────────────────────────────────────────────────────┘  │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                     SafeToolExecutor                             │
│  • Classifies tools by safety level                             │
│  • Hazard checks for dangerous operations                       │
│  • Permission checks for cloud tools                            │
│  • Routes to appropriate MCP server                             │
└────────────────────────────┬────────────────────────────────────┘
                             │
           ┌─────────────────┼─────────────────┐
           │                 │                 │
           ▼                 ▼                 ▼
    ┌──────────┐      ┌──────────┐     ┌──────────┐
    │   CAD    │      │   Home   │     │  Memory  │
    │   MCP    │      │ Assistant│     │   MCP    │
    │  Server  │      │   MCP    │     │  Server  │
    └──────────┘      └──────────┘     └──────────┘
         │                 │                 │
         ▼                 ▼                 ▼
    Zoo/Tripo         HA REST API       Qdrant Vector DB
```

## MCP Servers

KITTY implements three MCP servers, each providing specialized tools.

### CAD MCP Server

**Location**: `services/mcp/src/mcp/servers/cad_server.py`

Wraps CAD generation APIs (Zoo, Tripo, local) with a unified tool interface.

**Provider Selection Guide:**

- **Zoo CAD** (Parametric/Engineering)
  - Best for: Engineering-grade parts, mounting brackets, mechanical fittings, parametric designs
  - Technology: KCL (parametric modeling language) - fully editable code
  - Output formats: STEP (CAD software), STL (3D printing), GLTF (visualization)
  - Strengths: Precise dimensions, parametric editing, CAD software integration
  - Use cases: Functional parts, assemblies, mechanical components, fixtures

- **Tripo** (Organic/Artistic)
  - Best for: Organic models, artistic designs, visual/aesthetic pieces, characters
  - Technology: Image-to-3D, text-to-3D, multi-view reconstruction
  - Output formats: GLTF/GLB (web/game), OBJ (universal), FBX (animation)
  - Strengths: Photorealistic textures, organic shapes, rapid iteration from images
  - Use cases: Decorative objects, character models, artistic designs, concept visualization

- **Local** (Experimental)
  - Best for: Offline generation, privacy-sensitive designs
  - Technology: TripoSR, InstantMesh (local inference)
  - Limitations: Requires GPU, slower than cloud APIs

#### Tools

**generate_cad_model**
- Generates 3D CAD models from text descriptions
- Parameters:
  - `description` (string, required): Text description of object to generate
  - `format` (string, optional): Output format (stl, step, obj, fbx) - default: stl
  - `provider` (string, optional): CAD provider - default: zoo
    - `zoo`: Parametric/engineering models (recommended for functional parts)
    - `tripo`: Organic/artistic models (recommended for visual/aesthetic pieces)
    - `local`: Offline generation (experimental)
  - `quality` (string, optional): Quality level (draft, standard, high) - default: standard
- Returns: Model URL and metadata
- Safety: Cloud tool - requires budget approval

#### Resources

**cad://recent-models**
- Lists recently generated CAD models
- Useful for retrieving model history

**Example - Engineering Part (Zoo):**
```python
result = await cad_server.execute_tool(
    "generate_cad_model",
    {
        "description": "Mounting bracket with 4x M5 holes, 50mm x 30mm, 5mm thickness",
        "format": "step",  # STEP for CAD software import
        "provider": "zoo",  # Parametric/engineering
        "quality": "standard"
    }
)
# Returns: {"model_url": "s3://...", "format": "step", "kcl_code": "const part = ..."}
```

**Example - Organic Model (Tripo):**
```python
result = await cad_server.execute_tool(
    "generate_cad_model",
    {
        "description": "Decorative dragon figurine, scales and wings",
        "format": "glb",  # GLTF for web/game engines
        "provider": "tripo",  # Organic/artistic
        "quality": "high"
    }
)
# Returns: {"model_url": "s3://...", "format": "glb", "textures": [...]}
```

### Home Assistant MCP Server

**Location**: `services/mcp/src/mcp/servers/homeassistant_server.py`

Provides voice-controlled device management through Home Assistant integration.

#### Tools

**control_device**
- Call Home Assistant services (turn_on, turn_off, toggle, set_temperature, etc.)
- Parameters:
  - `entity_id` (string, required): HA entity ID (e.g., "light.workshop")
  - `action` (string, required): Action to perform (turn_on, turn_off, toggle, etc.)
  - `parameters` (object, optional): Action-specific parameters (e.g., brightness, temperature)
- Returns: Success status and new state
- Safety: Hazardous tool - some actions require hazard workflow confirmation
  - Unlocking locks requires "Confirm: proceed" phrase
  - Power tools require explicit confirmation

**get_entity_state**
- Query current state of any Home Assistant entity
- Parameters:
  - `entity_id` (string, required): HA entity ID
- Returns: Entity state and attributes
- Safety: Free tool - no restrictions

**list_entities**
- List all available Home Assistant entities
- Parameters:
  - `domain` (string, optional): Filter by domain (light, switch, lock, etc.)
- Returns: List of entities with IDs and friendly names
- Safety: Free tool - no restrictions

#### Resources

**homeassistant://entities**
- Real-time dump of all entity states
- Useful for understanding device availability

**Example:**
```python
# Check if lights are on
state = await ha_server.execute_tool(
    "get_entity_state",
    {"entity_id": "light.workshop"}
)

# Turn on lights
result = await ha_server.execute_tool(
    "control_device",
    {
        "entity_id": "light.workshop",
        "action": "turn_on",
        "parameters": {"brightness": 255}
    }
)
```

### Memory MCP Server

**Location**: `services/mcp/src/mcp/servers/memory_server.py`

Provides semantic memory storage and retrieval using Qdrant vector database.

#### Tools

**store_memory**
- Store memories with semantic embeddings
- Parameters:
  - `content` (string, required): Memory content to store
  - `conversation_id` (string, optional): Conversation context
  - `user_id` (string, optional): User context
  - `metadata` (object, optional): Additional metadata
- Returns: Memory ID and storage confirmation
- Safety: Free tool - no restrictions

**recall_memory**
- Search memories using semantic similarity
- Parameters:
  - `query` (string, required): Search query
  - `conversation_id` (string, optional): Filter by conversation
  - `user_id` (string, optional): Filter by user
  - `limit` (integer, optional): Max results (default: 5)
  - `score_threshold` (float, optional): Min similarity score (default: 0.7)
- Returns: List of relevant memories with scores
- Safety: Free tool - no restrictions

**delete_memory**
- Delete specific memories by ID
- Parameters:
  - `memory_id` (string, required): Memory ID to delete
- Returns: Deletion confirmation
- Safety: Free tool - no restrictions

#### Resources

**memory://stats**
- Memory system statistics (total memories, by user, by conversation)

**Example:**
```python
# Store a memory
result = await memory_server.execute_tool(
    "store_memory",
    {
        "content": "User prefers 10mm mounting holes for brackets",
        "conversation_id": "conv_123",
        "user_id": "jeremiah",
        "metadata": {"category": "preferences"}
    }
)

# Recall relevant memories
memories = await memory_server.execute_tool(
    "recall_memory",
    {
        "query": "mounting bracket design preferences",
        "user_id": "jeremiah",
        "limit": 3,
        "score_threshold": 0.75
    }
)
```

## ReAct Agent

**Location**: `services/brain/src/brain/agents/react_agent.py`

The ReAct (Reasoning + Acting) agent implements an iterative problem-solving loop.

### How It Works

1. **Initial State**: Agent receives user query and list of available tools
2. **Reasoning Loop** (max 10 iterations):
   - **Thought**: LLM reasons about what to do next
   - **Action**: If needed, LLM selects a tool and provides arguments
   - **Observation**: Tool executes and returns results
   - **Continue**: Loop repeats until answer is found or max iterations reached
3. **Final Answer**: Agent synthesizes observations into user response

### Agent Prompt Format

```
You are KITTY, a warehouse-grade creative and operational AI assistant.

## TOOL USAGE (ReAct Pattern)

When responding, use this pattern:

1. **Thought**: Reason about what you need to do next
2. **Action**: If you need information or to perform an action, call a tool:
   <tool_call>{"name": "tool_name", "arguments": {...}}</tool_call>
3. **Observation**: After calling a tool, you'll receive results
4. **Repeat**: Continue thinking and acting until you have enough information
5. **Answer**: When ready, provide your final answer without any tool calls

### Tools Available:
- **generate_cad_model**: Generate 3D CAD models from descriptions
- **control_device**: Control Home Assistant devices
- **store_memory**: Store semantic memories
- ...

USER QUERY:
{user_query}

Think step-by-step and use tools as needed.

Thought:
```

### Response Parsing

Agent parses LLM responses for:

1. **Thoughts**: Text before `<tool_call>` tags (reasoning process)
2. **Tool Calls**: XML format `<tool_call>{"name": "...", "arguments": {...}}</tool_call>`
3. **Final Answer**: Response without tool calls (indicates completion)

### Example Execution

**User Query**: "Generate a mounting bracket and turn on the workshop lights"

**Iteration 1**:
- Thought: "I need to generate a CAD model for a mounting bracket and control the workshop lights"
- Action: `<tool_call>{"name": "generate_cad_model", "arguments": {"description": "mounting bracket"}}</tool_call>`
- Observation: "Model generated: s3://models/bracket_abc123.stl"

**Iteration 2**:
- Thought: "CAD model created successfully. Now I need to turn on the workshop lights"
- Action: `<tool_call>{"name": "control_device", "arguments": {"entity_id": "light.workshop", "action": "turn_on"}}</tool_call>`
- Observation: "Light turned on successfully. Current state: on, brightness: 255"

**Iteration 3**:
- Thought: "Both tasks completed successfully"
- Answer: "I've generated a mounting bracket CAD model (available at s3://models/bracket_abc123.stl) and turned on the workshop lights."

## Safety and Permissions

KITTY implements two safety layers: hazard workflow integration and permission management.

### Hazard Workflow Integration

**Location**: `services/brain/src/brain/tools/executor.py`

Certain operations are classified as hazardous and require explicit confirmation.

#### Hazardous Operations

1. **lock.unlock** - Unlocking doors
   - Requires user to say "Confirm: proceed" (configurable via `HAZARD_CONFIRMATION_PHRASE`)
   - Checks zone permissions
   - Logs all unlock attempts

2. **power.enable** - Enabling power tools
   - Requires explicit confirmation
   - Prevents accidental activation

#### How It Works

```python
# SafeToolExecutor classifies tools
if tool_name == "control_device":
    action = arguments.get("action")
    if action == "unlock" or "unlock" in action:
        # Trigger hazard workflow
        allowed, response = await hazard_workflow.process_device_intent(
            intent="unlock",
            device_id=arguments["entity_id"],
            zone_id=zone,
            user_id=user_id,
            signature=None  # Voice signature for voice approval
        )
        if not allowed:
            return ToolResult(
                success=False,
                output=response.get("message", "Operation denied"),
                metadata={"hazard_blocked": True}
            )
```

### Permission Management

**Location**: `services/brain/src/brain/routing/permission.py`

Cloud tools (those that cost money) require budget approval.

#### Cloud Tools

1. **generate_cad_model** - Costs $0.10-$1.00 per model (Zoo/Tripo APIs)
2. Future: Online LLM calls (OpenAI, Anthropic, Perplexity)

#### How It Works

```python
# Before executing cloud tool
if self._is_cloud_tool(tool_name):
    estimated_cost = self._estimate_tool_cost(tool_name, arguments)

    # Check if approved
    allowed, reason = await permission_manager.check_permission(
        tool_name=tool_name,
        estimated_cost=estimated_cost,
        conversation_id=conversation_id,
        user_id=user_id
    )

    if not allowed:
        return ToolResult(
            success=False,
            output=f"Permission denied: {reason}",
            metadata={"budget_blocked": True, "estimated_cost": estimated_cost}
        )
```

#### Budget Configuration

Set in `.env`:

```bash
# Budget limit per conversation (default: $0.50)
BUDGET_PER_TASK_USD=0.50

# Password required for cloud tool approval (default: omega)
API_OVERRIDE_PASSWORD=omega
```

When a cloud tool is needed:
1. User is prompted: "Tool 'generate_cad_model' costs $0.50. Enter password to approve:"
2. User enters password (e.g., "omega")
3. If correct, tool executes and cost is tracked
4. Subsequent tools in same conversation check remaining budget

## Configuration

### Environment Variables

Add to `.env`:

```bash
# Enable agentic mode (default: false)
AGENTIC_MODE_ENABLED=true

# Maximum iterations for ReAct agent (default: 10)
REACT_MAX_ITERATIONS=10

# MCP Tool Servers
CAD_SERVICE_URL=http://cad:8200
HOME_ASSISTANT_URL=http://192.168.0.172:8123
HOME_ASSISTANT_TOKEN=<HOME_ASSISTANT_LONG_LIVED_TOKEN>

# Safety Configuration
HAZARD_CONFIRMATION_PHRASE="Confirm: proceed"
BUDGET_PER_TASK_USD=0.50
API_OVERRIDE_PASSWORD=omega

# llama.cpp Configuration (for tool calling)
LLAMACPP_HOST=http://localhost:8083
LLAMACPP_TOOL_CALLING=1  # Enable tool calling support
```

### llama.cpp Setup

Tool calling requires specific llama.cpp flags:

```bash
# Start llama.cpp with tool calling enabled
LLAMACPP_TOOL_CALLING=1 \
LLAMACPP_MODELS_DIR="/Users/Shared/Coding/models" \
LLAMACPP_PRIMARY_MODEL="Qwen2.5-Coder-32B-Instruct-GGUF/qwen2.5-coder-32b-instruct-q3_k_m.gguf" \
LLAMACPP_PRIMARY_ALIAS="kitty-coder" \
LLAMACPP_PORT="8083" \
LLAMACPP_CTX="8192" \
LLAMACPP_N_GPU_LAYERS="33" \
LLAMACPP_FLASH_ATTN="1" \
./ops/scripts/start-llamacpp.sh
```

The `LLAMACPP_TOOL_CALLING=1` flag adds `--jinja -fa` to llama-server, enabling:
- Jinja template support for Qwen2.5's tool calling format
- Function attachment (`-fa`) for proper tool schema handling

### Docker Compose

MCP servers are Python libraries imported by the Brain service:

```yaml
services:
  brain:
    environment:
      CAD_SERVICE_URL: http://cad:8200
      HOME_ASSISTANT_URL: ${HOME_ASSISTANT_URL}
      HOME_ASSISTANT_TOKEN: ${HOME_ASSISTANT_TOKEN}
    depends_on:
      - cad
      - homeassistant
      - mem0-mcp
    volumes:
      - ../../services/mcp:/app/services/mcp:ro  # MCP servers
```

## Usage Examples

### Example 1: CAD Generation with Memory

```python
from brain.orchestrator import BrainOrchestrator

# User: "Generate a small mounting bracket similar to the one I designed last week"

result = await orchestrator.generate_response(
    conversation_id="conv_123",
    request_id="req_456",
    prompt="Generate a small mounting bracket similar to the one I designed last week",
    user_id="jeremiah",
    use_agent=True  # Enable agentic mode
)

# Agent execution:
# 1. Recalls memory: "User prefers 10mm holes, 5mm thickness for brackets"
# 2. Generates CAD: generate_cad_model("mounting bracket, 10mm holes, 5mm thick")
# 3. Stores memory: "Generated bracket design on 2024-11-05"
# 4. Returns: "I've generated a mounting bracket based on your preferences..."
```

### Example 2: Smart Home Control

```python
# User: "Turn on the workshop lights and laser engraver"

result = await orchestrator.generate_response(
    conversation_id="conv_789",
    request_id="req_012",
    prompt="Turn on the workshop lights and laser engraver",
    user_id="jeremiah",
    use_agent=True
)

# Agent execution:
# 1. Lists entities to find "light.workshop" and "switch.laser_engraver"
# 2. Turns on light: control_device("light.workshop", "turn_on")
# 3. Attempts laser: control_device("switch.laser_engraver", "turn_on")
#    → Blocked by hazard workflow: "Power tool activation requires confirmation"
# 4. Returns: "Workshop lights are on. Laser engraver requires confirmation..."
```

### Example 3: Programmatic Tool Use

```python
from brain.routing.router import BrainRouter, RoutingRequest
from brain.routing.config import RoutingConfig

# Initialize router with tool support
router = BrainRouter(
    config=RoutingConfig(),
    tool_mcp_client=mcp_client,
    permission_manager=permission_manager,
    hazard_workflow=hazard_workflow
)

# Route with agentic mode
request = RoutingRequest(
    conversation_id="test_conv",
    request_id="test_req",
    prompt="List all lights in the workshop and turn them on",
    use_agent=True
)

result = await router.route(request)

print(f"Success: {result.success}")
print(f"Output: {result.output}")
print(f"Tools used: {result.metadata.get('tools_used', [])}")
print(f"Iterations: {result.metadata.get('iterations', 0)}")
```

## Testing

### Unit Tests

**test_parser_only.py** - Qwen2.5 XML parser tests (no dependencies):
```bash
python tests/test_parser_only.py
```

Tests:
- Single tool call parsing
- Multiple tool calls in one response
- JSON argument parsing
- Malformed XML handling
- Edge cases

### Live Integration Tests

**test_live_tool_calling.py** - Full integration with llama.cpp:
```bash
# Requires llama.cpp running on port 8083 with tool calling enabled
python tests/test_live_tool_calling.py
```

Tests:
1. XML format parsing
2. Simple tool call (get_weather)
3. Multiple tool selection (weather vs search_web)

Results:
```
✓ PASS - XML Parsing
✓ PASS - Simple Tool Call
✓ PASS - Multiple Tools

Results: 3/3 tests passed
```

### MCP Server Tests

Test individual MCP servers:

```python
# Test CAD server
from mcp.servers.cad_server import CADMCPServer

server = CADMCPServer(cad_service_url="http://localhost:8200")
tools = server.list_tools()
print(f"Available tools: {[t['function']['name'] for t in tools]}")

result = await server.execute_tool(
    "generate_cad_model",
    {"description": "test bracket", "provider": "zoo"}
)
print(f"Result: {result}")

# Test Home Assistant server
from mcp.servers.homeassistant_server import HomeAssistantMCPServer

server = HomeAssistantMCPServer(
    base_url="http://192.168.0.172:8123",
    token="your_token_here"
)
tools = server.list_tools()
result = await server.execute_tool(
    "list_entities",
    {"domain": "light"}
)
print(f"Lights: {result.output}")
```

### ReAct Agent Tests

Test agent execution:

```python
from brain.agents.react_agent import ReActAgent
from brain.tools.mcp_client import MCPClient

# Initialize agent
agent = ReActAgent(
    llm_client=llama_cpp_client,
    tool_client=mcp_client,
    max_iterations=10
)

# Run agent
result = await agent.run(
    query="Generate a bracket and turn on workshop lights",
    conversation_id="test_conv",
    user_id="test_user"
)

print(f"Success: {result.success}")
print(f"Answer: {result.answer}")
print(f"Steps taken: {len(result.steps)}")
for i, step in enumerate(result.steps, 1):
    print(f"\nStep {i}:")
    print(f"  Thought: {step.thought}")
    print(f"  Action: {step.action}")
    print(f"  Observation: {step.observation}")
```

## Implementation Details

### File Structure

```
services/
├── brain/
│   └── src/brain/
│       ├── agents/
│       │   ├── __init__.py
│       │   └── react_agent.py              # ReAct agent implementation
│       ├── prompts/
│       │   ├── __init__.py
│       │   ├── expert_system.py            # System prompts with ReAct
│       │   └── tool_formatter.py           # Tool formatting utilities
│       ├── routing/
│       │   ├── router.py                   # Agentic routing
│       │   ├── permission.py               # Budget/permission management
│       │   └── pricing.py                  # Cost estimation
│       └── tools/
│           ├── __init__.py
│           ├── mcp_client.py               # MCP client wrapper
│           └── executor.py                 # Safe tool executor
└── mcp/
    └── src/mcp/
        ├── protocol/
        │   ├── __init__.py
        │   ├── base.py                     # MCPServer base class
        │   └── types.py                    # ToolResult, etc.
        └── servers/
            ├── __init__.py
            ├── cad_server.py               # CAD MCP server
            ├── homeassistant_server.py     # Home Assistant MCP server
            └── memory_server.py            # Memory MCP server
```

### Key Classes

**MCPServer** (`services/mcp/src/mcp/protocol/base.py`):
- Abstract base class for all MCP servers
- Provides `list_tools()`, `execute_tool()`, `list_resources()`, `read_resource()`
- Subclasses override to implement specific tools

**ReActAgent** (`services/brain/src/brain/agents/react_agent.py`):
- `run(query, conversation_id, user_id)` - Main agent loop
- `run_single_action(query, tool_name, arguments)` - Direct tool execution
- Builds ReAct prompts with tool context
- Parses LLM responses for thoughts/actions/answers
- Executes tools via SafeToolExecutor

**SafeToolExecutor** (`services/brain/src/brain/tools/executor.py`):
- Wraps MCPClient with safety checks
- `execute_tool(tool_name, arguments, conversation_id, user_id)` - Execute with safety
- Classifies tools as hazardous, cloud, or free
- Integrates hazard workflow and permission manager
- Tracks tool usage and costs

**BrainRouter** (`services/brain/src/brain/routing/router.py`):
- `route(RoutingRequest)` - Main routing logic
- `_invoke_agent(request)` - Agentic routing path
- Decides local vs cloud based on confidence
- Integrates permission checks for cloud calls
- Returns RoutingResult with metadata

### Adding New Tools

To add a new tool:

1. **Create MCP Server** (if new domain):
```python
from mcp.protocol.base import MCPServer, ToolResult

class MyMCPServer(MCPServer):
    def __init__(self, config):
        super().__init__()
        self._config = config
        self._register_tools()

    def _register_tools(self):
        self._tools.append({
            "type": "function",
            "function": {
                "name": "my_tool",
                "description": "What this tool does",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "param1": {"type": "string", "description": "..."}
                    },
                    "required": ["param1"]
                }
            }
        })

    async def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> ToolResult:
        if tool_name == "my_tool":
            result = await self._do_something(arguments["param1"])
            return ToolResult(success=True, output=result)
        raise ValueError(f"Unknown tool: {tool_name}")
```

2. **Register in MCP Client**:
```python
# services/brain/src/brain/tools/mcp_client.py
from mcp.servers.my_server import MyMCPServer

class MCPClient:
    def __init__(self, ...):
        # ...
        self._servers["my_domain"] = MyMCPServer(config)
```

3. **Configure Safety** (if needed):
```python
# services/brain/src/brain/tools/executor.py
class SafeToolExecutor:
    def __init__(self, ...):
        # ...
        self.add_cloud_tool("my_tool", provider="my_api", cost_per_call=0.10)
        # OR
        self.add_hazardous_tool("my_tool", hazard_type="dangerous_action")
```

4. **Update Environment**:
```bash
# .env
MY_SERVICE_URL=http://my-service:8080
MY_API_KEY=secret
```

5. **Test**:
```python
result = await agent.run(
    query="Use my new tool to do something",
    conversation_id="test",
    user_id="test"
)
```

### Performance Considerations

1. **Tool Execution Latency**:
   - CAD generation: 30-60 seconds (cloud APIs)
   - Home Assistant: <500ms (local network)
   - Memory: <100ms (local Qdrant)

2. **Agent Iterations**:
   - Most queries: 2-3 iterations
   - Complex multi-step: 5-10 iterations
   - Max iterations: 10 (configurable)

3. **LLM Performance**:
   - Qwen2.5-Coder-32B-Q3_K_M: ~20 tokens/sec on M1 Max
   - Context size: 8192 tokens
   - Tool call parsing: <10ms

4. **Optimization Tips**:
   - Use `run_single_action()` for direct tool calls (bypass reasoning)
   - Reduce `REACT_MAX_ITERATIONS` for time-sensitive operations
   - Cache tool results in memory (avoid redundant calls)
   - Use compact tool formatting in prompts to save tokens

## Troubleshooting

### llama.cpp not generating tool calls

**Problem**: LLM responds with text instead of `<tool_call>` XML

**Solutions**:
1. Verify tool calling enabled: `LLAMACPP_TOOL_CALLING=1`
2. Check llama-server flags: should see `--jinja -fa` in logs
3. Confirm model supports function calling (Qwen2.5 recommended)
4. Check prompt includes ReAct instructions and tool list

### Hazard workflow blocking operations

**Problem**: "Permission denied" for legitimate operations

**Solutions**:
1. Check hazard confirmation phrase: `HAZARD_CONFIRMATION_PHRASE="Confirm: proceed"`
2. Verify user has zone permissions in Safety service
3. Check logs for specific hazard workflow denial reason
4. For testing, temporarily disable hazard checks in SafeToolExecutor

### Budget/permission errors

**Problem**: "Budget exceeded" or "Permission denied" for cloud tools

**Solutions**:
1. Check remaining budget: `BUDGET_PER_TASK_USD=0.50`
2. Verify password correct: `API_OVERRIDE_PASSWORD=omega`
3. Reset budget by starting new conversation (new conversation_id)
4. For development, set high budget: `BUDGET_PER_TASK_USD=100.00`

### MCP server connection errors

**Problem**: "Connection refused" or "Service unavailable" for tools

**Solutions**:
1. Verify service URLs in `.env`:
   - `CAD_SERVICE_URL=http://cad:8200`
   - `HOME_ASSISTANT_URL=http://192.168.0.172:8123`
2. Check Docker Compose services running: `docker compose ps`
3. Test service connectivity: `curl http://cad:8200/health`
4. Check service logs: `docker compose logs cad`

### Agent not completing

**Problem**: Agent reaches max iterations without answer

**Solutions**:
1. Increase max iterations: `REACT_MAX_ITERATIONS=20`
2. Check LLM response parsing (might not detect final answer)
3. Simplify query or provide more context
4. Review agent steps in logs to see where it's stuck
5. Use `run_single_action()` for direct tool calls if reasoning not needed

## Future Enhancements

Planned improvements:

1. **Streaming Support**: Stream agent thoughts and tool calls in real-time
2. **Tool Chaining**: Automatic dependency resolution (e.g., "list_entities before control_device")
3. **Parallel Tool Execution**: Execute independent tools concurrently
4. **Tool Learning**: Learn which tools work best for specific queries
5. **Voice Approval**: Biometric voice confirmation for hazard workflow
6. **Cost Optimization**: Automatically switch to cheaper providers when quality doesn't matter
7. **Tool Metrics**: Track tool success rates, latency, and user satisfaction
8. **Dynamic Tool Discovery**: Auto-discover new MCP servers at runtime

## References

- [MCP Protocol Specification](https://anthropic.com/mcp) - Anthropic's Model Context Protocol
- [ReAct Paper](https://arxiv.org/abs/2210.03629) - Reasoning and Acting in Language Models
- [Qwen2.5 Function Calling](https://qwen.readthedocs.io/en/latest/function_calling.html) - Native tool support
- [llama.cpp Documentation](https://github.com/ggerganov/llama.cpp) - Local LLM inference
- [Home Assistant REST API](https://developers.home-assistant.io/docs/api/rest/) - Device control

## License

Copyright (c) 2024 KITTY Project. All rights reserved.
