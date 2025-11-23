# KITTY Agents Overview

_Last refreshed from repo state `448ae9e`._ This note captures what is currently implemented for KITTY's agentic stack so future work can quickly see what is real, what is stubbed, and where to plug in. It complements [`docs/tools-and-agents.md`](tools-and-agents.md), which goes deeper on the tool catalog itself.

> Developer workflow: always run the relevant tests or health checks after each feature/fix so agent behavior is verified before considering work done.

## Current Agent Stack

| Component | Location | Trigger / Entry | Purpose | Status |
| --- | --- | --- | --- | --- |
| **Brain Router / Orchestrator** | `services/brain/src/brain/orchestrator.py`, `routing/router.py` | Gateway → Brain `generate_response()` | Chooses routing tier (Q4 ↔ F16), enforces confirmations, hands off to agents/tools. | Shipping – LangGraph integration behind feature flag. |
| **ReAct Tool Agent** | `services/brain/src/brain/agents/react_agent.py` | `BrainOrchestrator.generate_response(... use_agent=True)` or CLI `/agent on` | Iterative Thought → Action → Observation loop over MCP tools with llama.cpp Qwen2.5. | Shipping locally; guarded by `AGENTIC_MODE_ENABLED` / `KITTY_TOOLS_ENABLED`. |
| **LangGraph Router Graphs** | `services/brain/src/brain/agents/graphs/*.py` | `LangGraphRoutingIntegration` when `BRAIN_USE_LANGGRAPH=true` | Structured routing with complexity scoring, multi-tier escalation, tool orchestration. | Graph + metrics implemented, Brain integration rollout pending (README shows TODO for wiring/tests). |
| **Tool Orchestrator** | `services/brain/src/brain/agents/orchestration/tool_orchestrator.py` | Called by LangGraph nodes or future workflows | Parallel tool execution with dependency graph + retries + hazard checkpoints. | Library written; integration work tracked in Phase 2 plan. |
| **Collective Meta-Agent** | `services/brain/src/brain/agents/collective/`, docs in `docs/agents/collective.md` | Brain endpoint `POST /api/collective/run`, Gateway `/api/collective/run`, CLI `kitty-cli ... /agent on` | Offline council/debate/pipeline patterns with proposer blinding and F16 judge. | Council/debate live; pipeline node still stubbed with placeholder result. |
| **Coder Agent Service** | `services/coder-agent/src/coder_agent/` | Dedicated FastAPI app (`main.py`) or invoked via Collective pipeline | LangGraph Plan → Code → Test → Run → Refine → Summarize loop with sandboxed pytest tests. | Service + tests exist; wiring into Collective pipeline still TODO. |

The diagram below mirrors what the code is doing today:

```
User / CLI / Gateway
        │
        ▼
 BrainOrchestrator (services/brain/.../orchestrator.py)
        │
        ├─► Traditional BrainRouter (local Q4) ──► Direct response
        │
        ├─► LangGraphRoutingIntegration (if enabled)
        │       │
        │       └─► router_graph → ToolOrchestrator → MCP tools
        │
        └─► ReActAgent (use_agent=True)
                │
                └─► MCPClient → CAD / Home Assistant / Memory / Research / Vision servers
```

## Brain ReAct Agent (`services/brain/src/brain/agents/react_agent.py`)

**Responsibilities**
- Builds a unified Kitty prompt via `KittySystemPrompt` and injects limited history (`AGENT_HISTORY_STEPS`, `AGENT_HISTORY_TOKEN_BUDGET`).
- Runs up to `REACT_MAX_ITERATIONS` (default 10) using Qwen2.5 via `LlamaCppClient`, with auto-detected model format (`detect_model_format`).
- Calls `MCPClient` for tool execution and uses `ToolCallValidator` to reject hallucinated calls before they hit the executor.
- Pipes observations through `SafetyChecker` (hazard confirmations) and `SafeToolExecutor` (hazard + budget gating in `services/brain/src/brain/tools/executor.py`).
- Applies `_ground_final_answer` so “current/latest” responses stay tied to recent `web_search` data.

**Key behaviors surfaced in code**
- History is truncated either by count (`AGENT_HISTORY_STEPS`, default 4) or by `AGENT_HISTORY_TOKEN_BUDGET` (default 8000) using `_history_for_prompt`.
- Observations are trimmed to `AGENT_OBSERVATION_CHARS` (default 2000) before being fed back to the LLM.
- The agent keeps a dedicated `_tool_mcp` reference so callers can bypass the loop for direct tool execution fallbacks if needed.

**Configuration checklist**
- `.env`: `AGENTIC_MODE_ENABLED=true`, `KITTY_TOOLS_ENABLED=true`, `LLAMACPP_TOOL_CALLING=1`, plus MCP host URLs (`CAD_SERVICE_URL`, `HOME_ASSISTANT_URL`, `MEM0_MCP_URL`, etc.).
- llama.cpp must be launched with the jinja/function attachment flags (see `docs/tools-and-agents.md#llamacpp-setup`).
- Budget + hazard gating are controlled via `BUDGET_PER_TASK_USD`, `API_OVERRIDE_PASSWORD`, and `HAZARD_CONFIRMATION_PHRASE`.

**Tests & validation**
- Parser + llama.cpp interfaces: `tests/test_tool_calling.py`, `tests/test_live_tool_calling.py`, and `tests/test_parser_only.py` cover XML extraction and backwards compatibility.
- End-to-end flows that depend on the agent + MCP tools: `tests/test_kitty_conversation.py`, `tests/integration/test_brain_cad_flow.py`, `tests/integration/test_homeassistant_integration.py`, and `tests/integration/test_e2e_cad_workflow.py` all exercise tool execution paths.

## Tool Orchestrator & Safety Net

- `services/brain/src/brain/agents/orchestration/tool_orchestrator.py` defines `ToolExecutionPlan` batches, dependency graphs (e.g., `generate_cad` → `analyze_model` → `slice_model` → `queue_print`), retries with exponential backoff, and status tracking (`ToolStatus`).
- Designed to plug into LangGraph nodes so that multiple tools can execute in parallel while honoring hazards (e.g., queueing `control_device` until confirmation arrives).
- Hazard handling lives in `services/brain/src/brain/tools/executor.py` and is shared between ReAct and LangGraph. It enforces confirmation phrases for `lock.unlock` and `power.enable`, and records approval metadata for auditing.

## LangGraph Routing Graphs (`services/brain/src/brain/agents/graphs/`)

- `router_graph.py` + `states.py` implement a structured state machine with:
  - `complexity/analyzer.py` to score incoming prompts and choose between Q4 direct, Q4 with escalation, or F16 deep reasoning.
  - Memory-aware branches that call `MemoryClient` and `MCPClient` directly from graph nodes.
  - Hooks for `ToolOrchestrator` so dependent tools (CAD → fabrication) run in the right order.
- `integration.py` exposes `LangGraphRoutingIntegration`, which the Brain orchestrator instantiates and gates via `BRAIN_USE_LANGGRAPH` and `BRAIN_LANGGRAPH_ROLLOUT_PERCENT`. Rollout uses conversation-id hashing for predictable A/B.</n- Observability is already wired through `services/brain/src/brain/agents/metrics/langgraph_metrics.py` (Prometheus counters for node latency, tier routing, confidence, tool success, etc.).
- Current state (per `services/brain/src/brain/agents/graphs/README.md`): router graph and complexity analyzer are done, but “Integration with BrainOrchestrator” and dedicated tests remain unchecked, so expect to keep the feature flag off until those TODOs close.
- Relevant tests today: `tests/integration/test_research_graph_wiring.py`, `tests/integration/test_phase3_integration.py`, `tests/integration/test_multi_provider.py`, and the shell harness in `tests/langgraph_system_test.sh` validate wiring, though they still mock some downstream services.

## Collective Meta-Agent (`services/brain/src/brain/agents/collective/`)

- Graph defined in `graph.py` uses LangGraph’s `StateGraph` to support three patterns:
  1. **pipeline** – placeholder that expects an external coding graph to drop results in; currently returns a stub (`"<pipeline result inserted by router>"`).
  2. **council** – spawns `k` specialists (`specialist_1` uses `Q4B` for diversity, others use `Q4`), each receiving filtered memory context via `context_policy.fetch_domain_context(... for_proposer=True)` which blinds them to `meta/dev/collective` tags.
  3. **debate** – produces PRO/CON arguments with the same blinding rules.
- `judge` node always runs on `F16`, sees full context (`for_proposer=False`), and returns the final verdict + rationale.
- Environment knobs: `COLLECTIVE_PROPOSER_BLIND`, `MEMORY_EXCLUDE_TAGS`, `MEMORY_INCLUDE_TAGS`, `COLLECTIVE_HINT_PROPOSER`, `COLLECTIVE_HINT_JUDGE`.
- Routes/usage:
  - Brain: `POST /api/collective/run` (see `tests/integration/test_collective_api.py`).
  - Gateway exposes `/api/collective/run` and is invoked by CLI via `kitty-cli say "/agent on. call collective.run pattern=council k=3 ..."` (documented in `docs/agents/collective.md`).
- Offline-only guarantee: all nodes call local llama.cpp via `brain.llm_client.chat` and never touch network APIs.
- Next steps noted in repo:
  - Replace pipeline placeholder with an actual drop-in from `services/coder-agent`.
  - Expand proposer metrics/aggregation (currently `aggregate.py` exposes a best-of scoring helper, but `graph.py` returns raw proposals and defers scoring to judge).

## Coder Agent Service (`services/coder-agent/src/coder_agent/`)

- `graph.py` implements a LangGraph workflow with `plan → code → tests → run → refine → summarize`. Refinement loops continue until tests pass or `max_refinements` is hit (default 2).
- `sandbox.py` contains an isolated pytest runner that mounts temp dirs and enforces timeouts, preventing runaway tests.
- The FastAPI app (`app.py` / `main.py`) exposes `/api/coder/run` plus health endpoints so it can be run as a standalone microservice or invoked from the Collective pipeline.
- Prompting strategy (see `prompts.py`): dedicated system prompt (`CODER_SYSTEM`), planning template, code template capped by `MAX_CODE_LENGTH`, and targeted test/refine prompts so outputs remain deterministic for 32B Qwen.
- Tests/shims:
  - `tests/integration/test_coder_integration.sh` spins up the service and verifies the REST surface.
  - `tests/integration/test_diversity_seat.sh` and `tests/integration/test_high_impact_additions_smoke.sh` include scenarios where the coding agent is expected to be called from Collective council members.

## Supporting Docs & Next Steps

- Operator quick-notes for the Collective live in [`docs/agents/collective.md`](agents/collective.md); deployment/runbook details are in `docs/COLLECTIVE_META_AGENT_DEPLOYMENT.md`.
- Tool schemas, safety rules, and configuration live in [`docs/tools-and-agents.md`](tools-and-agents.md). Keep that doc updated when adding MCP servers or hazard classes.
- Planning references: `Research/KITTY_LangGraph_Multi_Agent_Enhancement.md`, `Research/KITTY_LangGraph_Coding_Agent_Integration_Guide.md`, `Research/offline-agent-research-workflow.md` describe the future Phase 2 “agent-runtime” service mentioned throughout the code.
- Known gaps from the codebase:
  1. LangGraph router is implemented but not fully wired into `BrainOrchestrator` (feature flag stays off until tests + rollout config are in place).
  2. Collective `pipeline` path still expects the coder agent drop-in.
  3. ToolOrchestrator is not yet invoked from the ReAct loop; today the ReAct agent still executes tools sequentially.
  4. Observatory dashboards for the Prometheus metrics (`brain_graph_*`, `brain_tier_*`) have TODOs in `docs/tool-aware-implementation-roadmap.md` – no Grafana panels checked in yet.

Having this snapshot should make it straightforward to reason about where a new agent should live, which toggles to flip, and which tests/docs to touch when shipping changes.
