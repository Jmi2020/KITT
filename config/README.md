# KITTY ReAct Agent Configuration

This directory contains configuration files for the KITTY Conversation Framework with ReAct agent and MCP tool orchestration.

## Overview

The **tool_registry.yaml** defines all available tools that the ReAct agent can use to fulfill user requests. Each tool maps to a Model Context Protocol (MCP) endpoint with JSON schema validation and safety metadata.

## Architecture

```
User Intent
    ↓
ReAct Agent (Q4 llama.cpp on :8083)
    ↓
Tool Registry (tool_registry.yaml)
    ↓
MCP Client (HTTP wrapper)
    ↓
Gateway Proxy (:8080)
    ↓
Microservices (CAD, Images, Fabrication, etc.)
```

## Tool Categories

### 1. **CAD Generation** (`cad.*`)
- `cad.generate_model` - Generate 3D models via Zoo/Tripo/local
  - Supports image-to-CAD via `imageRefs` parameter
  - Auto-fallback: Zoo API → Tripo API → CadQuery/FreeCAD

### 2. **Image Generation** (`images.*`)
- `images.generate` - Stable Diffusion text-to-image
- `images.get_latest` - List recent generations
- `images.select` - Select image for imageRef compatibility

### 3. **Fabrication** (`fabrication.*`)
- `fabrication.queue_print` - Queue print jobs to OctoPrint/Klipper
  - **Safety:** Requires confirmation phrase

### 4. **Home Assistant** (`homeassistant.*`)
- `homeassistant.control_device` - Control lights, switches, doors
  - **Safety:** Hazardous devices require confirmation

### 5. **Vision & Research** (`vision.*`, `research.*`)
- `vision.search` - Search for visual references
- `vision.store` - Store reference images
- `research.web_search` - Web search via Perplexity
- `research.fetch_webpage` - Extract webpage content

### 6. **Memory** (`memory.*`)
- `memory.remember` - Store facts/preferences in Qdrant
- `memory.search` - Semantic search over conversation history

## Safety Levels

| Hazard Class | Confirmation Required | Examples |
|--------------|----------------------|----------|
| `none` | No | Research, memory, vision search |
| `low` | No | CAD generation, image generation |
| `medium` | Yes | Print queue, material handling |
| `high` | Yes + dual auth | Door unlock, power relays |
| `varies` | Conditional | Device control (depends on entity) |

## Usage in Brain Service

```python
from brain.conversation.tools import ToolRegistry

# Load registry
registry = ToolRegistry("config/tool_registry.yaml")

# Get tool inventory for agent prompt
tool_inventory = registry.inv_str()

# Validate agent action
action = {"tool": "images.generate", "args": {"prompt": "cyberpunk workshop"}}
registry.validate_args(action["tool"], action["args"])

# Execute via MCP client
mcp_client = MCPClient(registry, httpx.AsyncClient())
result = await mcp_client.execute(action["tool"], action["args"])
```

## Example Flows

### Image → CAD → Print Pipeline

```yaml
User: "Generate an image of a water bottle, then create a 3D model and print it"

Agent Turn 1:
  type: action
  tool: images.generate
  args:
    prompt: "studio photo matte black water bottle, product photography"
    model: sdxl_base
    width: 1024
    height: 1024

Observation: {"png_key": "s3://kitty-artifacts/images/20250111_143022.png"}

Agent Turn 2:
  type: action
  tool: images.select
  args:
    image_key: "images/20250111_143022.png"

Observation: {"imageRef": "s3://kitty-artifacts/images/20250111_143022.png"}

Agent Turn 3:
  type: action
  tool: cad.generate_model
  args:
    prompt: "water bottle from reference image"
    provider: tripo
    imageRefs: ["s3://kitty-artifacts/images/20250111_143022.png"]

Observation: {"stl_path": "/Users/Shared/KITTY/artifacts/cad/bottle.stl"}

Safety Check: fabrication.queue_print requires confirmation

Agent Turn 4:
  type: ask_user
  message: "Ready to print. Say 'alpha-omega-protocol' to proceed."

User: "alpha-omega-protocol"

Agent Turn 5:
  type: action
  tool: fabrication.queue_print
  args:
    artifact_path: "/Users/Shared/KITTY/artifacts/cad/bottle.stl"
    printer_id: "prusa-mk4"

Agent Final:
  type: final
  message: "Water bottle print queued to prusa-mk4, ETA 2h 15m"
```

### Memory-Enhanced Conversation

```yaml
User: "I prefer 0.4mm nozzles for detailed prints"

Agent:
  type: action
  tool: memory.remember
  args:
    text: "User prefers 0.4mm nozzles for detailed prints"
    tags: ["preference", "printing", "nozzle"]

---

User (later): "Queue my bracket print"

Agent Turn 1:
  type: action
  tool: memory.search
  args:
    query: "printing preferences"
    top_k: 3

Observation: [{"text": "User prefers 0.4mm nozzles for detailed prints", ...}]

Agent Turn 2:
  type: action
  tool: fabrication.queue_print
  args:
    printer_id: "prusa-mk4"
    profile: "detailed-0.4mm"  # ← Inferred from memory!
```

## Adding New Tools

1. **Add to tool_registry.yaml:**
   ```yaml
   myservice.my_action:
     method: POST
     url: http://gateway:8080/api/myservice/action
     schema:
       type: object
       properties:
         param1: {type: string}
       required: [param1]
     safety:
       hazard_class: "low"
       confirmation_required: false
   ```

2. **Add Gateway proxy route:**
   ```python
   # services/gateway/src/gateway/routes/myservice.py
   @router.post("/api/myservice/action")
   async def my_action(request: Request):
       data = await request.json()
       # Proxy to actual service
       return await myservice_client.action(data)
   ```

3. **Register in Gateway app:**
   ```python
   # services/gateway/src/gateway/app.py
   from .routes.myservice import router as myservice_router
   app.include_router(myservice_router)
   ```

4. **Reload tool registry:** The agent automatically picks up new tools on restart.

## Environment Variables

```bash
# Safety & Budget
HAZARD_CONFIRMATION_PHRASE=alpha-omega-protocol
API_OVERRIDE_PASSWORD=omega
BUDGET_PER_TASK_USD=0.50

# LLM Endpoints
LLAMACPP_Q4_URL=http://localhost:8083/v1/chat/completions
LLAMACPP_F16_URL=http://localhost:8082/v1/chat/completions

# Gateway
GATEWAY_BASE=http://gateway:8080
```

## Related Documentation

- **Implementation Guide:** `Research/KITTY_Conversation_Framework_Implementation.md`
- **Operations Manual:** `KITTY_OperationsManual.md`
- **API Reference:** `Research/APIinfo.md`
- **Vision Pipeline:** See `services/gateway/routes/vision.py`
- **Image Generation:** See `services/gateway/routes/images.py`

## Testing Tools

```bash
# Test tool registry parsing
python -c "
from services.brain.src.brain.conversation.tools import ToolRegistry
registry = ToolRegistry('config/tool_registry.yaml')
print(registry.inv_str())
"

# Test tool via Gateway
curl -X POST http://localhost:8080/api/images/generate \
  -H 'Content-Type: application/json' \
  -d '{"prompt": "cyberpunk workshop", "model": "sdxl_base"}'

# Test CAD with imageRefs
curl -X POST http://localhost:8080/api/cad/generate \
  -H 'Content-Type: application/json' \
  -d '{
    "prompt": "water bottle",
    "provider": "tripo",
    "imageRefs": ["s3://kitty-artifacts/images/example.png"]
  }'
```

## Security Notes

- **Confirmation Phrases:** Stored in `.env`, never in code
- **API Override:** Required for cloud frontier tier calls (GPT-4, Claude)
- **Audit Logging:** All tool calls logged to PostgreSQL `telemetry_events` table
- **Safety Events:** Hazardous actions logged to `safety_events` with camera bookmarks
- **Token Budget:** Enforced per-task to prevent runaway cloud costs

## Data Collection for Training

Every tool call is logged with:
- **Input:** User intent, parsed action, tool arguments
- **Output:** Service response, success/failure status
- **Metadata:** Timestamp, conversation ID, user ID, tier (local/mcp/frontier)
- **Performance:** Latency, token count, cost

This structured data enables:
- Fine-tuning local models on successful flows
- RLHF from safety confirmations
- Intent classification improvement
- Tool argument prediction
- Multi-turn dialogue optimization

Export training data:
```sql
SELECT
  conversation_id,
  JSON_AGG(payload ORDER BY timestamp) as agent_trace
FROM telemetry_events
WHERE event_type IN ('agent_action', 'tool_call')
GROUP BY conversation_id;
```
