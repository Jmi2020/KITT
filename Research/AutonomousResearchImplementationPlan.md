# KITT Autonomous Research Implementation Plan

**Created:** 2025-01-16
**Status:** Ready for Implementation
**Target:** Enable 2-6 hour autonomous research sessions with fault tolerance

## Executive Summary

This plan implements four interconnected systems to enable KITT's autonomous research capabilities as outlined in `KITTYAutonomousResearch.md`. The implementation builds on existing infrastructure (LangGraph, PostgreSQL, Redis, MCP) and adds: persistent checkpointing, advanced tool orchestration, dual-model coordination, and quality metrics.

**Key Outcomes:**
- Hours-long research sessions with automatic crash recovery
- 85% cost reduction through intelligent Q4/F16 routing
- Quantitative stopping criteria (RAGAS metrics + saturation detection)
- Real-time quality monitoring and gap detection

---

## Current State Analysis

### What Exists
- ✅ **LangGraph:** Already integrated for collective meta-agent workflows (`brain/agents/collective/graph_async.py`)
- ✅ **PostgreSQL:** Database infrastructure in place
- ✅ **Redis:** Cache layer operational
- ✅ **MCP:** Tool execution framework (`brain/tools/mcp_client.py`)
- ✅ **ReAct Agent:** Production agent with safety checks (`brain/agents/react_agent.py`)
- ✅ **Q4/F16 Models:** Dual local model setup via llama.cpp
- ✅ **Research Tools:** Web search, fetch_webpage, research_deep (`mcp/servers/research_server.py`)

### What's Missing
- ❌ **PostgreSQL Checkpointing:** LangGraph graphs don't persist to database
- ❌ **Session Management:** No long-running session lifecycle support
- ❌ **Advanced Orchestration:** Missing wave execution, validation pipelines, strategy selection
- ❌ **Model Coordinator:** No intelligent Q4/F16 routing based on complexity
- ❌ **Quality Metrics:** No RAGAS, confidence scoring, or saturation detection
- ❌ **Streaming Progress:** No real-time updates for long sessions

---

## Implementation Roadmap

### Phase 1: Foundation - State Management & Checkpointing (Week 1-2)

**Goal:** Enable persistent, recoverable research sessions

#### 1.1 PostgreSQL Checkpointing Infrastructure

**Files to Create:**
- `services/brain/src/brain/research/checkpoint.py` - PostgresSaver configuration
- `services/brain/src/brain/research/session_manager.py` - Session lifecycle management
- `services/brain/migrations/006_research_checkpoints.sql` - Database schema

**Database Schema:**
```sql
-- LangGraph auto-creates these, but we'll ensure they exist
CREATE TABLE IF NOT EXISTS checkpoints (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    checkpoint_id TEXT NOT NULL,
    parent_checkpoint_id TEXT,
    type TEXT,
    checkpoint JSONB NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}',
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
);

CREATE INDEX IF NOT EXISTS idx_checkpoints_thread_ts
    ON checkpoints(thread_id, checkpoint_ns, checkpoint->>'ts' DESC);

CREATE TABLE IF NOT EXISTS checkpoint_blobs (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    channel TEXT NOT NULL,
    version TEXT NOT NULL,
    type TEXT NOT NULL,
    blob BYTEA,
    PRIMARY KEY (thread_id, checkpoint_ns, channel, version)
);

CREATE TABLE IF NOT EXISTS checkpoint_writes (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    checkpoint_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    idx INTEGER NOT NULL,
    channel TEXT NOT NULL,
    type TEXT,
    blob BYTEA,
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
);

-- Custom tables for research tracking
CREATE TABLE research_sessions (
    session_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    query TEXT NOT NULL,
    status TEXT DEFAULT 'active',  -- active, paused, completed, failed
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    thread_id TEXT,
    metadata JSONB,
    FOREIGN KEY (thread_id) REFERENCES checkpoints(thread_id) ON DELETE CASCADE
);

CREATE TABLE research_findings (
    id SERIAL PRIMARY KEY,
    session_id TEXT REFERENCES research_sessions(session_id) ON DELETE CASCADE,
    finding_type TEXT,  -- material, property, supplier, cost, design
    content TEXT,
    confidence FLOAT,
    sources JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_research_sessions_status ON research_sessions(status);
CREATE INDEX idx_research_sessions_user ON research_sessions(user_id);
CREATE INDEX idx_research_findings_session ON research_findings(session_id);
```

**Implementation Steps:**
1. Create `checkpoint.py` with PostgresSaver initialization from connection pool
2. Build `ResearchSessionManager` class with methods:
   - `create_session(user_id, query, config) -> session_id`
   - `pause_session(session_id) -> void`
   - `resume_session(session_id, additional_context) -> void`
   - `get_session_status(session_id) -> SessionStatus`
   - `list_user_sessions(user_id) -> List[SessionInfo]`
3. Implement distributed recovery with Redis locks
4. Add state compression for long sessions (>50 messages)
5. Write tests: create → crash → recover → verify state

**Dependencies:**
```python
# Add to pyproject.toml
"langgraph-checkpoint-postgres>=0.0.6",
"psycopg[binary,pool]>=3.1",
```

**Success Criteria:**
- Create session, kill process mid-execution, resume successfully
- State persists across restarts
- Multiple concurrent sessions isolated by thread_id
- Compression triggers at 50+ messages

---

#### 1.2 FastAPI Session Endpoints

**Files to Modify/Create:**
- `services/brain/src/brain/routes/research.py` - New research session routes
- `services/brain/src/brain/routes/__init__.py` - Register new routes

**Endpoints:**
```python
POST   /api/research/sessions              # Create new research session
GET    /api/research/sessions              # List user's sessions
GET    /api/research/sessions/{id}         # Get session details
POST   /api/research/sessions/{id}/pause   # Pause session
POST   /api/research/sessions/{id}/resume  # Resume session
DELETE /api/research/sessions/{id}         # Cancel session
WS     /api/research/sessions/{id}/stream  # Stream progress
```

**Implementation:**
```python
from fastapi import APIRouter, BackgroundTasks, WebSocket
from brain.research.session_manager import ResearchSessionManager

router = APIRouter(prefix="/api/research", tags=["research"])

@router.post("/sessions")
async def create_research_session(
    query: str,
    user_id: str,
    config: Optional[Dict] = None,
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    session_id = await session_manager.create_session(user_id, query, config)
    background_tasks.add_task(monitor_session, session_id)
    return {"session_id": session_id, "status": "started"}

@router.websocket("/sessions/{session_id}/stream")
async def stream_session_progress(websocket: WebSocket, session_id: str):
    await websocket.accept()
    async for event in session_manager.stream_events(session_id):
        await websocket.send_json(event)
```

**Success Criteria:**
- Create session via API, receive session_id
- WebSocket streams real-time progress events
- Pause/resume works via API calls
- Background task monitors session health

---

### Phase 2: Advanced Tool Orchestration (Week 3-4)

**Goal:** Implement wave execution, validation pipelines, and strategy selection

#### 2.1 Tool Dependency Graph & Wave Execution

**Files to Create:**
- `services/brain/src/brain/research/orchestration/tool_graph.py` - Dependency graph
- `services/brain/src/brain/research/orchestration/wave_executor.py` - Wave-based parallel execution

**Implementation:**
```python
class ToolNode:
    def __init__(self, tool_id: str, tool: BaseTool):
        self.tool_id = tool_id
        self.tool = tool
        self.dependencies: List[str] = []
        self.success_rate = 1.0

class WaveOrchestrator:
    def __init__(self, tools: List[BaseTool]):
        self.graph = self._build_dependency_graph(tools)
        self.waves = self._calculate_waves()

    def _calculate_waves(self) -> List[List[str]]:
        """Topological sort for wave-based execution"""
        waves = []
        remaining = set(self.graph.nodes.keys())
        completed = set()

        while remaining:
            # Find nodes with all dependencies satisfied
            wave = [n for n in remaining
                   if all(d in completed for d in self.graph.nodes[n].dependencies)]
            if not wave:
                raise CyclicDependencyError("Tool dependency cycle detected")

            waves.append(wave)
            remaining -= set(wave)
            completed.update(wave)

        return waves

    async def execute(self, inputs: Dict) -> Dict:
        """Execute tools in waves (parallel within wave, sequential across waves)"""
        context = inputs.copy()

        for wave in self.waves:
            tasks = [self._execute_tool(tool_id, context) for tool_id in wave]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for tool_id, result in zip(wave, results):
                if isinstance(result, Exception):
                    logger.error(f"Tool {tool_id} failed: {result}")
                    context[f"{tool_id}_error"] = str(result)
                else:
                    context[f"{tool_id}_result"] = result

        return context
```

**Success Criteria:**
- Define 5+ tools with dependencies
- Topological sort produces correct wave order
- Independent tools execute in parallel (verify timing)
- Handles failures gracefully

---

#### 2.2 Multi-Layer Validation Pipeline

**Files to Create:**
- `services/brain/src/brain/research/validation/pipeline.py` - Validation orchestration
- `services/brain/src/brain/research/validation/hallucination.py` - Claim verification
- `services/brain/src/brain/research/validation/schema.py` - Input/output validation

**Implementation:**
```python
class ValidationPipeline:
    def __init__(self):
        self.validators = [
            SchemaValidator(),
            FormatValidator(),
            QualityValidator(),
            HallucinationDetector()
        ]

    async def validate_input(self, tool_name: str, input_data: Dict) -> ValidationResult:
        """Validate before tool execution"""
        schema = get_tool_schema(tool_name)
        return SchemaValidator().validate(input_data, schema)

    async def validate_output(self, output: ToolOutput) -> ValidationResult:
        """Validate after tool execution"""
        results = await asyncio.gather(*[
            v.validate(output) for v in self.validators
        ])

        passed = all(r.passed for r in results)
        confidence = min(r.confidence for r in results) if results else 0.0

        return ValidationResult(
            passed=passed,
            confidence=confidence,
            issues=[i for r in results for i in r.issues]
        )

    async def validate_chain(self, source_output: ToolOutput,
                            target_input: Dict) -> ValidationResult:
        """Validate data compatibility between chained tools"""
        # Check that source output provides required fields for target input
        required_fields = get_tool_schema(target_input['tool']).required
        available_fields = set(source_output.data.keys())

        missing = set(required_fields) - available_fields
        if missing:
            return ValidationResult(
                passed=False,
                confidence=0.0,
                issues=[f"Missing required fields: {missing}"]
            )

        return ValidationResult(passed=True, confidence=1.0, issues=[])
```

**Hallucination Detection:**
```python
class HallucinationDetector:
    async def validate(self, output: ToolOutput) -> ValidationResult:
        """Check if claims are supported by sources"""
        if not output.metadata.get('sources'):
            return ValidationResult(
                passed=False,
                confidence=0.0,
                issues=["No sources provided for verification"]
            )

        claims = self._extract_claims(output.content)
        sources = output.metadata['sources']

        supported_count = sum(
            1 for claim in claims
            if self._verify_claim_in_sources(claim, sources)
        )

        support_rate = supported_count / len(claims) if claims else 1.0

        return ValidationResult(
            passed=support_rate >= 0.85,
            confidence=support_rate,
            issues=[] if support_rate >= 0.85 else ["Low claim support rate"]
        )

    def _extract_claims(self, text: str) -> List[str]:
        """Extract atomic factual claims from text"""
        # Use LLM to decompose text into atomic claims
        prompt = f"Extract atomic factual claims from:\n{text}\n\nReturn JSON list."
        response = llm_call(prompt, temperature=0.1)
        return json.loads(response)

    def _verify_claim_in_sources(self, claim: str, sources: List[Dict]) -> bool:
        """Check if claim appears in any source"""
        for source in sources:
            if claim.lower() in source['content'].lower():
                return True
        return False
```

**Success Criteria:**
- Schema validation catches invalid inputs
- Hallucination detector identifies unsupported claims
- Chain validation prevents incompatible tool sequences
- Validation failures trigger refinement loops

---

#### 2.3 Multi-Strategy Research Agents

**Files to Create:**
- `services/brain/src/brain/research/agents/breadth_first.py` - Parallel exploration
- `services/brain/src/brain/research/agents/depth_first.py` - Iterative refinement
- `services/brain/src/brain/research/agents/task_decomposition.py` - Hierarchical planning
- `services/brain/src/brain/research/orchestration/strategy_selector.py` - Strategy routing

**Implementation:**
```python
class MultiStrategyOrchestrator:
    def __init__(self, tools: List[BaseTool]):
        self.tools = tools
        self.strategies = {
            "react": ReActAgent(llm, tools),
            "breadth_first": BreadthFirstAgent(llm, tools),
            "depth_first": DepthFirstAgent(llm, tools),
            "task_decomposition": TaskDecompositionAgent(llm, tools)
        }
        self.metrics = MetricsCollector()

    async def execute(self, query: str, strategy: str = "auto") -> Dict:
        if strategy == "auto":
            strategy = await self._select_strategy(query)

        logger.info(f"Using strategy: {strategy} for query: {query[:100]}")
        agent = self.strategies[strategy]

        start_time = time.time()
        result = await agent.run(query)
        latency = time.time() - start_time

        self.metrics.record(strategy, result, latency)

        return {
            "result": result,
            "strategy_used": strategy,
            "latency": latency,
            "metrics": result.get("metrics", {})
        }

    async def _select_strategy(self, query: str) -> str:
        """Classify query and select best strategy"""
        classification_prompt = f"""Analyze this research query and select the best strategy:

Query: {query}

Strategies:
- react: General reasoning with iterative tool use (good for exploratory research)
- breadth_first: Parallel exploration of multiple hypotheses (good for comparing options)
- depth_first: Iterative refinement with validation loops (good for design iteration)
- task_decomposition: Break into subtasks for complex goals (good for multi-faceted problems)

Respond with just the strategy name."""

        response = await llm_call(classification_prompt, model="Q4", temperature=0.1)
        strategy = response.strip().lower()

        if strategy not in self.strategies:
            logger.warning(f"Invalid strategy '{strategy}', defaulting to react")
            return "react"

        return strategy
```

**Breadth-First Agent (for parallel material exploration):**
```python
class BreadthFirstAgent:
    async def run(self, query: str) -> Dict:
        """Explore multiple hypotheses in parallel"""

        # Generate hypotheses
        hypotheses = await self._generate_hypotheses(query)
        logger.info(f"Generated {len(hypotheses)} hypotheses to explore")

        # Investigate all hypotheses in parallel
        tasks = [self._investigate_hypothesis(h, query) for h in hypotheses]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter failures
        valid_results = [r for r in results if not isinstance(r, Exception)]

        # Rank and select best
        ranked = await self._rank_results(valid_results, query)

        return {
            "hypotheses_explored": len(hypotheses),
            "successful_investigations": len(valid_results),
            "ranked_results": ranked,
            "best_option": ranked[0] if ranked else None
        }

    async def _generate_hypotheses(self, query: str) -> List[str]:
        """Generate multiple alternative approaches"""
        prompt = f"Generate 5 alternative approaches for: {query}\nReturn as JSON list."
        response = await llm_call(prompt, model="Q4")
        return json.loads(response)

    async def _investigate_hypothesis(self, hypothesis: str, original_query: str) -> Dict:
        """Deeply investigate one hypothesis"""
        # Use existing ReAct agent for each hypothesis
        agent = ReActAgent(self.llm, self.tools, max_iterations=5)
        return await agent.run(f"{original_query}\nFocus on: {hypothesis}")
```

**Success Criteria:**
- Strategy selector chooses appropriate strategy for different query types
- Breadth-first explores 5+ hypotheses in parallel
- Task decomposition breaks complex queries into subtasks
- Metrics show performance differences between strategies

---

### Phase 3: Model Coordination Protocol (Week 5)

**Goal:** Implement intelligent Q4/F16 routing and consultation patterns

#### 3.1 Model Capability Registry & Router

**Files to Create:**
- `services/brain/src/brain/research/models/registry.py` - Model capability definitions
- `services/brain/src/brain/research/models/coordinator.py` - Routing logic
- `services/brain/src/brain/research/models/consultation.py` - Validation loops

**Model Registry:**
```python
MODEL_REGISTRY = {
    "llama-3.1-8b-q4": {
        "type": "local",
        "cost": 0.0,
        "latency_p50": 0.5,
        "latency_p95": 1.2,
        "capabilities": {
            "reasoning": 0.6,
            "tool_use": 0.8,
            "code": 0.7,
            "math": 0.6,
            "synthesis": 0.5
        },
        "context_window": 8192,
        "max_tokens": 2048,
        "endpoint": "http://localhost:8001/v1/chat/completions"
    },
    "llama-3.1-70b-f16": {
        "type": "local",
        "cost": 0.0,
        "latency_p50": 5.0,
        "latency_p95": 12.0,
        "capabilities": {
            "reasoning": 0.85,
            "tool_use": 0.75,
            "code": 0.8,
            "math": 0.85,
            "synthesis": 0.9
        },
        "context_window": 32768,
        "max_tokens": 4096,
        "endpoint": "http://localhost:8002/v1/chat/completions"
    },
    "gpt-4": {
        "type": "external",
        "cost": 0.03,  # per 1k tokens
        "latency_p50": 2.0,
        "latency_p95": 5.0,
        "capabilities": {
            "reasoning": 0.95,
            "tool_use": 0.9,
            "code": 0.9,
            "math": 0.9,
            "synthesis": 0.95
        },
        "context_window": 128000,
        "max_tokens": 4096,
        "endpoint": "https://api.openai.com/v1/chat/completions"
    }
}

class ModelCapabilityRegistry:
    def __init__(self):
        self.registry = MODEL_REGISTRY.copy()
        self.performance_tracker = PerformanceTracker()

    def get_best_model(self, task_type: str,
                       max_cost: float = 0.0,
                       max_latency: float = float('inf')) -> str:
        """Select best model for task within constraints"""

        candidates = []
        for model_id, spec in self.registry.items():
            # Filter by constraints
            if spec['cost'] > max_cost:
                continue
            if spec['latency_p50'] > max_latency:
                continue

            # Score by capability
            capability_score = spec['capabilities'].get(task_type, 0.5)

            # Adjust by observed performance
            actual_performance = self.performance_tracker.get_success_rate(model_id, task_type)
            if actual_performance:
                capability_score = 0.7 * capability_score + 0.3 * actual_performance

            candidates.append((model_id, capability_score))

        if not candidates:
            return "llama-3.1-8b-q4"  # Fallback to Q4

        # Return highest scoring model
        return max(candidates, key=lambda x: x[1])[0]

    def update_performance(self, model_id: str, task_type: str,
                          success: bool, latency: float):
        """Update registry based on actual performance"""
        self.performance_tracker.record(model_id, task_type, success, latency)

        # Update latency estimates
        avg_latency = self.performance_tracker.get_avg_latency(model_id)
        if avg_latency:
            self.registry[model_id]['latency_p50'] = avg_latency
```

**Coordinator:**
```python
class KITTModelCoordinator:
    def __init__(self):
        self.registry = ModelCapabilityRegistry()
        self.client = httpx.AsyncClient(timeout=60.0)
        self.cache = SemanticCache()

        self.stats = {
            "q4_calls": 0,
            "f16_calls": 0,
            "external_calls": 0,
            "cache_hits": 0,
            "total_cost": 0.0
        }

    async def coordinate(self,
                        query: str,
                        task_type: str = "reasoning",
                        context: Optional[Dict] = None,
                        max_cost: float = 0.0) -> CoordinationResult:
        """Main coordination entry point"""

        # Check cache first
        cached = await self.cache.get(query, context)
        if cached:
            self.stats["cache_hits"] += 1
            return cached

        # Classify complexity
        classification = await self._classify_query(query)

        # Route based on complexity and constraints
        if classification["complexity"] < 0.3:
            result = await self._execute_with_model("llama-3.1-8b-q4", query, context)
        elif classification["complexity"] < 0.7:
            if classification["requires_synthesis"]:
                result = await self._consult_f16_for_synthesis(query, context, classification)
            else:
                result = await self._execute_with_model("llama-3.1-8b-q4", query, context)
        else:
            # High complexity - use F16 or external
            if max_cost == 0.0:
                result = await self._execute_with_model("llama-3.1-70b-f16", query, context)
            else:
                result = await self._execute_with_model("gpt-4", query, context)

        # Cache result
        await self.cache.set(query, context, result)

        return result

    async def _classify_query(self, query: str) -> Dict:
        """Use Q4 to classify query complexity"""
        classification_prompt = f"""Analyze and respond with JSON only:
{{
  "complexity": 0.0-1.0,
  "requires_tools": true/false,
  "requires_synthesis": true/false,
  "reasoning_depth": "shallow|medium|deep",
  "estimated_tokens": number
}}

Query: {query}"""

        response = await self._call_model("llama-3.1-8b-q4", classification_prompt)
        self.stats["q4_calls"] += 1

        return json.loads(response)

    async def _consult_f16_for_synthesis(self, query: str,
                                         context: Dict,
                                         classification: Dict) -> CoordinationResult:
        """Q4 gathers data, F16 synthesizes"""

        # Q4 gathers information
        gathering_prompt = f"Gather relevant information for: {query}"
        raw_data = await self._execute_with_model("llama-3.1-8b-q4", gathering_prompt, context)
        self.stats["q4_calls"] += 1

        # F16 synthesizes
        synthesis_prompt = f"""Synthesize this information into a coherent answer:

Question: {query}

Raw data:
{raw_data.content}

Provide: synthesized answer with key insights."""

        synthesis = await self._execute_with_model("llama-3.1-70b-f16", synthesis_prompt, None)
        self.stats["f16_calls"] += 1

        return CoordinationResult(
            content=synthesis.content,
            model_used="llama-3.1-70b-f16",
            strategy="q4_gather_f16_synthesize",
            cost=0.0,
            latency=raw_data.latency + synthesis.latency
        )
```

**Success Criteria:**
- Q4 handles 70-80% of queries completely
- F16 used for synthesis (15-20% of queries)
- External APIs reserved for <10% of queries
- Cost tracking shows 85%+ reduction vs all-GPT-4
- Performance tracker updates success rates

---

#### 3.2 Mixture of Agents for Critical Decisions

**Files to Create:**
- `services/brain/src/brain/research/models/mixture.py` - MoA debate implementation

**Implementation:**
```python
class MixtureOfAgentsDebate:
    def __init__(self, proposer_models: List[str], aggregator_model: str):
        self.proposers = proposer_models
        self.aggregator = aggregator_model
        self.coordinator = KITTModelCoordinator()

    async def debate(self, query: str, context: Dict, rounds: int = 2) -> DebateResult:
        """Multi-round debate for critical decisions"""

        # Round 1: Independent proposals
        proposals = await self._generate_independent_proposals(query, context)

        # Rounds 2+: Iterative refinement
        for round_num in range(1, rounds):
            proposals = await self._refine_with_peer_review(query, proposals, round_num)

        # Final aggregation
        final_decision = await self._aggregate_proposals(query, proposals, context)

        return DebateResult(
            decision=final_decision,
            proposals=proposals,
            rounds=rounds,
            consensus_score=self._calculate_consensus(proposals)
        )

    async def _generate_independent_proposals(self, query: str, context: Dict) -> List[Proposal]:
        """Each model proposes independently"""

        tasks = []
        for model_id in self.proposers:
            prompt = f"Analyze and provide your recommendation:\n{query}\n\nContext: {context}"
            tasks.append(self.coordinator._execute_with_model(model_id, prompt, None))

        responses = await asyncio.gather(*tasks)

        return [
            Proposal(model=model, content=resp.content, confidence=0.7)
            for model, resp in zip(self.proposers, responses)
        ]

    async def _refine_with_peer_review(self, query: str,
                                       proposals: List[Proposal],
                                       round_num: int) -> List[Proposal]:
        """Each model sees others' proposals and refines"""

        refined = []
        for i, proposal in enumerate(proposals):
            others = [p for j, p in enumerate(proposals) if j != i]

            peer_review_prompt = f"""Your previous response: {proposal.content}

Others' responses:
{chr(10).join(f"- {p.model}: {p.content}" for p in others)}

Critique all responses and provide an improved answer for: {query}"""

            refined_resp = await self.coordinator._execute_with_model(
                proposal.model, peer_review_prompt, None
            )

            refined.append(Proposal(
                model=proposal.model,
                content=refined_resp.content,
                confidence=min(proposal.confidence + 0.1, 1.0),
                round=round_num
            ))

        return refined

    async def _aggregate_proposals(self, query: str,
                                   proposals: List[Proposal],
                                   context: Dict) -> str:
        """Aggregator model synthesizes final decision"""

        aggregation_prompt = f"""Synthesize these expert proposals into a final decision:

Query: {query}
Context: {context}

Expert proposals:
{chr(10).join(f"{i+1}. {p.model}: {p.content}" for i, p in enumerate(proposals))}

Provide:
1. Final decision with rationale
2. Key points of agreement
3. Remaining uncertainties
4. Confidence level (0-1)"""

        result = await self.coordinator._execute_with_model(
            self.aggregator, aggregation_prompt, None
        )

        return result.content
```

**Success Criteria:**
- MoA produces better decisions than single model (measured via validation)
- Consensus score increases across rounds
- Critical material selection uses MoA with Q4, F16, and optionally GPT-4
- Debate history stored for analysis

---

### Phase 4: Quality Metrics & Stopping Criteria (Week 6-7)

**Goal:** Implement RAGAS evaluation, confidence scoring, and saturation detection

#### 4.1 RAGAS Integration

**Files to Create:**
- `services/brain/src/brain/research/quality/ragas_metrics.py` - RAGAS wrapper
- `services/brain/src/brain/research/quality/confidence.py` - Confidence scoring

**Dependencies:**
```python
# Add to pyproject.toml
"ragas>=0.1.0",
"datasets>=2.14",
```

**Implementation:**
```python
from ragas import evaluate
from ragas.metrics import Faithfulness, AnswerRelevancy, ContextPrecision, ContextRecall
from datasets import Dataset

class RAGASEvaluator:
    def __init__(self):
        self.metrics = [
            Faithfulness(),
            AnswerRelevancy(),
            ContextPrecision(),
            ContextRecall()
        ]

        self.thresholds = {
            "faithfulness": 0.85,
            "answer_relevancy": 0.75,
            "context_precision": 0.70,
            "context_recall": 0.65
        }

    async def evaluate_response(self,
                               question: str,
                               answer: str,
                               contexts: List[str],
                               ground_truth: Optional[str] = None) -> RAGASResult:
        """Evaluate a single research response"""

        data = {
            "question": [question],
            "answer": [answer],
            "contexts": [contexts],
            "ground_truth": [ground_truth] if ground_truth else [answer]  # Fallback
        }

        dataset = Dataset.from_dict(data)

        try:
            result = evaluate(dataset=dataset, metrics=self.metrics)

            scores = {
                "faithfulness": result["faithfulness"],
                "answer_relevancy": result["answer_relevancy"],
                "context_precision": result["context_precision"],
                "context_recall": result["context_recall"]
            }

            # Check thresholds
            passed = all(
                scores[metric] >= threshold
                for metric, threshold in self.thresholds.items()
            )

            return RAGASResult(
                scores=scores,
                passed=passed,
                overall_score=sum(scores.values()) / len(scores),
                failing_metrics=[
                    metric for metric, score in scores.items()
                    if score < self.thresholds[metric]
                ]
            )
        except Exception as e:
            logger.error(f"RAGAS evaluation failed: {e}")
            return RAGASResult(
                scores={},
                passed=False,
                overall_score=0.0,
                error=str(e)
            )

    async def evaluate_session(self, session_id: str) -> SessionQualityReport:
        """Evaluate entire research session"""

        # Fetch all findings from session
        findings = await db.fetch_research_findings(session_id)

        results = []
        for finding in findings:
            result = await self.evaluate_response(
                question=finding.query,
                answer=finding.content,
                contexts=[s['content'] for s in finding.sources]
            )
            results.append(result)

        avg_scores = {
            metric: sum(r.scores.get(metric, 0) for r in results) / len(results)
            for metric in self.thresholds.keys()
        }

        return SessionQualityReport(
            session_id=session_id,
            findings_evaluated=len(results),
            average_scores=avg_scores,
            passed_findings=sum(1 for r in results if r.passed),
            overall_quality=sum(avg_scores.values()) / len(avg_scores)
        )
```

**Multi-Factor Confidence Scoring:**
```python
class ConfidenceScorer:
    def __init__(self):
        self.weights = {
            'source_quality': 0.25,
            'consensus': 0.25,
            'recency': 0.15,
            'evidence_strength': 0.20,
            'verification': 0.15
        }

    def calculate_confidence(self, finding: ResearchFinding) -> ConfidenceScore:
        """Calculate multi-factor confidence score"""

        source_quality = self._calculate_source_quality(finding.sources)
        consensus = self._calculate_consensus(finding.claims)
        recency = self._calculate_recency(finding.sources)
        evidence_strength = self._calculate_evidence_strength(finding.sources)
        verification = self._calculate_verification(finding.claims, finding.sources)

        overall = (
            self.weights['source_quality'] * source_quality +
            self.weights['consensus'] * consensus +
            self.weights['recency'] * recency +
            self.weights['evidence_strength'] * evidence_strength +
            self.weights['verification'] * verification
        )

        return ConfidenceScore(
            overall=overall,
            source_quality=source_quality,
            consensus=consensus,
            recency=recency,
            evidence_strength=evidence_strength,
            verification=verification,
            recommendation=self._make_recommendation(overall)
        )

    def _calculate_source_quality(self, sources: List[Dict]) -> float:
        """Evaluate source quality (peer review, citations, authority)"""
        if not sources:
            return 0.0

        scores = []
        for source in sources:
            score = 0.0

            # Peer reviewed
            if source.get('peer_reviewed'):
                score += 0.4

            # Citation count
            citations = source.get('citations', 0)
            score += min(math.log10(citations + 1) / 4, 0.3)

            # Author expertise
            if source.get('author_h_index', 0) > 10:
                score += 0.2

            # Domain authority
            domain = source.get('domain', '')
            if domain.endswith(('.edu', '.gov')):
                score += 0.1

            scores.append(min(score, 1.0))

        return sum(scores) / len(scores)

    def _calculate_consensus(self, claims: List[Dict]) -> float:
        """Measure agreement across sources"""
        if not claims:
            return 0.5  # Neutral

        supporting = sum(1 for c in claims if c.get('support') == 'strong')
        conflicting = sum(1 for c in claims if c.get('support') == 'contradicts')

        return (supporting - conflicting + len(claims)) / (2 * len(claims))

    def _calculate_recency(self, sources: List[Dict]) -> float:
        """Exponential decay based on publication date"""
        if not sources:
            return 0.0

        current_year = datetime.now().year
        scores = []

        for source in sources:
            pub_year = source.get('publication_year', current_year - 10)
            age = current_year - pub_year
            score = math.exp(-age / 5)  # Half-life of 5 years
            scores.append(score)

        return sum(scores) / len(scores)

    def _calculate_evidence_strength(self, sources: List[Dict]) -> float:
        """Academic evidence hierarchy"""
        hierarchy = {
            'meta-analysis': 1.0,
            'systematic_review': 0.9,
            'rct': 0.8,
            'cohort_study': 0.6,
            'case_control': 0.5,
            'case_series': 0.4,
            'expert_opinion': 0.3,
            'manufacturer_data': 0.5,
            'user_review': 0.2,
            'unknown': 0.3
        }

        if not sources:
            return 0.0

        scores = [hierarchy.get(s.get('evidence_type', 'unknown'), 0.3) for s in sources]
        return sum(scores) / len(scores)

    def _calculate_verification(self, claims: List[Dict], sources: List[Dict]) -> float:
        """Cross-source consistency check"""
        if not claims:
            return 1.0

        verified_count = 0
        for claim in claims:
            # Count how many sources support this claim
            support_count = sum(
                1 for s in sources
                if claim['text'].lower() in s.get('content', '').lower()
            )

            if support_count >= 2:  # At least 2 sources
                verified_count += 1

        return verified_count / len(claims)

    def _make_recommendation(self, overall_score: float) -> str:
        """Recommend action based on confidence"""
        if overall_score >= 0.8:
            return "HIGH_CONFIDENCE"
        elif overall_score >= 0.6:
            return "MEDIUM_CONFIDENCE"
        else:
            return "LOW_CONFIDENCE"
```

**Success Criteria:**
- RAGAS faithfulness >0.85 for high-stakes findings
- Answer relevancy >0.75 across all findings
- Confidence scores differentiate high/medium/low quality
- Multi-factor scoring catches low-quality sources

---

#### 4.2 Saturation Detection & Stopping Criteria

**Files to Create:**
- `services/brain/src/brain/research/quality/saturation.py` - Saturation detector
- `services/brain/src/brain/research/quality/gaps.py` - Knowledge gap detection
- `services/brain/src/brain/research/quality/monitor.py` - Real-time quality monitoring

**Saturation Detection:**
```python
class SaturationDetector:
    def __init__(self,
                 base_size: int = 10,
                 run_length: int = 3,
                 new_info_threshold: float = 0.05):
        self.base_size = base_size
        self.run_length = run_length
        self.new_info_threshold = new_info_threshold

        self.consecutive_low_novelty = 0
        self.all_themes = set()
        self.sources_processed = 0
        self.novelty_history = []

    async def process_source(self, source: Dict, extracted_themes: Set[str]) -> SaturationCheck:
        """Process a new source and check for saturation"""

        new_themes = extracted_themes - self.all_themes
        novelty_rate = len(new_themes) / len(extracted_themes) if extracted_themes else 0.0

        self.novelty_history.append(novelty_rate)

        if novelty_rate < self.new_info_threshold:
            self.consecutive_low_novelty += 1
        else:
            self.consecutive_low_novelty = 0

        self.all_themes.update(extracted_themes)
        self.sources_processed += 1

        # Check saturation conditions
        saturated = (
            self.sources_processed >= self.base_size and
            self.consecutive_low_novelty >= self.run_length
        )

        return SaturationCheck(
            saturated=saturated,
            sources_processed=self.sources_processed,
            unique_themes=len(self.all_themes),
            novelty_rate=novelty_rate,
            consecutive_low_novelty=self.consecutive_low_novelty,
            recommendation="STOP" if saturated else "CONTINUE",
            confidence="HIGH" if saturated else "MEDIUM"
        )

    def reset(self):
        """Reset detector for new research session"""
        self.consecutive_low_novelty = 0
        self.all_themes = set()
        self.sources_processed = 0
        self.novelty_history = []
```

**Knowledge Gap Detection:**
```python
class KnowledgeGapDetector:
    def __init__(self, required_topics: Set[str]):
        self.required_topics = required_topics
        self.covered_topics = set()
        self.topic_depth = {}  # topic -> source count
        self.contradictions = []

    def update(self, topics_found: Set[str], source: Dict):
        """Update coverage tracking"""
        self.covered_topics.update(topics_found)

        for topic in topics_found:
            self.topic_depth[topic] = self.topic_depth.get(topic, 0) + 1

    def detect_coverage_gaps(self) -> GapAnalysis:
        """Identify missing topics"""
        missing = self.required_topics - self.covered_topics
        severity = len(missing) / len(self.required_topics) if self.required_topics else 0.0

        return GapAnalysis(
            gap_type="COVERAGE",
            severity=severity,
            missing_topics=list(missing),
            action_required=severity > 0.3
        )

    def detect_depth_gaps(self, min_sources: int = 3) -> GapAnalysis:
        """Identify shallow topics"""
        shallow = {
            topic: count
            for topic, count in self.topic_depth.items()
            if count < min_sources
        }

        severity = len(shallow) / len(self.covered_topics) if self.covered_topics else 0.0

        return GapAnalysis(
            gap_type="DEPTH",
            severity=severity,
            shallow_topics=shallow,
            action_required=severity > 0.4
        )

    def detect_consistency_gaps(self) -> GapAnalysis:
        """Identify contradictions"""
        severity = len(self.contradictions) / max(len(self.covered_topics), 1)

        return GapAnalysis(
            gap_type="CONSISTENCY",
            severity=severity,
            contradictions=self.contradictions,
            action_required=len(self.contradictions) > 3
        )

    def compute_completeness(self) -> CompletenessScore:
        """Overall completeness assessment"""
        coverage_gap = self.detect_coverage_gaps()
        depth_gap = self.detect_depth_gaps()
        consistency_gap = self.detect_consistency_gaps()

        coverage_score = 1.0 - coverage_gap.severity
        depth_score = 1.0 - depth_gap.severity
        consistency_score = 1.0 - consistency_gap.severity

        overall = (coverage_score + depth_score + consistency_score) / 3

        return CompletenessScore(
            overall_score=overall,
            coverage=coverage_score,
            depth=depth_score,
            consistency=consistency_score,
            ready_to_proceed=overall >= 0.7,
            gaps=[coverage_gap, depth_gap, consistency_gap]
        )
```

**Real-Time Quality Monitor:**
```python
class ResearchQualityMonitor:
    def __init__(self, session_id: str, db_connection):
        self.session_id = session_id
        self.db = db_connection

        self.ragas_evaluator = RAGASEvaluator()
        self.confidence_scorer = ConfidenceScorer()
        self.saturation_detector = SaturationDetector()
        self.gap_detector = None  # Initialized when required_topics known

        self.thresholds = {
            'min_confidence': 0.6,
            'min_coverage': 0.7,
            'min_depth': 0.5,
            'min_faithfulness': 0.85,
            'max_contradictions': 3
        }

    async def process_finding(self,
                             finding: ResearchFinding,
                             extracted_themes: Set[str]) -> ContinuationDecision:
        """Process new finding and decide whether to continue research"""

        # Evaluate quality
        ragas_result = await self.ragas_evaluator.evaluate_response(
            question=finding.query,
            answer=finding.content,
            contexts=[s['content'] for s in finding.sources]
        )

        # Calculate confidence
        confidence = self.confidence_scorer.calculate_confidence(finding)

        # Check saturation
        saturation = await self.saturation_detector.process_source(
            finding.sources[0] if finding.sources else {},
            extracted_themes
        )

        # Check gaps (if detector initialized)
        completeness = None
        if self.gap_detector:
            self.gap_detector.update(extracted_themes, finding.sources[0] if finding.sources else {})
            completeness = self.gap_detector.compute_completeness()

        # Store metrics
        await self._log_metrics(ragas_result, confidence, saturation, completeness)

        # Make decision
        decision = self._make_stopping_decision(
            ragas_result, confidence, saturation, completeness
        )

        return decision

    def _make_stopping_decision(self,
                                ragas: RAGASResult,
                                confidence: ConfidenceScore,
                                saturation: SaturationCheck,
                                completeness: Optional[CompletenessScore]) -> ContinuationDecision:
        """Decide whether to continue or stop research"""

        # Stopping criteria:
        # 1. Saturation reached AND
        # 2. Completeness sufficient AND
        # 3. Quality acceptable

        quality_ok = (
            ragas.scores.get('faithfulness', 0) >= self.thresholds['min_faithfulness'] and
            confidence.overall >= self.thresholds['min_confidence']
        )

        saturation_reached = saturation.saturated

        completeness_ok = True
        if completeness:
            completeness_ok = completeness.overall_score >= self.thresholds['min_coverage']

        should_stop = saturation_reached and completeness_ok and quality_ok

        reasons = []
        if saturation_reached:
            reasons.append(f"Saturation reached ({saturation.consecutive_low_novelty} consecutive low-novelty sources)")
        if completeness_ok:
            reasons.append(f"Completeness sufficient ({completeness.overall_score:.2f})")
        if quality_ok:
            reasons.append(f"Quality acceptable (faithfulness={ragas.scores.get('faithfulness', 0):.2f}, confidence={confidence.overall:.2f})")

        if not should_stop:
            if not saturation_reached:
                reasons.append("Still discovering new information")
            if not completeness_ok:
                reasons.append(f"Gaps remain (completeness={completeness.overall_score:.2f})")
            if not quality_ok:
                reasons.append("Quality below thresholds")

        return ContinuationDecision(
            continue_research=not should_stop,
            confidence="HIGH" if should_stop else "MEDIUM",
            reasons=reasons,
            metrics={
                'ragas': ragas.scores,
                'confidence': confidence.overall,
                'saturation': saturation.novelty_rate,
                'completeness': completeness.overall_score if completeness else None
            }
        )

    async def _log_metrics(self, ragas, confidence, saturation, completeness):
        """Store metrics in database"""
        await self.db.execute("""
            INSERT INTO quality_metrics (
                session_id, metric_type, metric_value, calculated_at, metadata
            ) VALUES ($1, $2, $3, NOW(), $4)
        """,
            self.session_id,
            'ragas_faithfulness',
            ragas.scores.get('faithfulness', 0),
            json.dumps({'all_scores': ragas.scores})
        )

        await self.db.execute("""
            INSERT INTO confidence_scores (
                session_id, overall_confidence, source_quality_score,
                consensus_score, recency_score, evidence_strength_score,
                verification_score, created_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, NOW())
        """,
            self.session_id,
            confidence.overall,
            confidence.source_quality,
            confidence.consensus,
            confidence.recency,
            confidence.evidence_strength,
            confidence.verification
        )

        await self.db.execute("""
            INSERT INTO saturation_tracking (
                session_id, sources_processed, unique_themes_count,
                novelty_rate, consecutive_low_novelty, saturated, checked_at
            ) VALUES ($1, $2, $3, $4, $5, $6, NOW())
        """,
            self.session_id,
            saturation.sources_processed,
            saturation.unique_themes,
            saturation.novelty_rate,
            saturation.consecutive_low_novelty,
            saturation.saturated
        )
```

**Database Schema:**
```sql
CREATE TABLE quality_metrics (
    metric_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id TEXT REFERENCES research_sessions(session_id) ON DELETE CASCADE,
    metric_type VARCHAR(50),
    metric_value FLOAT,
    calculated_at TIMESTAMP DEFAULT NOW(),
    metadata JSONB
);

CREATE TABLE knowledge_gaps (
    gap_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id TEXT REFERENCES research_sessions(session_id) ON DELETE CASCADE,
    gap_type VARCHAR(50),
    severity FLOAT,
    description TEXT,
    resolved BOOLEAN DEFAULT FALSE,
    identified_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE saturation_tracking (
    tracking_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id TEXT REFERENCES research_sessions(session_id) ON DELETE CASCADE,
    sources_processed INTEGER,
    unique_themes_count INTEGER,
    novelty_rate FLOAT,
    consecutive_low_novelty INTEGER,
    saturated BOOLEAN,
    checked_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE confidence_scores (
    score_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id TEXT REFERENCES research_sessions(session_id) ON DELETE CASCADE,
    overall_confidence FLOAT,
    source_quality_score FLOAT,
    consensus_score FLOAT,
    recency_score FLOAT,
    evidence_strength_score FLOAT,
    verification_score FLOAT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_quality_metrics_session ON quality_metrics(session_id);
CREATE INDEX idx_knowledge_gaps_session ON knowledge_gaps(session_id);
CREATE INDEX idx_saturation_tracking_session ON saturation_tracking(session_id);
CREATE INDEX idx_confidence_scores_session ON confidence_scores(session_id);
```

**Success Criteria:**
- Saturation detector stops after 10-15 sources when novelty < 5% for 3+ consecutive sources
- Gap detector identifies missing topics and shallow coverage
- Quality monitor logs metrics to database every finding
- Stopping criteria prevent both premature termination and wasteful over-research

---

### Phase 5: Integration & End-to-End Workflow (Week 8)

**Goal:** Connect all four systems into cohesive autonomous research workflow

#### 5.1 Autonomous Research LangGraph

**Files to Create:**
- `services/brain/src/brain/research/graph/autonomous_graph.py` - Main research graph
- `services/brain/src/brain/research/graph/nodes.py` - Graph node implementations
- `services/brain/src/brain/research/graph/state.py` - Research state definition

**Research State:**
```python
from typing import TypedDict, List, Annotated
import operator

class ResearchState(TypedDict):
    # Input
    session_id: str
    user_id: str
    query: str
    required_topics: List[str]

    # Research progress
    hypotheses: Annotated[List[str], operator.add]
    findings: Annotated[List[Dict], operator.add]
    sources: Annotated[List[Dict], operator.add]
    themes: Annotated[Set[str], operator.or_]

    # Quality tracking
    completeness_score: float
    confidence_score: float
    saturation_status: Dict
    quality_metrics: Dict

    # Control flow
    current_strategy: str
    iteration: int
    should_continue: bool

    # Output
    final_synthesis: str
    recommendations: List[Dict]
```

**Graph Construction:**
```python
def build_autonomous_research_graph(checkpointer) -> StateGraph:
    """Build complete autonomous research LangGraph with checkpointing"""

    graph = StateGraph(ResearchState)

    # Nodes
    graph.add_node("initialize", initialize_research)
    graph.add_node("generate_hypotheses", generate_hypotheses_node)
    graph.add_node("select_strategy", select_research_strategy)
    graph.add_node("execute_research", execute_research_node)
    graph.add_node("evaluate_quality", evaluate_quality_node)
    graph.add_node("check_stopping_criteria", check_stopping_node)
    graph.add_node("synthesize_findings", synthesize_findings_node)
    graph.add_node("finalize", finalize_research)

    # Entry point
    graph.set_entry_point("initialize")

    # Edges
    graph.add_edge("initialize", "generate_hypotheses")
    graph.add_edge("generate_hypotheses", "select_strategy")
    graph.add_edge("select_strategy", "execute_research")
    graph.add_edge("execute_research", "evaluate_quality")
    graph.add_edge("evaluate_quality", "check_stopping_criteria")

    # Conditional: continue or stop
    graph.add_conditional_edges(
        "check_stopping_criteria",
        lambda s: "synthesize" if not s["should_continue"] else "execute_research",
        {
            "synthesize": "synthesize_findings",
            "execute_research": "execute_research"
        }
    )

    graph.add_edge("synthesize_findings", "finalize")
    graph.add_edge("finalize", END)

    # Compile with checkpointing
    return graph.compile(checkpointer=checkpointer)
```

**Node Implementations:**
```python
async def initialize_research(state: ResearchState) -> ResearchState:
    """Initialize research session"""
    logger.info(f"Initializing research session {state['session_id']}")

    # Parse query to extract required topics
    required_topics = await extract_required_topics(state['query'])

    return {
        **state,
        "required_topics": required_topics,
        "iteration": 0,
        "should_continue": True,
        "hypotheses": [],
        "findings": [],
        "sources": [],
        "themes": set()
    }

async def generate_hypotheses_node(state: ResearchState) -> ResearchState:
    """Generate research hypotheses/approaches"""

    coordinator = KITTModelCoordinator()

    prompt = f"""Generate 5 research hypotheses/approaches for:
{state['query']}

Return as JSON list of strings."""

    result = await coordinator.coordinate(prompt, task_type="reasoning", max_cost=0.0)
    hypotheses = json.loads(result.content)

    logger.info(f"Generated {len(hypotheses)} hypotheses")

    return {**state, "hypotheses": hypotheses}

async def select_research_strategy(state: ResearchState) -> ResearchState:
    """Select best research strategy for current iteration"""

    orchestrator = MultiStrategyOrchestrator(tools=get_research_tools())

    # Auto-select based on query and current progress
    if state['iteration'] == 0:
        strategy = "breadth_first"  # Start with parallel exploration
    elif state['completeness_score'] < 0.5:
        strategy = "task_decomposition"  # Fill gaps systematically
    else:
        strategy = "depth_first"  # Refine and validate

    logger.info(f"Selected strategy: {strategy} for iteration {state['iteration']}")

    return {**state, "current_strategy": strategy}

async def execute_research_node(state: ResearchState) -> ResearchState:
    """Execute research using selected strategy"""

    orchestrator = MultiStrategyOrchestrator(tools=get_research_tools())

    # Execute research
    result = await orchestrator.execute(
        query=state['query'],
        strategy=state['current_strategy']
    )

    # Extract findings and sources
    new_findings = result.get('findings', [])
    new_sources = result.get('sources', [])
    new_themes = set(result.get('themes', []))

    logger.info(f"Research iteration {state['iteration']} found {len(new_findings)} findings")

    return {
        **state,
        "findings": state.get('findings', []) + new_findings,
        "sources": state.get('sources', []) + new_sources,
        "themes": state.get('themes', set()) | new_themes,
        "iteration": state['iteration'] + 1
    }

async def evaluate_quality_node(state: ResearchState) -> ResearchState:
    """Evaluate research quality and update metrics"""

    monitor = ResearchQualityMonitor(state['session_id'], db_connection)

    # Initialize gap detector if not done
    if not monitor.gap_detector:
        monitor.gap_detector = KnowledgeGapDetector(set(state['required_topics']))

    # Process latest finding
    if state['findings']:
        latest_finding = state['findings'][-1]
        decision = await monitor.process_finding(
            latest_finding,
            state['themes']
        )

        return {
            **state,
            "completeness_score": decision.metrics.get('completeness', 0.0),
            "confidence_score": decision.metrics.get('confidence', 0.0),
            "saturation_status": {
                'rate': decision.metrics.get('saturation', 0.0),
                'saturated': decision.metrics.get('saturation', 0.0) < 0.05
            },
            "quality_metrics": decision.metrics
        }

    return state

async def check_stopping_node(state: ResearchState) -> ResearchState:
    """Check if research should continue or stop"""

    # Stopping criteria
    max_iterations = 15

    should_stop = (
        state['iteration'] >= max_iterations or
        (
            state.get('saturation_status', {}).get('saturated', False) and
            state.get('completeness_score', 0.0) >= 0.7 and
            state.get('confidence_score', 0.0) >= 0.6
        )
    )

    logger.info(f"Iteration {state['iteration']}: should_stop={should_stop}")
    logger.info(f"  Completeness: {state.get('completeness_score', 0.0):.2f}")
    logger.info(f"  Confidence: {state.get('confidence_score', 0.0):.2f}")
    logger.info(f"  Saturation: {state.get('saturation_status', {})}")

    return {**state, "should_continue": not should_stop}

async def synthesize_findings_node(state: ResearchState) -> ResearchState:
    """Synthesize all findings using F16"""

    coordinator = KITTModelCoordinator()

    # Use MoA debate for final synthesis
    debate = MixtureOfAgentsDebate(
        proposer_models=["llama-3.1-8b-q4", "llama-3.1-70b-f16"],
        aggregator_model="llama-3.1-70b-f16"
    )

    synthesis_query = f"""Synthesize research findings for:
{state['query']}

Findings:
{json.dumps(state['findings'], indent=2)}

Provide:
1. Comprehensive answer
2. Key insights
3. Recommendations
4. Confidence assessment
5. Remaining uncertainties"""

    result = await debate.debate(synthesis_query, context=state, rounds=2)

    return {
        **state,
        "final_synthesis": result.decision,
        "recommendations": extract_recommendations(result.decision)
    }

async def finalize_research(state: ResearchState) -> ResearchState:
    """Finalize research session"""

    # Update session status in database
    await db.execute("""
        UPDATE research_sessions
        SET status = 'completed', updated_at = NOW()
        WHERE session_id = $1
    """, state['session_id'])

    logger.info(f"Research session {state['session_id']} completed")
    logger.info(f"  Iterations: {state['iteration']}")
    logger.info(f"  Findings: {len(state['findings'])}")
    logger.info(f"  Sources: {len(state['sources'])}")
    logger.info(f"  Final completeness: {state['completeness_score']:.2f}")

    return state
```

**Success Criteria:**
- Graph executes end-to-end for material research query
- Checkpoints save after each node execution
- Crash and resume works at any point
- Stopping criteria trigger correctly
- Final synthesis combines all findings coherently

---

#### 5.2 Integration with Existing Brain Service

**Files to Modify:**
- `services/brain/src/brain/main.py` - Add research routes, lifespan setup
- `services/brain/src/brain/orchestrator.py` - Add autonomous research mode

**Main.py Updates:**
```python
from brain.research.routes import router as research_router
from brain.research.checkpoint import init_checkpointer
from brain.research.graph.autonomous_graph import build_autonomous_research_graph

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Existing setup...

    # Initialize research infrastructure
    app.state.pg_pool = ConnectionPool(
        conninfo=os.getenv("DATABASE_URL"),
        max_size=20,
        kwargs={"autocommit": True, "row_factory": dict_row}
    )

    app.state.checkpointer = init_checkpointer(app.state.pg_pool)
    app.state.research_graph = build_autonomous_research_graph(app.state.checkpointer)
    app.state.session_manager = ResearchSessionManager(
        app.state.research_graph,
        app.state.checkpointer,
        app.state.pg_pool
    )

    yield

    # Cleanup
    await app.state.pg_pool.close()

app = FastAPI(lifespan=lifespan)

# Add research routes
app.include_router(research_router)
```

**Orchestrator Updates:**
```python
async def generate_response(self, conversation_id: str, use_agent: bool = None):
    """Enhanced orchestrator with autonomous research mode"""

    # Existing logic...

    # Check if query requires long-form autonomous research
    if self._should_use_autonomous_research(latest_message):
        return await self._execute_autonomous_research(
            conversation_id,
            latest_message
        )

    # Existing routing logic...

def _should_use_autonomous_research(self, message: str) -> bool:
    """Determine if query needs autonomous research"""

    triggers = [
        "research",
        "investigate",
        "find alternatives",
        "compare options",
        "evaluate materials",
        "comprehensive analysis"
    ]

    return any(trigger in message.lower() for trigger in triggers)

async def _execute_autonomous_research(self, conversation_id: str, query: str) -> Dict:
    """Execute autonomous research session"""

    session_id = await self.session_manager.create_session(
        user_id=conversation_id,
        query=query,
        config={"autonomous": True}
    )

    # Run in background, return session info
    asyncio.create_task(self.session_manager.run_session(session_id))

    return {
        "output": f"Started autonomous research session {session_id}\n\nMonitor progress at: /api/research/sessions/{session_id}/stream",
        "session_id": session_id,
        "type": "autonomous_research"
    }
```

**Success Criteria:**
- Research sessions launch from normal queries
- Integration doesn't break existing functionality
- Sessions visible in conversation history
- Progress streaming works from web UI

---

### Phase 6: Testing, Monitoring & Documentation (Week 9-10)

#### 6.1 Comprehensive Testing

**Test Files to Create:**
- `services/brain/tests/research/test_checkpoint_recovery.py`
- `services/brain/tests/research/test_wave_orchestration.py`
- `services/brain/tests/research/test_model_coordination.py`
- `services/brain/tests/research/test_quality_metrics.py`
- `services/brain/tests/research/test_end_to_end.py`

**Key Test Scenarios:**
1. **Checkpoint Recovery:** Create session → kill process → resume → verify state
2. **Wave Execution:** Define 10 tools with dependencies → verify parallel execution
3. **Model Routing:** Send 100 queries → verify Q4/F16/external distribution matches expectations
4. **Saturation Detection:** Feed incremental sources → verify stops at correct threshold
5. **End-to-End:** Material research query → full autonomous execution → validate output quality

**Example E2E Test:**
```python
async def test_autonomous_material_research():
    """Test complete autonomous research workflow"""

    query = """Research sustainable 3D printing materials for consumer products.
    Evaluate PLA, PETG, and recycled ABS. Compare cost, environmental impact,
    and mechanical properties. Recommend best option."""

    # Create session
    session_id = await session_manager.create_session(
        user_id="test_user",
        query=query,
        config={"max_iterations": 10}
    )

    # Execute research
    result = await session_manager.run_session(session_id)

    # Verify outputs
    assert result["status"] == "completed"
    assert len(result["findings"]) >= 5
    assert result["completeness_score"] >= 0.7
    assert result["confidence_score"] >= 0.6

    # Verify database state
    session = await db.fetch_one(
        "SELECT * FROM research_sessions WHERE session_id = $1",
        session_id
    )
    assert session["status"] == "completed"

    # Verify quality metrics logged
    metrics = await db.fetch_all(
        "SELECT * FROM quality_metrics WHERE session_id = $1",
        session_id
    )
    assert len(metrics) >= 5  # At least 5 quality checks

    # Verify final synthesis exists
    assert "final_synthesis" in result
    assert len(result["final_synthesis"]) > 500  # Substantial answer
```

---

#### 6.2 Monitoring & Observability

**Grafana Dashboard:**
Create dashboard showing:
- Active research sessions
- Average session duration
- Q4/F16/external call distribution
- Quality metric trends (faithfulness, confidence, completeness)
- Saturation detection effectiveness
- Checkpoint recovery success rate
- Cost savings vs baseline

**Prometheus Metrics:**
```python
from prometheus_client import Counter, Histogram, Gauge

research_sessions_total = Counter(
    'research_sessions_total',
    'Total research sessions created',
    ['user_id', 'status']
)

research_duration_seconds = Histogram(
    'research_duration_seconds',
    'Research session duration',
    buckets=[60, 300, 900, 1800, 3600, 7200, 14400]
)

research_findings_total = Counter(
    'research_findings_total',
    'Total findings generated',
    ['session_id', 'finding_type']
)

research_quality_score = Gauge(
    'research_quality_score',
    'Current quality scores',
    ['session_id', 'metric_type']
)

model_calls_total = Counter(
    'model_calls_total',
    'Model API calls',
    ['model', 'task_type', 'success']
)

research_cost_dollars = Counter(
    'research_cost_dollars',
    'Research cost in USD',
    ['session_id', 'model']
)
```

---

#### 6.3 Documentation

**Files to Create:**
- `docs/autonomous-research/README.md` - Overview and architecture
- `docs/autonomous-research/API.md` - API documentation
- `docs/autonomous-research/CONFIGURATION.md` - Configuration guide
- `docs/autonomous-research/TROUBLESHOOTING.md` - Common issues
- `docs/autonomous-research/EXAMPLES.md` - Usage examples

**README Outline:**
```markdown
# KITT Autonomous Research System

## Overview
Four-system architecture enabling 2-6 hour autonomous research with fault tolerance.

## Architecture
- System 1: State Management (LangGraph + PostgreSQL)
- System 2: Tool Orchestration (Wave execution + validation)
- System 3: Model Coordination (Q4/F16 routing)
- System 4: Quality Metrics (RAGAS + saturation)

## Quick Start
[Installation, configuration, first research session]

## API Reference
[Link to API.md]

## Configuration
[Link to CONFIGURATION.md]

## Monitoring
[Grafana dashboards, metrics, alerts]

## Troubleshooting
[Link to TROUBLESHOOTING.md]
```

---

## Deployment Plan

### Environment Variables
```bash
# PostgreSQL
DATABASE_URL=postgresql://user:pass@localhost:5432/kitt

# LLM Endpoints
LLAMACPP_Q4_ENDPOINT=http://localhost:8001/v1/chat/completions
LLAMACPP_F16_ENDPOINT=http://localhost:8002/v1/chat/completions
OPENAI_API_KEY=sk-...

# Research Configuration
RESEARCH_MAX_ITERATIONS=15
RESEARCH_BASE_SIZE=10
RESEARCH_SATURATION_THRESHOLD=0.05
RESEARCH_MIN_CONFIDENCE=0.6
RESEARCH_MIN_COMPLETENESS=0.7

# Model Routing
MODEL_ROUTING_ENABLED=true
MODEL_Q4_WEIGHT=0.8
MODEL_F16_WEIGHT=0.15
MODEL_EXTERNAL_WEIGHT=0.05
```

### Database Migration
```bash
cd services/brain
psql $DATABASE_URL -f migrations/006_research_checkpoints.sql
```

### Service Start
```bash
# Start llama.cpp servers
./scripts/start_llamacpp_q4.sh
./scripts/start_llamacpp_f16.sh

# Start brain service with research
cd services/brain
uv run uvicorn brain.main:app --reload --port 8080
```

---

## Success Metrics

### Phase 1 (State Management)
- ✅ Sessions persist across crashes
- ✅ Recovery works within 5 seconds
- ✅ Multiple concurrent sessions isolated

### Phase 2 (Tool Orchestration)
- ✅ Wave execution achieves 2-3x speedup vs sequential
- ✅ Validation catches >90% of hallucinations
- ✅ Strategy selection improves efficiency by 30%+

### Phase 3 (Model Coordination)
- ✅ Q4 handles 70-80% of queries
- ✅ Cost reduction >85% vs all-GPT-4
- ✅ Quality maintained at 90-95% of GPT-4 level

### Phase 4 (Quality Metrics)
- ✅ RAGAS faithfulness >0.85 for critical findings
- ✅ Saturation detection stops at correct point
- ✅ Completeness score correlates with human judgment

### Phase 5 (Integration)
- ✅ End-to-end material research completes in <2 hours
- ✅ Final synthesis coherent and actionable
- ✅ Zero regressions in existing functionality

### Phase 6 (Production)
- ✅ Uptime >99.5%
- ✅ Mean recovery time <10 seconds
- ✅ User satisfaction >4.5/5

---

## Risk Mitigation

### Technical Risks
1. **Checkpoint bloat:** Implement compression, archive old sessions
2. **Graph deadlocks:** Add timeouts, cycle detection
3. **Model availability:** Fallback chains, graceful degradation
4. **Database load:** Connection pooling, read replicas

### Operational Risks
1. **Cost overruns:** Budget alerts, rate limiting, auto-pause
2. **Quality degradation:** Continuous monitoring, A/B testing
3. **User confusion:** Clear progress indicators, examples, docs

---

## Timeline Summary

| Week | Phase | Deliverables |
|------|-------|-------------|
| 1-2 | State Management | PostgreSQL checkpointing, session lifecycle, FastAPI routes |
| 3-4 | Tool Orchestration | Wave execution, validation pipeline, multi-strategy agents |
| 5 | Model Coordination | Registry, routing, consultation loops, MoA |
| 6-7 | Quality Metrics | RAGAS, confidence scoring, saturation detection, monitoring |
| 8 | Integration | Autonomous graph, end-to-end workflow, existing service integration |
| 9-10 | Testing & Docs | Comprehensive tests, monitoring setup, documentation |

**Total Duration:** 10 weeks
**Team Size:** 1-2 developers
**Dependencies:** LangGraph, PostgreSQL, Redis, llama.cpp servers

---

## Next Steps

1. **Review this plan** with stakeholders
2. **Set up development environment** (PostgreSQL, llama.cpp, dependencies)
3. **Start Phase 1** with checkpoint infrastructure
4. **Iterate based on feedback** from each phase

---

## Appendix: File Structure

```
services/brain/
├── src/brain/research/
│   ├── __init__.py
│   ├── checkpoint.py                 # PostgresSaver setup
│   ├── session_manager.py            # Session lifecycle
│   ├── routes.py                     # FastAPI routes
│   ├── orchestration/
│   │   ├── tool_graph.py            # Dependency graph
│   │   ├── wave_executor.py         # Wave execution
│   │   └── strategy_selector.py     # Strategy routing
│   ├── validation/
│   │   ├── pipeline.py              # Validation orchestration
│   │   ├── hallucination.py         # Claim verification
│   │   └── schema.py                # Input/output validation
│   ├── agents/
│   │   ├── breadth_first.py         # Parallel exploration
│   │   ├── depth_first.py           # Iterative refinement
│   │   └── task_decomposition.py    # Hierarchical planning
│   ├── models/
│   │   ├── registry.py              # Model capabilities
│   │   ├── coordinator.py           # Routing logic
│   │   ├── consultation.py          # Validation loops
│   │   └── mixture.py               # MoA debate
│   ├── quality/
│   │   ├── ragas_metrics.py         # RAGAS wrapper
│   │   ├── confidence.py            # Confidence scoring
│   │   ├── saturation.py            # Saturation detection
│   │   ├── gaps.py                  # Gap detection
│   │   └── monitor.py               # Real-time monitoring
│   └── graph/
│       ├── autonomous_graph.py      # Main research graph
│       ├── nodes.py                 # Node implementations
│       └── state.py                 # State definitions
├── migrations/
│   └── 006_research_checkpoints.sql
├── tests/research/
│   ├── test_checkpoint_recovery.py
│   ├── test_wave_orchestration.py
│   ├── test_model_coordination.py
│   ├── test_quality_metrics.py
│   └── test_end_to_end.py
└── pyproject.toml                    # Add new dependencies
```

---

**Implementation Plan Version:** 1.0
**Last Updated:** 2025-01-16
**Status:** Ready for Implementation
