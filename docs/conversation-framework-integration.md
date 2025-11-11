# KITTY Conversation Framework Integration

**Status**: ✅ Completed
**Date**: 2025-01-10
**Branch**: `claude/kitty-001-access-011CUybyHrDBaPsk6JaCEBRL`

## Overview

This document summarizes the integration of the KITTY Conversation Framework with ReAct agent workflows, safety management, and multi-turn conversation state. The integration adds comprehensive tool safety checks, user confirmation flows for high-hazard operations, and conversation state persistence.

## Implementation Summary

### Phase 1: Environment Configuration Cleanup ✅

**File**: `.env.example` (reorganized from 310 → 378 lines)

**Changes**:
- Reorganized from 14 scattered sections to 12 logical groups
- Added dedicated **Dual-Model Architecture** section (Q4 Tool Orchestrator + F16 Reasoning Engine)
- Added new **Agent & Tool Configuration** section with:
  - `TOOL_REGISTRY_PATH=config/tool_registry.yaml`
  - `AGENT_HISTORY_STEPS=4`
  - `AGENT_HISTORY_TOKEN_BUDGET=8000`
  - `AGENT_OBSERVATION_CHARS=2000`
  - `REACT_MAX_ITERATIONS=10`
- Enhanced inline documentation for all sections
- Created backup: `.env.example.backup`

**Commit**: `276cb2b` - "feat: Reorganize .env and create tool registry for ReAct framework"

---

### Phase 2: Tool Registry & Safety Infrastructure ✅

#### Phase 2.4: Tool Registry Creation

**File**: `config/tool_registry.yaml` (new, 292 lines)

**Content**:
- **22 tools** registered across 8 MCP servers
- **Hazard classifications**: none, low, medium, high
- **Budget tiers**: free, paid, premium
- **Tool categories**: research, vision, memory, cad, fabrication, homeassistant, broker, reasoning
- **Safety policies**: Global enforcement rules for confirmations and overrides

**Key Tools**:
- `web_search`, `fetch_webpage`, `research_deep` (research)
- `image_search`, `image_filter`, `store_selection` (vision)
- `remember`, `search_memories` (memory)
- `cad.generate_model`, `cad.image_to_mesh`, `cad.local_generate` (CAD)
- `fabrication.queue_print` (medium hazard, requires confirmation)
- `homeassistant.unlock_door` (high hazard, requires confirmation + signature)
- `homeassistant.enable_power` (high hazard, requires confirmation + signature)
- `reason_with_f16` (new, for F16 reasoning delegation)

#### Phase 2.3: Conversation Module

**Files**:
- `services/brain/src/brain/conversation/__init__.py`
- `services/brain/src/brain/conversation/state.py` (177 lines)
- `services/brain/src/brain/conversation/safety.py` (253 lines)

**Key Classes**:

##### `ConversationState`
- Tracks conversation history (List[AgentStep])
- Manages pending confirmations with 5-minute expiration
- Metadata storage for custom fields
- Methods: `add_step()`, `set_pending_confirmation()`, `clear_pending_confirmation()`, `is_confirmation_expired()`

##### `ConversationStateManager`
- In-memory state management (production should use Redis/PostgreSQL)
- Methods: `get_or_create()`, `get()`, `delete()`, `cleanup_expired()`, `count()`

##### `SafetyChecker`
- Loads `config/tool_registry.yaml` on initialization
- Methods:
  - `check_tool_execution()`: Validate tool against registry policies
  - `verify_confirmation()`: Check if user message contains required phrase
  - `get_confirmation_message()`: Generate user-facing confirmation prompt

##### `ToolSafetyMetadata` & `SafetyResult`
- Dataclasses for tool metadata and safety check results
- Fields: `hazard_class`, `requires_confirmation`, `confirmation_phrase`, `requires_signature`, `requires_override`, `budget_tier`

**Commit**: `8fe09b4` - "feat: Add conversation framework with safety and state management"

---

### Phase 2.2: Safety-Integrated ReAct Agent ✅

**File**: `services/brain/src/brain/agents/react_agent.py` (657 lines, +113 lines)

**Changes**:

#### Enhanced `AgentResult` Dataclass
Added confirmation fields:
- `requires_confirmation: bool = False`
- `confirmation_phrase: Optional[str] = None`
- `pending_tool: Optional[str] = None`
- `pending_tool_args: Optional[Dict[str, Any]] = None`
- `hazard_class: Optional[str] = None`

#### Enhanced `ReActAgent`
- Initialize `SafetyChecker` in `__init__`
- Added safety checks before tool execution in both:
  - `run()` method (ReAct loop)
  - `run_single_action()` method (direct tool execution)

#### Safety Flow
1. Validate tool call parameters (existing ToolCallValidator)
2. **NEW**: Check safety against `tool_registry.yaml`
3. If `requires_confirmation`: Pause and return AgentResult with confirmation request
4. If `requires_override`: Block with error message (paid/premium tools need API_OVERRIDE_PASSWORD)
5. If disabled: Block with error message
6. If approved: Execute tool normally

**Commit**: `a61c041` - "feat: Integrate safety checks into ReAct agent before tool execution"

---

### Phase 4: Orchestration & API Integration ✅

#### Phase 4.1: Enhanced Orchestrator

**File**: `services/brain/src/brain/orchestrator.py` (300 lines, +123 lines)

**Changes**:

##### Initialization
- Added `ConversationStateManager` for multi-turn workflow tracking
- Added `SafetyChecker` for confirmation phrase verification

##### Enhanced `generate_response()`
- Check for pending confirmations before response generation
- Verify confirmation phrases when user responds
- Support cancellation keywords: `cancel`, `abort`, `no`, `stop`
- Handle confirmation expiration (5-minute timeout)
- Return early with confirmation prompt or cancellation message

##### New Methods
- `set_pending_confirmation()`: Store pending tool confirmations in conversation state
- `get_conversation_state()`: Access conversation state
- `clear_pending_confirmation()`: Remove pending confirmations

**Commit**: `5e551d3` - "feat: Enhance orchestrator with conversation state and confirmation flow"

#### Phase 4.2: Query Route & Router Integration

**Files**:
- `services/brain/src/brain/routes/query.py` (144 lines, +34 lines)
- `services/brain/src/brain/routing/router.py` (+13 lines in `_invoke_agent()`)
- `services/brain/src/brain/agents/react_agent.py` (fixed `allow_paid` usage)

**Changes**:

##### Enhanced `QueryResponse`
Added confirmation fields:
- `requires_confirmation: bool = Field(False, alias="requiresConfirmation")`
- `confirmation_phrase: Optional[str] = Field(None, alias="confirmationPhrase")`
- `pending_tool: Optional[str] = Field(None, alias="pendingTool")`
- `hazard_class: Optional[str] = Field(None, alias="hazardClass")`

##### Enhanced Query Route Handler
- Extract confirmation metadata from `RoutingResult.metadata`
- Call `orchestrator.set_pending_confirmation()` when confirmation required
- Pass confirmation fields to response

##### Enhanced Router `_invoke_agent()`
- Extract confirmation fields from `AgentResult`
- Pass them through `RoutingResult.metadata`
- Log warning when confirmation is required

##### Fixed ReActAgent
- Removed `override_provided` from `__init__` (should be per-request, not per-instance)
- Use `allow_paid` parameter (passed per-request) in safety checks
- Added `allow_paid` parameter to `run_single_action()`

**Commit**: `4f38d1f` - "feat: Wire up confirmation flow through routing and query layers"

---

## End-to-End Confirmation Flow

### Example: Queue Print Job (Medium Hazard)

1. **User Request**:
   ```json
   POST /api/query
   {
     "conversationId": "conv-123",
     "userId": "user-001",
     "intent": "conversational",
     "prompt": "Queue the bracket.stl to printer_01",
     "useAgent": true
   }
   ```

2. **Agent Execution**:
   - Agent identifies tool: `fabrication.queue_print`
   - Safety check: `requires_confirmation=true` (medium hazard)
   - Returns `AgentResult` with confirmation request

3. **Router Processing**:
   - Extracts confirmation info from `AgentResult`
   - Passes through `RoutingResult.metadata`

4. **Query Route Response**:
   ```json
   {
     "conversationId": "conv-123",
     "intent": "conversational",
     "result": {
       "output": "⚠️  Confirmation required for 'fabrication.queue_print'\nReason: Confirmation required for medium hazard tool\n\nTo proceed, reply with: Confirm: proceed\nTo cancel, reply with: cancel"
     },
     "requiresConfirmation": true,
     "confirmationPhrase": "Confirm: proceed",
     "pendingTool": "fabrication.queue_print",
     "hazardClass": "medium"
   }
   ```

5. **User Confirmation**:
   ```json
   POST /api/query
   {
     "conversationId": "conv-123",
     "userId": "user-001",
     "intent": "conversational",
     "prompt": "Confirm: proceed"
   }
   ```

6. **Orchestrator Verification**:
   - Checks for pending confirmation in conversation state
   - Verifies phrase matches: "Confirm: proceed"
   - Clears pending confirmation
   - Re-executes tool with confirmation granted

7. **Tool Execution**:
   - Safety check passes (confirmation provided)
   - Tool executes normally
   - Print job queued to `printer_01`

### Example: Cancel Action

```json
POST /api/query
{
  "conversationId": "conv-123",
  "userId": "user-001",
  "intent": "conversational",
  "prompt": "cancel"
}
```

Response:
```json
{
  "conversationId": "conv-123",
  "intent": "conversational",
  "result": {
    "output": "Action cancelled: fabrication.queue_print was not executed."
  }
}
```

---

## Testing the Integration

### 1. Start KITTY Services

```bash
# Ensure .env is updated with new variables
cp .env.example .env
# Edit .env as needed

# Start llama.cpp + Docker services
./ops/scripts/start-kitty.sh
```

### 2. Test Low-Hazard Tool (No Confirmation)

```bash
curl -X POST http://localhost:8080/api/query \
  -H "Content-Type: application/json" \
  -d '{
    "conversationId": "test-001",
    "userId": "user-001",
    "intent": "conversational",
    "prompt": "Search the web for the current weather in San Francisco",
    "useAgent": true
  }'
```

**Expected**: Direct execution, no confirmation required

### 3. Test Medium-Hazard Tool (Requires Confirmation)

```bash
# Request print job
curl -X POST http://localhost:8080/api/query \
  -H "Content-Type: application/json" \
  -d '{
    "conversationId": "test-002",
    "userId": "user-001",
    "intent": "conversational",
    "prompt": "Queue bracket.stl to printer_01",
    "useAgent": true
  }'
```

**Expected**: Response with `requiresConfirmation=true`, `confirmationPhrase="Confirm: proceed"`

```bash
# Provide confirmation
curl -X POST http://localhost:8080/api/query \
  -H "Content-Type: application/json" \
  -d '{
    "conversationId": "test-002",
    "userId": "user-001",
    "intent": "conversational",
    "prompt": "Confirm: proceed"
  }'
```

**Expected**: Tool execution proceeds

### 4. Test Cancellation

```bash
# Request high-hazard action
curl -X POST http://localhost:8080/api/query \
  -H "Content-Type: application/json" \
  -d '{
    "conversationId": "test-003",
    "userId": "user-001",
    "intent": "conversational",
    "prompt": "Unlock the front door",
    "useAgent": true
  }'

# Cancel
curl -X POST http://localhost:8080/api/query \
  -H "Content-Type: application/json" \
  -d '{
    "conversationId": "test-003",
    "userId": "user-001",
    "intent": "conversational",
    "prompt": "cancel"
  }'
```

**Expected**: Cancellation confirmation, tool not executed

### 5. Test Paid Tool Override

```bash
curl -X POST http://localhost:8080/api/query \
  -H "Content-Type: application/json" \
  -d '{
    "conversationId": "test-004",
    "userId": "user-001",
    "intent": "conversational",
    "prompt": "omega Use Perplexity to research quantum computing advances in 2024",
    "useAgent": true
  }'
```

**Expected**: Paid tool (`research_deep`) executes because `omega` (API_OVERRIDE_PASSWORD) was detected

---

## Configuration Reference

### Environment Variables

```bash
# Agent Configuration
REACT_MAX_ITERATIONS=10
AGENT_HISTORY_STEPS=4
AGENT_HISTORY_TOKEN_BUDGET=8000
AGENT_OBSERVATION_CHARS=2000

# Tool Registry
TOOL_REGISTRY_PATH=config/tool_registry.yaml

# Safety Configuration
HAZARD_CONFIRMATION_PHRASE="Confirm: proceed"
API_OVERRIDE_PASSWORD=omega
```

### Tool Registry Schema

```yaml
tools:
  tool_name:
    server: mcp_server_name
    description: Human-readable description
    hazard_class: none | low | medium | high
    requires_confirmation: true | false
    confirmation_phrase: "Custom phrase (optional)"
    requires_signature: true | false
    requires_override: true | false
    budget_tier: free | paid | premium
    enabled: true | false
    note: Additional context for users
```

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                          /api/query                             │
│                      (Query Route Handler)                      │
└─────────────────────┬───────────────────────────────────────────┘
                      │
                      ├─> Check for pending confirmation
                      │   (ConversationStateManager)
                      │
                      ├─> If pending & confirmed:
                      │   Clear state, proceed with tool execution
                      │
                      ├─> If pending & cancelled:
                      │   Return cancellation message
                      │
                      ├─> If pending & neither:
                      │   Re-display confirmation prompt
                      │
                      v
          ┌───────────────────────────┐
          │   BrainOrchestrator       │
          │   .generate_response()    │
          └───────────┬───────────────┘
                      │
                      v
          ┌───────────────────────────┐
          │      BrainRouter          │
          │      .route()             │
          └───────────┬───────────────┘
                      │
                      ├─> use_agent=true
                      │
                      v
          ┌───────────────────────────┐
          │    ReActAgent.run()       │
          │                           │
          │  ┌─────────────────────┐  │
          │  │ 1. Get tools        │  │
          │  │ 2. Reasoning loop   │  │
          │  │ 3. Tool validation  │  │
          │  │ 4. Safety check ⚠️   │  │
          │  │ 5. Execute or pause │  │
          │  └─────────────────────┘  │
          └───────────┬───────────────┘
                      │
                      ├─> Safety check fails
                      │   requires_confirmation=true
                      │
                      v
          ┌───────────────────────────┐
          │       AgentResult         │
          │  - answer (confirmation)  │
          │  - requires_confirmation  │
          │  - confirmation_phrase    │
          │  - pending_tool           │
          │  - pending_tool_args      │
          │  - hazard_class           │
          └───────────┬───────────────┘
                      │
                      v
          ┌───────────────────────────┐
          │      RoutingResult        │
          │   .metadata contains:     │
          │   - requires_confirmation │
          │   - confirmation_phrase   │
          │   - pending_tool          │
          │   - hazard_class          │
          └───────────┬───────────────┘
                      │
                      v
          ┌───────────────────────────┐
          │   Query Route Handler     │
          │  - Extract metadata       │
          │  - Set pending in state   │
          │  - Return QueryResponse   │
          └───────────┬───────────────┘
                      │
                      v
          ┌───────────────────────────┐
          │      QueryResponse        │
          │  - requiresConfirmation   │
          │  - confirmationPhrase     │
          │  - pendingTool            │
          │  - hazardClass            │
          └───────────────────────────┘
```

---

## Safety Matrix

| Tool | Hazard Class | Confirmation | Signature | Override | Budget Tier |
|------|-------------|--------------|-----------|----------|-------------|
| web_search | none | ❌ | ❌ | ❌ | free |
| research_deep | none | ❌ | ❌ | ✅ | paid |
| cad.generate_model | low | ❌ | ❌ | ✅ | premium |
| fabrication.queue_print | medium | ✅ | ❌ | ❌ | free |
| homeassistant.unlock_door | high | ✅ | ✅ | ❌ | free |
| homeassistant.enable_power | high | ✅ | ✅ | ❌ | free |
| broker.execute_command | medium | ✅ | ❌ | ❌ | free (disabled) |

---

## Next Steps

### Production Enhancements

1. **State Persistence**: Replace in-memory `ConversationStateManager` with Redis or PostgreSQL
2. **Signature Verification**: Implement cryptographic signature verification for `requires_signature=true` tools
3. **Dual Confirmation**: Add dual-confirmation flow for critical operations (two users must approve)
4. **Audit Logging**: Enhance PostgreSQL audit logs with confirmation events
5. **Rate Limiting**: Add per-user rate limits for high-hazard operations

### UI/CLI Integration

1. **Frontend**: Update React UI to handle `requiresConfirmation` in responses
2. **CLI**: Update `kitty-cli` to detect and prompt for confirmations
3. **Voice**: Add confirmation flow to voice interaction handler

### Testing

1. **Unit Tests**: Add tests for `SafetyChecker`, `ConversationState`, confirmation flow
2. **Integration Tests**: End-to-end tests for confirmation workflows
3. **Security Tests**: Attempt bypass of safety checks, confirmation expiration edge cases

---

## Troubleshooting

### Issue: Tools execute without confirmation

**Check**:
1. Is `TOOL_REGISTRY_PATH` correctly set in `.env`?
2. Does `config/tool_registry.yaml` exist and have correct permissions?
3. Is `requires_confirmation: true` set for the tool?
4. Is `use_agent=true` in the request? (Safety checks only apply in agent mode)

### Issue: Confirmation phrase not recognized

**Check**:
1. Phrase is case-insensitive and substring-matched
2. Default phrase: "Confirm: proceed" (can override in `.env` with `HAZARD_CONFIRMATION_PHRASE`)
3. Tool-specific phrase in `tool_registry.yaml` takes precedence

### Issue: Paid tools blocked even with override password

**Check**:
1. Is `API_OVERRIDE_PASSWORD` set in `.env`?
2. Is the password present in the user's prompt? (e.g., "omega search for...")
3. Is `requires_override: true` set in tool registry?

---

## Git History

```bash
# View integration commits
git log --oneline --grep="feat:" --since="2025-01-10"

276cb2b feat: Reorganize .env and create tool registry for ReAct framework
8fe09b4 feat: Add conversation framework with safety and state management
a61c041 feat: Integrate safety checks into ReAct agent before tool execution
5e551d3 feat: Enhance orchestrator with conversation state and confirmation flow
4f38d1f feat: Wire up confirmation flow through routing and query layers
```

---

## References

- **Implementation Guide**: `Research/KITTY_Conversation_Framework_Implementation.md`
- **Tool Registry**: `config/tool_registry.yaml`
- **Environment Config**: `.env.example`
- **Conversation Module**: `services/brain/src/brain/conversation/`
- **ReAct Agent**: `services/brain/src/brain/agents/react_agent.py`
- **Orchestrator**: `services/brain/src/brain/orchestrator.py`
- **Query Route**: `services/brain/src/brain/routes/query.py`
- **Router**: `services/brain/src/brain/routing/router.py`
