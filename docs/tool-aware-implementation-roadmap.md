# KITTY Tool-Aware Agentic System - Implementation Roadmap

## Overview

Transforming KITTY into a tool-aware agent using full MCP protocol, ReAct pattern (reasoning + action loops), and native Qwen2.5 function calling via llama.cpp.

**Total Estimated Effort**: 25-33 hours
**Completed**: 4/19 tasks (~6 hours)
**Remaining**: 15/19 tasks (~20-27 hours)

---

## ✅ Completed (Phase 1 + 2.1)

### Phase 1: Function Calling Infrastructure ✅

**Commits**:
- `3bdcf33` - llama.cpp function calling flags
- `1843ec0` - Tool calling support in LlamaCppClient

**What's Working**:
1. ✅ llama.cpp startup script updated with `--jinja -fa` flags
   - `LLAMACPP_TOOL_CALLING` env var (default: enabled)
   - Enables native Qwen2.5 function calling

2. ✅ Tool response parser (`services/brain/src/brain/tools/parser.py`)
   - Parses Qwen2.5 XML format: `<tool_call>...</tool_call>`
   - Returns structured `ToolCall` objects with name and arguments

3. ✅ LlamaCppClient extended (`services/brain/src/brain/routing/llama_cpp_client.py`)
   - `tools` parameter support (JSON Schema format)
   - Parses and returns `tool_calls` list
   - Backwards compatible

4. ✅ `<user_query>` wrapper + unified prompt builder (`services/brain/src/brain/prompts/unified.py`, documented in `README.md`)
   - Keeps tool instructions + registry in every request while forcing temp=0
   - Prevents hallucinated tool names/params before ReAct loop begins
   - Cornerstone dependency for all subsequent MCP/tool orchestration work

### Phase 2.1: MCP Server Framework ✅

**Commit**: `2ccc379` - MCP server framework

**What's Working**:
4. ✅ MCP base framework (`services/mcp/src/mcp/server.py`)
   - `MCPServer` abstract base class
   - `ToolDefinition`, `ResourceDefinition`, `PromptDefinition` dataclasses
   - `ToolResult` for execution results
   - JSON Schema tool definitions

---

## 🚧 Remaining Work

### Phase 2: MCP Servers (Tasks 5-8, ~6-8 hours)

#### Task 5: Implement CAD MCP Server

**File**: `services/mcp/src/mcp/servers/cad_server.py`

**Tools**:
```python
generate_cad_model:
  description: "Generate a 3D CAD model from text description"
  parameters:
    prompt: str (required)
    provider: enum ["zoo", "tripo", "local"] (optional, default: "zoo")
    output_format: enum ["gltf", "step", "glb"] (optional)
  returns: {"artifact_url": "s3://...", "format": "gltf"}
```

**Resources**:
```python
cad://projects/{id}/artifacts - List CAD artifacts for project
cad://recent - Recently generated models
```

**Implementation**:
```python
from ..server import MCPServer, ToolDefinition, ToolResult
from cad.cycler import CADCycler  # Import existing CAD service

class CADMCPServer(MCPServer):
    def __init__(self):
        super().__init__("cad", "CAD generation via Zoo/Tripo/local")
        self._cad_cycler = CADCycler()

        # Register generate_cad_model tool
        self.register_tool(ToolDefinition(
            name="generate_cad_model",
            description="Generate 3D CAD model from text",
            parameters={
                "type": "object",
                "properties": {
                    "prompt": {"type": "string"},
                    "provider": {"type": "string", "enum": ["zoo", "tripo", "local"]},
                },
                "required": ["prompt"]
            }
        ))

    async def execute_tool(self, tool_name, arguments):
        if tool_name == "generate_cad_model":
            result = await self._cad_cycler.generate(
                prompt=arguments["prompt"],
                provider=arguments.get("provider", "zoo")
            )
            return ToolResult(success=True, data=result)
        return ToolResult(success=False, error="Unknown tool")
```

---

#### Task 6: Implement Home Assistant MCP Server

**File**: `services/mcp/src/mcp/servers/ha_server.py`

**Tools**:
```python
control_light:
  description: "Turn lights on or off"
  parameters:
    entity_id: str (required, e.g., "light.welding_bay")
    action: enum ["on", "off"] (required)
    brightness: int 0-255 (optional)

control_lock:
  description: "Lock or unlock doors"
  parameters:
    entity_id: str (required)
    action: enum ["lock", "unlock"] (required)
    confirmation_phrase: str (required for unlock)

activate_scene:
  description: "Trigger Home Assistant scene"
  parameters:
    scene_name: str (required)
```

**Resources**:
```python
ha://entities/lights - List all light entities
ha://entities/locks - List all lock entities
ha://state/{entity_id} - Get current state
```

**Implementation**:
```python
from ..server import MCPServer, ToolDefinition, ToolResult
from brain.skills.home_assistant import HomeAssistantClient

class HomeAssistantMCPServer(MCPServer):
    def __init__(self):
        super().__init__("home-assistant", "Control HA devices")
        self._ha_client = HomeAssistantClient()

        self.register_tool(ToolDefinition(
            name="control_light",
            description="Turn lights on or off",
            parameters={
                "type": "object",
                "properties": {
                    "entity_id": {"type": "string"},
                    "action": {"type": "string", "enum": ["on", "off"]},
                    "brightness": {"type": "integer", "minimum": 0, "maximum": 255}
                },
                "required": ["entity_id", "action"]
            }
        ))

    async def execute_tool(self, tool_name, arguments):
        if tool_name == "control_light":
            await self._ha_client.call_service(
                domain="light",
                service="turn_" + arguments["action"],
                entity_id=arguments["entity_id"],
                brightness=arguments.get("brightness")
            )
            return ToolResult(success=True, data={"status": "executed"})
```

---

#### Task 7: Upgrade Memory MCP Server

**File**: `services/mem0-mcp/src/mem0_mcp/mcp_adapter.py` (new file alongside existing `app.py`)

**Tools**:
```python
create_project_note:
  description: "Store project memory"
  parameters:
    conversation_id: str (required)
    summary: str (required)
    artifacts: list (optional)
    metadata: object (optional)

search_memories:
  description: "Semantic search over memories"
  parameters:
    query: str (required)
    user_id: str (optional)
    limit: int (optional, default: 3)
    score_threshold: float (optional, default: 0.75)
```

**Resources**:
```python
memory://project/{conversation_id} - Get project details
memory://recent - Recent memories
```

**Implementation**:
```python
from mcp.server import MCPServer, ToolDefinition, ToolResult
from .app import MemoryClient  # Import existing memory service

class MemoryMCPServer(MCPServer):
    def __init__(self):
        super().__init__("memory", "Project memory and notes")
        self._memory = MemoryClient()

        self.register_tool(ToolDefinition(
            name="create_project_note",
            description="Store project memory",
            parameters={
                "type": "object",
                "properties": {
                    "conversation_id": {"type": "string"},
                    "summary": {"type": "string"},
                    "artifacts": {"type": "array"},
                },
                "required": ["conversation_id", "summary"]
            }
        ))

    async def execute_tool(self, tool_name, arguments):
        if tool_name == "create_project_note":
            result = await self._memory.add_memory(
                content=arguments["summary"],
                metadata={"conversation_id": arguments["conversation_id"]}
            )
            return ToolResult(success=True, data=result)
```

---

#### Task 8: Create MCP Client for Brain Service

**File**: `services/brain/src/brain/tools/mcp_client.py`

**Purpose**: Connect Brain service to MCP servers and fetch available tools

**Implementation**:
```python
from typing import Dict, List
from mcp.server import ToolDefinition, ToolResult

class MCPClient:
    """Client for connecting to MCP tool servers."""

    def __init__(self):
        self._servers: Dict[str, Any] = {}

    def register_server(self, name: str, server: MCPServer):
        """Register an MCP server."""
        self._servers[name] = server

    def get_all_tools(self) -> List[ToolDefinition]:
        """Get all tools from all registered servers."""
        tools = []
        for server in self._servers.values():
            tools.extend(server.list_tools())
        return tools

    async def execute_tool(
        self, tool_name: str, arguments: Dict[str, Any]
    ) -> ToolResult:
        """Execute a tool by routing to the appropriate server."""
        # Find which server has this tool
        for server in self._servers.values():
            tool_defs = {t.name: t for t in server.list_tools()}
            if tool_name in tool_defs:
                return await server.execute_tool(tool_name, arguments)

        return ToolResult(success=False, error=f"Tool '{tool_name}' not found")
```

**Integration**:
```python
# In services/brain/src/brain/app.py or orchestrator.py

from mcp.servers.cad_server import CADMCPServer
from mcp.servers.ha_server import HomeAssistantMCPServer
from mem0_mcp.mcp_adapter import MemoryMCPServer
from brain.tools.mcp_client import MCPClient

# Initialize MCP client with all servers
mcp_client = MCPClient()
mcp_client.register_server("cad", CADMCPServer())
mcp_client.register_server("ha", HomeAssistantMCPServer())
mcp_client.register_server("memory", MemoryMCPServer())
```

---

### Phase 3: ReAct Agent (Tasks 9-11, ~6-8 hours)

#### Task 9: Implement ReAct Agent Controller

**File**: `services/brain/src/brain/agents/react.py`

**Core Loop**:
```python
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

@dataclass
class ReActStep:
    """Single step in ReAct reasoning chain."""
    thought: str  # LLM's reasoning
    action: Optional[Dict[str, Any]]  # Tool call
    observation: Optional[str]  # Tool result

@dataclass
class ReActResult:
    """Final result from ReAct loop."""
    answer: str
    steps: List[ReActStep]
    iterations: int
    success: bool


class ReActAgent:
    """ReAct pattern agent: Reasoning + Acting in iterative loop."""

    def __init__(
        self,
        llm_client: LlamaCppClient,
        mcp_client: MCPClient,
        max_iterations: int = 5,
        timeout_seconds: int = 60
    ):
        self._llm = llm_client
        self._mcp = mcp_client
        self._max_iterations = max_iterations
        self._timeout = timeout_seconds

    async def run(
        self,
        prompt: str,
        tools: Optional[List[ToolDefinition]] = None
    ) -> ReActResult:
        """Execute ReAct loop until final answer or max iterations."""

        steps: List[ReActStep] = []
        context_messages = []

        # Get tools from MCP if not provided
        if tools is None:
            tool_defs = self._mcp.get_all_tools()
            tools = [t.to_json_schema() for t in tool_defs]

        for i in range(self._max_iterations):
            # Build prompt with conversation history
            full_prompt = self._build_prompt(prompt, steps)

            # Get LLM response with tools
            response = await self._llm.generate(
                prompt=full_prompt,
                tools=tools
            )

            # Extract thought and tool calls
            thought = response["response"]
            tool_calls = response.get("tool_calls", [])

            # If no tool calls, this is the final answer
            if not tool_calls:
                return ReActResult(
                    answer=thought,
                    steps=steps,
                    iterations=i + 1,
                    success=True
                )

            # Execute tool calls and collect observations
            for tool_call in tool_calls:
                result = await self._mcp.execute_tool(
                    tool_name=tool_call.name,
                    arguments=tool_call.arguments
                )

                observation = str(result.data) if result.success else f"Error: {result.error}"

                steps.append(ReActStep(
                    thought=thought,
                    action=tool_call.to_dict(),
                    observation=observation
                ))

        # Max iterations reached
        return ReActResult(
            answer="Max iterations reached without final answer",
            steps=steps,
            iterations=self._max_iterations,
            success=False
        )

    def _build_prompt(self, original_prompt: str, steps: List[ReActStep]) -> str:
        """Build prompt with ReAct history."""
        parts = [original_prompt]

        for i, step in enumerate(steps):
            parts.append(f"\nThought {i+1}: {step.thought}")
            if step.action:
                parts.append(f"Action {i+1}: {step.action}")
            if step.observation:
                parts.append(f"Observation {i+1}: {step.observation}")

        return "\n".join(parts)
```

---

#### Task 10: Update BrainRouter for Agentic Routing

**File**: `services/brain/src/brain/routing/router.py`

**Changes**:
```python
# Add to BrainRouter.__init__
from ..agents.react import ReActAgent
from ..tools.mcp_client import MCPClient

def __init__(self, ..., mcp_client: Optional[MCPClient] = None):
    # ... existing code ...
    self._mcp_client = mcp_client
    if self._mcp_client:
        self._react_agent = ReActAgent(
            llm_client=self._llama,
            mcp_client=self._mcp_client
        )

# Add new method
async def route_agentic(self, request: RoutingRequest) -> RoutingResult:
    """Route request through ReAct agent with tool use."""

    # Get available tools
    tools = [t.to_json_schema() for t in self._mcp_client.get_all_tools()]

    # Run ReAct loop
    result = await self._react_agent.run(request.prompt, tools)

    # Return as RoutingResult
    return RoutingResult(
        output=result.answer,
        tier=RoutingTier.local,  # or based on tool usage
        confidence=0.9 if result.success else 0.5,
        latency_ms=0,  # TODO: track actual latency
        metadata={
            "agent": "react",
            "iterations": result.iterations,
            "steps": [s.__dict__ for s in result.steps]
        }
    )

# Modify route() to check if tools should be used
async def route(self, request: RoutingRequest) -> RoutingResult:
    # If tools enabled and MCP client available, use agentic routing
    if request.use_tools and self._mcp_client:
        return await self.route_agentic(request)

    # Otherwise use existing simple routing
    return await self._invoke_local(request)
```

**Add to RoutingRequest**:
```python
class RoutingRequest(BaseModel):
    # ... existing fields ...
    use_tools: bool = False  # Enable tool-aware agentic routing
```

---

#### Task 11: Create Tool Executor with Safety Checks

**File**: `services/brain/src/brain/tools/executor.py`

**Purpose**: Add safety layer before tool execution

**Implementation**:
```python
from typing import Dict, Any
from mcp.server import ToolResult
from brain.routing.permission import PermissionManager
from safety.workflows.hazard import HazardWorkflow

class SafeToolExecutor:
    """Execute tools with safety checks and permission gating."""

    def __init__(
        self,
        mcp_client: MCPClient,
        permission_manager: PermissionManager,
        hazard_workflow: HazardWorkflow
    ):
        self._mcp = mcp_client
        self._permission = permission_manager
        self._hazard = hazard_workflow

        # Classify tools by safety level
        self._hazardous_tools = {"control_lock"}  # Requires hazard workflow
        self._cloud_tools = {"generate_cad_model"}  # May cost money

    async def execute(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        user_id: str,
        conversation_id: str
    ) -> ToolResult:
        """Execute tool with appropriate safety checks."""

        # Hazardous tools require signature verification
        if tool_name in self._hazardous_tools:
            if tool_name == "control_lock" and arguments.get("action") == "unlock":
                # Require hazard confirmation
                allowed, response = await self._hazard.process_device_intent(
                    intent="lock.unlock",
                    device_id=arguments.get("entity_id"),
                    zone_id=None,
                    user_id=user_id,
                    signature=arguments.get("confirmation_phrase")
                )
                if not allowed:
                    return ToolResult(
                        success=False,
                        error=f"Hazard workflow denied: {response}"
                    )

        # Cloud tools may require budget approval
        if tool_name in self._cloud_tools:
            # Estimate cost (simplified - real impl would be more complex)
            estimated_cost = 0.05  # Example: Zoo API call

            approved = await self._permission.request_permission(
                tier=RoutingTier.mcp,
                provider="zoo",
                estimated_cost=estimated_cost,
                reason="CAD generation requested",
                conversation_id=conversation_id
            )

            if not approved:
                return ToolResult(
                    success=False,
                    error="Permission denied: budget limit or user declined"
                )

        # Execute tool via MCP client
        return await self._mcp.execute_tool(tool_name, arguments)
```

---

### Phase 4: System Prompts (Tasks 12-13, ~3-4 hours)

#### Task 12: Update Expert System Prompts with ReAct Instructions

**File**: `services/brain/src/brain/prompts/expert_system.py`

**Add ReAct Section**:
```python
REACT_INSTRUCTIONS = """
You have access to tools that can help you answer questions and perform tasks.

When responding, use this ReAct (Reasoning + Acting) pattern:

1. **Thought**: Reason about what you need to do next
2. **Action**: If you need information or to perform an action, call a tool using:
   <tool_call>{"name": "tool_name", "arguments": {...}}</tool_call>
3. **Observation**: After calling a tool, you'll receive results
4. **Repeat**: Continue thinking and acting until you have enough information
5. **Answer**: When ready, provide your final answer without any tool calls

Example:
Thought: I need to generate a CAD model for the mounting bracket.
Action: <tool_call>{"name": "generate_cad_model", "arguments": {"prompt": "L-shaped mounting bracket with 4 holes", "provider": "zoo"}}</tool_call>

[After receiving observation with artifact URL]

Thought: The CAD model has been generated successfully. Now I should inform the user.
Answer: I've created an L-shaped mounting bracket CAD model. The artifact is available at [URL].
"""

def get_expert_system_prompt(
    user_query: str,
    tools: Optional[List[Dict]] = None,
    ...
) -> str:
    # ... existing verbosity, context code ...

    # Add tool instructions if tools provided
    tool_section = ""
    if tools:
        tool_section = f"\n\n{REACT_INSTRUCTIONS}\n\nAVAILABLE TOOLS:\n"
        for tool in tools:
            func = tool.get("function", {})
            tool_section += f"- {func.get('name')}: {func.get('description')}\n"

    prompt = f"""
{IDENTITY}
{verbosity_instructions}
{tool_section}
{context_section}

USER QUERY: {user_query}
"""
    return prompt
```

---

#### Task 13: Create Dynamic Tool Formatter

**File**: `services/brain/src/brain/prompts/tool_formatter.py`

**Purpose**: Format tools for injection into prompts

**Implementation**:
```python
from typing import List, Dict, Any

def format_tools_for_prompt(tools: List[Dict[str, Any]]) -> str:
    """Format tool definitions for inclusion in system prompt."""

    formatted = []
    for tool in tools:
        func = tool.get("function", {})
        name = func.get("name", "unknown")
        desc = func.get("description", "")
        params = func.get("parameters", {}).get("properties", {})
        required = func.get("parameters", {}).get("required", [])

        # Format parameters
        param_lines = []
        for param_name, param_def in params.items():
            param_type = param_def.get("type", "any")
            param_desc = param_def.get("description", "")
            req_marker = " (required)" if param_name in required else " (optional)"
            param_lines.append(f"  - {param_name}: {param_type}{req_marker} - {param_desc}")

        tool_text = f"""
**{name}**
{desc}

Parameters:
{chr(10).join(param_lines)}
"""
        formatted.append(tool_text)

    return "\n".join(formatted)
```

---

### Phase 5: Integration (Tasks 14-16, ~2-3 hours)

#### Task 14: Update Docker Compose

**File**: `infra/compose/docker-compose.yml`

**Add MCP Tools Service**:
```yaml
services:
  # ... existing services ...

  mcp-tools:
    build:
      context: ../../
      dockerfile: services/mcp/Dockerfile
    environment:
      - CAD_SERVICE_URL=http://cad:8200
      - HA_BASE_URL=${HOME_ASSISTANT_BASE_URL}
      - HA_TOKEN=${HOME_ASSISTANT_TOKEN}
      - MEMORY_SERVICE_URL=http://mem0-mcp:8001
    depends_on:
      - cad
      - mem0-mcp
    networks:
      - kitty-net
```

**Create Dockerfile**:
```dockerfile
# services/mcp/Dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY services/mcp/pyproject.toml .
RUN pip install -e .
COPY services/mcp/src/ ./src/
CMD ["python", "-m", "mcp.app"]
```

---

#### Task 15: Add Environment Variables

**File**: `.env.example`

**Add**:
```bash
# Tool-aware agent settings
KITTY_TOOLS_ENABLED=true
KITTY_REACT_MAX_ITERATIONS=5
KITTY_REACT_TIMEOUT_SECONDS=60

# MCP server configuration
MCP_CAD_ENABLED=true
MCP_HA_ENABLED=true
MCP_MEMORY_ENABLED=true
```

---

#### Task 16: Update Orchestrator

**File**: `services/brain/src/brain/orchestrator.py`

**Changes**:
```python
from .tools.mcp_client import MCPClient
from mcp.servers.cad_server import CADMCPServer
from mcp.servers.ha_server import HomeAssistantMCPServer
from mem0_mcp.mcp_adapter import MemoryMCPServer

class BrainOrchestrator:
    def __init__(self):
        # ... existing code ...

        # Initialize MCP client if tools enabled
        if settings.kitty_tools_enabled:
            self._mcp_client = MCPClient()
            if settings.mcp_cad_enabled:
                self._mcp_client.register_server("cad", CADMCPServer())
            if settings.mcp_ha_enabled:
                self._mcp_client.register_server("ha", HomeAssistantMCPServer())
            if settings.mcp_memory_enabled:
                self._mcp_client.register_server("memory", MemoryMCPServer())

            # Pass MCP client to router
            self._router = BrainRouter(mcp_client=self._mcp_client)
        else:
            self._mcp_client = None
            self._router = BrainRouter()

    async def process_query(self, query: str, use_tools: bool = False, **kwargs):
        # ... build RoutingRequest ...
        request = RoutingRequest(
            prompt=query,
            use_tools=use_tools,
            ...
        )

        result = await self._router.route(request)
        return result
```

---

### Phase 6: Testing & Docs (Tasks 17-19, ~4-5 hours)

#### Task 17: Create Integration Tests

**File**: `tests/integration/test_tool_calling.py`

```python
import pytest
from brain.routing.llama_cpp_client import LlamaCppClient

@pytest.mark.asyncio
async def test_llama_cpp_function_calling():
    """Test basic function calling with llama.cpp."""
    client = LlamaCppClient()

    tools = [{
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get weather for a location",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string"}
                },
                "required": ["location"]
            }
        }
    }]

    response = await client.generate(
        prompt="What's the weather in San Francisco?",
        tools=tools
    )

    assert "tool_calls" in response
    assert len(response["tool_calls"]) > 0
    assert response["tool_calls"][0].name == "get_weather"
```

---

#### Task 18: Create End-to-End ReAct Test

**File**: `tests/integration/test_react_agent.py`

```python
@pytest.mark.asyncio
async def test_react_multi_step():
    """Test ReAct agent with multiple tool calls."""

    # Setup: mock MCP servers
    mcp_client = MCPClient()
    cad_server = CADMCPServer()
    ha_server = HomeAssistantMCPServer()
    mcp_client.register_server("cad", cad_server)
    mcp_client.register_server("ha", ha_server)

    # Agent
    agent = ReActAgent(
        llm_client=LlamaCppClient(),
        mcp_client=mcp_client
    )

    # Test multi-step task
    result = await agent.run(
        "Generate a mounting bracket and turn on the welding bay lights"
    )

    assert result.success
    assert result.iterations >= 2
    assert any("generate_cad_model" in str(step.action) for step in result.steps)
    assert any("control_light" in str(step.action) for step in result.steps)
```

---

#### Task 19: Write Documentation

**File**: `docs/tools-and-agents.md`

**Sections**:
1. Architecture Overview
2. How to Add New Tools
3. ReAct Pattern Explanation
4. Troubleshooting Guide
5. Example Workflows

---

## Quick Start Guide for Remaining Implementation

### To Continue Implementation:

1. **Phase 2 (MCP Servers)**: Start with `cad_server.py` since CAD generation is core to KITTY
2. **Phase 3 (ReAct Agent)**: Implement agent, then router integration, then safety executor
3. **Phase 4-6 (Integration)**: Update prompts, configs, tests, docs

### Key Files to Create:

**Highest Priority**:
- `services/mcp/src/mcp/servers/cad_server.py`
- `services/mcp/src/mcp/servers/ha_server.py`
- `services/mem0-mcp/src/mem0_mcp/mcp_adapter.py`
- `services/brain/src/brain/tools/mcp_client.py`
- `services/brain/src/brain/agents/react.py`

**Medium Priority**:
- `services/brain/src/brain/tools/executor.py`
- Update `services/brain/src/brain/routing/router.py`
- Update `services/brain/src/brain/prompts/expert_system.py`

**Lower Priority**:
- Tests, docs, Docker configs

### Testing Strategy:

1. **Unit test each MCP server** independently
2. **Test MCP client** can discover and call tools
3. **Test ReAct agent** with mocked tool results
4. **Integration test** full end-to-end workflow
5. **Manual test** with real llama.cpp server

---

## Dependencies to Add

**Python Packages** (add to `pyproject.toml`):
- No new external dependencies needed (all using existing code)

**Environment Variables**:
```bash
# Already have:
LLAMACPP_TOOL_CALLING=1  # Added ✅

# Need to add:
KITTY_TOOLS_ENABLED=true
KITTY_REACT_MAX_ITERATIONS=5
MCP_CAD_ENABLED=true
MCP_HA_ENABLED=true
MCP_MEMORY_ENABLED=true
```

---

## Success Criteria

- [ ] KITTY can reason about which tool to use
- [ ] KITTY can execute CAD generation via tools
- [ ] KITTY can control HA devices via tools
- [ ] KITTY can store/retrieve project notes via tools
- [ ] ReAct loop completes multi-step tasks
- [ ] Tool calls logged and auditable
- [ ] Safety checks enforced (hazard workflow, budget)
- [ ] MCP servers reusable by other clients

---

## Estimated Timeline

| Phase | Tasks | Hours | Priority |
|-------|-------|-------|----------|
| 2.2-2.4 | MCP Servers (3 servers) | 6-8 | HIGH |
| 2.5 | MCP Client | 2 | HIGH |
| 3.1 | ReAct Agent | 4-5 | HIGH |
| 3.2 | Router Integration | 2 | HIGH |
| 3.3 | Safety Executor | 2-3 | MEDIUM |
| 4 | Prompts | 3-4 | MEDIUM |
| 5 | Integration | 2-3 | MEDIUM |
| 6 | Testing & Docs | 4-5 | LOW |

**Total Remaining**: ~25-30 hours

---

## Current Git Status

**Branch**: `001-KITTY`

**Commits**:
1. `3bdcf33` - llama.cpp function calling flags
2. `1843ec0` - Tool calling support in LlamaCppClient
3. `2ccc379` - MCP server framework

**Next Commit**: MCP servers implementation (Tasks 5-7)
