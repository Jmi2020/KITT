Based on my research into multi-agent LLM research systems and analysis of your KITT pipeline's output, I can see several critical issues that are causing shallow, low-quality research reports. Let me provide you with actionable implementation guidance.

## Critical Problems Identified in Your Current Output

Looking at your research report example, the issues are clear:

1. **Zero-confidence findings** (3 out of 5 findings have 0.00 confidence)
2. **"No results found"** placeholder content dominating output
3. **Wrong template selected** (Product Research template for an AI ethics question)
4. **No actual synthesis or analysis** - just raw search results
5. **Missing all N/A fields** that should contain actual methodology
6. **PBS Kids and Psychology videos** appearing in AI ethics research (irrelevant sources)

## Research-Backed Solutions for Multi-Agent Research Systems

Based on recent advances in multi-agent LLM systems[1][2][3], here are the most effective patterns:

### 1. **Orchestrator-Worker Pattern with Parallel Subagents** (Anthropic's Research System)

**Why it works:** Anthropic's internal evaluations show 90.2% improvement over single-agent systems by decomposing queries and running parallel subagents[1].

**Implementation for KITT:**

```python
# In services/brain/src/brain/research/graph/nodes.py

async def decompose_and_delegate_node(state: ResearchState) -> ResearchState:
    """
    Lead agent decomposes query into sub-questions and spawns parallel subagents.
    This replaces linear iteration with breadth-first exploration.
    """
    query = state.query
    
    # Use lead LLM (GPTOSS-120B or Claude Opus) to decompose
    decomposition_prompt = f"""
    Given this research question: {query}
    
    Decompose it into 3-5 independent sub-questions that:
    1. Can be researched in parallel
    2. Cover different aspects (evidence, viewpoints, methodologies, context)
    3. Are specific enough to yield concrete findings
    4. Don't overlap significantly
    
    Format as JSON array of objects with: {{"sub_question": str, "search_strategy": str, "priority": int}}
    """
    
    sub_questions = await coordinator.invoke_lead_model(decomposition_prompt)
    
    # Spawn parallel subagents (3-5 workers)
    tasks = []
    for sq in sub_questions[:5]:  # Limit to 5 parallel agents
        task = asyncio.create_task(
            run_subagent_research(
                question=sq["sub_question"],
                strategy=sq["search_strategy"],
                model="claude-sonnet-4",  # Faster model for workers
                max_tools_calls=10
            )
        )
        tasks.append(task)
    
    # Wait for all parallel research to complete
    subagent_results = await asyncio.gather(*tasks)
    
    state.sub_research_results = subagent_results
    return state

async def run_subagent_research(question: str, strategy: str, model: str, max_tools_calls: int):
    """
    Individual subagent that iteratively searches, evaluates, and refines.
    Uses extended thinking + interleaved reflection (Anthropic pattern).
    """
    findings = []
    for iteration in range(max_tools_calls):
        # Extended thinking planning
        plan = await think_and_plan(question, findings, model)
        
        # Parallel tool calls (3-5 tools simultaneously)
        tool_results = await execute_tools_parallel(plan.tool_calls)
        
        # Interleaved reflection after tool results
        reflection = await reflect_on_results(tool_results, question, findings)
        
        if reflection.is_sufficient or reflection.confidence > 0.85:
            break
            
        # Refine next query based on gaps
        question = reflection.refined_query
        findings.extend(reflection.validated_findings)
    
    return {"findings": findings, "confidence": reflection.confidence, "sources": reflection.sources}
```

### 2. **Multi-Critic Ensemble with Weighted Voting** (Medical QA Pattern)

**Why it works:** Ensemble methods show 5-65% improvement over single models by filtering hallucinations and aggregating diverse strengths[2][3].

**Implementation for KITT:**

```python
# In services/brain/src/brain/research/graph/nodes.py

async def multi_critic_synthesis_node(state: ResearchState) -> ResearchState:
    """
    Multiple LLMs critique and synthesize findings with weighted voting.
    Filters out hallucinations and low-quality findings.
    """
    subagent_results = state.sub_research_results
    
    # Define critic ensemble (3-5 models with different strengths)
    critics = [
        {"model": "MODELHERE", "weight": 0.35, "specialty": "reasoning"},
        {"model": "MODELHERE", "weight": 0.30, "specialty": "synthesis"},
        {"model": "MODELHERE", "weight": 0.20, "specialty": "fact_checking"},
        {"model": "MODELHERE", "weight": 0.15, "specialty": "domain_expertise"}
    ]
    
    # Each critic independently evaluates findings
    critic_evaluations = []
    for critic in critics:
        eval_prompt = f"""
        Evaluate these research findings for:
        1. Factual accuracy (0-1)
        2. Relevance to query (0-1)
        3. Source credibility (0-1)
        4. Evidence strength (0-1)
        
        Findings: {json.dumps(subagent_results)}
        Original query: {state.query}
        
        Return JSON with per-finding scores and overall synthesis.
        """
        evaluation = await coordinator.invoke_model(critic["model"], eval_prompt)
        critic_evaluations.append({
            "model": critic["model"],
            "weight": critic["weight"],
            "evaluation": evaluation
        })
    
    # Weighted voting with consensus threshold
    consensus_threshold = 0.65  # Tune based on precision/recall needs
    final_findings = []
    
    for finding_idx in range(len(subagent_results)):
        weighted_score = 0
        for critic_eval in critic_evaluations:
            finding_score = critic_eval["evaluation"]["findings"][finding_idx]["overall_score"]
            weighted_score += finding_score * critic_eval["weight"]
        
        if weighted_score >= consensus_threshold:
            finding = subagent_results[finding_idx]
            finding["ensemble_confidence"] = weighted_score
            final_findings.append(finding)
    
    # Lead model synthesizes validated findings
    synthesis = await synthesize_final_report(final_findings, state.query, critic_evaluations)
    
    state.final_findings = final_findings
    state.synthesis = synthesis
    return state
```

### 3. **Dynamic Template Selection with Query Classification**

**Problem:** Your system used "Product Research" template for an AI ethics question.

**Solution:** Multi-stage template selection with query analysis[4][5].

```python
# In services/brain/src/brain/research/template_selector.py

class ImprovedTemplateSelector:
    def __init__(self):
        self.templates = {
            "comparative_analysis": {
                "pattern": r"(compare|contrast|versus|vs|differences|similarities)",
                "required_sections": ["viewpoint_extraction", "evidence_comparison", "synthesis"],
                "min_sources": 8,
                "use_debate": True,
                "critic_diversity": "high"
            },
            "conflicting_viewpoints": {
                "pattern": r"(conflict|disagree|debate|controversy|opposing)",
                "required_sections": ["stakeholder_analysis", "evidence_mapping", "reconciliation"],
                "min_sources": 10,
                "use_debate": True,
                "critic_diversity": "high"
            },
            "comprehensive_review": {
                "pattern": r"(review|survey|landscape|state of|overview)",
                "required_sections": ["taxonomy", "key_findings", "gaps", "future_directions"],
                "min_sources": 12,
                "use_debate": False,
                "breadth_over_depth": True
            },
            "technical_deep_dive": {
                "pattern": r"(how does|mechanism|implementation|architecture)",
                "required_sections": ["technical_details", "examples", "limitations"],
                "min_sources": 6,
                "use_debate": False,
                "depth_over_breadth": True
            }
        }
    
    async def select_template(self, query: str, context: dict) -> ResearchTemplate:
        """
        Two-stage selection: Pattern matching + LLM verification.
        """
        # Stage 1: Pattern-based candidates
        candidates = []
        for template_name, config in self.templates.items():
            if re.search(config["pattern"], query, re.IGNORECASE):
                candidates.append(template_name)
        
        # Stage 2: LLM classifies query intent
        classification_prompt = f"""
        Classify this research query's primary intent:
        Query: {query}
        
        Candidates: {candidates}
        
        Consider:
        1. Is it asking for comparison/contrast?
        2. Does it involve conflicting information?
        3. Is it a broad survey or narrow deep-dive?
        4. What type of synthesis is needed?
        
        Return: {{"template": str, "reasoning": str, "confidence": float}}
        """
        
        classification = await coordinator.invoke_model("claude-opus-4", classification_prompt)
        
        # Get template config
        selected_template = self.templates[classification["template"]]
        
        # Dynamically adjust parameters based on query complexity
        selected_template["max_iterations"] = self._estimate_complexity(query) * 3
        selected_template["search_keywords"] = await self._extract_domain_keywords(query)
        
        return selected_template
    
    def _estimate_complexity(self, query: str) -> int:
        """Estimate query complexity (1-5) based on structure."""
        factors = {
            "multi_part": len(re.split(r"[.?!]", query)) > 1,
            "requires_synthesis": any(word in query.lower() for word in ["explain", "why", "reasons"]),
            "temporal_scope": bool(re.search(r"\d{4}|last year|recent|latest", query)),
            "requires_comparison": bool(re.search(r"top \d+|compare|versus", query))
        }
        return min(sum(factors.values()) + 1, 5)
```

### 4. **Iterative Refinement with Agent Reflection** (IMPROVE Pattern)

**Why it works:** Allows agents to evaluate quality and identify gaps before proceeding[6][1].

```python
# In services/brain/src/brain/research/graph/nodes.py

async def reflection_and_gap_analysis_node(state: ResearchState) -> ResearchState:
    """
    Agent reflects on findings quality and identifies research gaps.
    Decides whether to continue or synthesize.
    """
    current_findings = state.findings
    query = state.query
    iteration = state.iteration
    
    reflection_prompt = f"""
    Reflect on the current research progress:
    
    Query: {query}
    Findings so far: {len(current_findings)}
    Current iteration: {iteration}
    
    Evaluate:
    1. Coverage: What aspects of the query are still unaddressed? (List specific gaps)
    2. Quality: Are findings substantive or superficial? (Score 0-1 per finding)
    3. Source diversity: Are we relying too heavily on similar sources? (Identify clusters)
    4. Confidence: Can we synthesize a high-quality answer now? (Yes/No + reasoning)
    
    If gaps exist, suggest:
    - 2-3 specific refined search queries to fill gaps
    - Alternative search strategies (academic vs. news vs. primary sources)
    - Tools to use (web_search, web_fetch, arxiv, etc.)
    
    Return JSON: {{
        "coverage_score": float,
        "quality_scores": [float],
        "source_diversity": float,
        "can_synthesize": bool,
        "gaps": [str],
        "refined_queries": [str],
        "recommended_tools": [str]
    }}
    """
    
    reflection = await coordinator.invoke_lead_model(reflection_prompt)
    
    # Decision logic
    if reflection["can_synthesize"] or iteration >= state.max_iterations:
        state.should_continue = False
        state.ready_for_synthesis = True
    else:
        # Generate new search strategy based on gaps
        state.next_search_queries = reflection["refined_queries"]
        state.next_tools = reflection["recommended_tools"]
        state.should_continue = True
    
    state.reflection = reflection
    state.iteration += 1
    return state
```

### 5. **Enhanced Extraction with Structured Output**

**Problem:** Your current output has no synthesis, just raw search snippets.

**Solution:** Force structured extraction with schema validation.

```python
# In services/brain/src/brain/research/extraction.py

from pydantic import BaseModel, Field
from typing import List, Optional

class Finding(BaseModel):
    """Structured finding with provenance and confidence."""
    claim: str = Field(description="The specific claim or finding")
    evidence: str = Field(description="Supporting evidence from sources")
    source_urls: List[str] = Field(description="Direct URLs to sources")
    source_credibility: float = Field(ge=0, le=1, description="Assessed credibility")
    confidence: float = Field(ge=0, le=1, description="Confidence in this finding")
    contradictions: Optional[List[str]] = Field(default=None, description="Conflicting info found")
    context: str = Field(description="Important context or caveats")

class ResearchSynthesis(BaseModel):
    """Final structured research output."""
    executive_summary: str = Field(min_length=200, description="High-level synthesis")
    key_findings: List[Finding] = Field(min_items=3, description="Core findings")
    methodology: str = Field(description="How research was conducted")
    limitations: List[str] = Field(description="Known limitations of findings")
    confidence_overall: float = Field(ge=0, le=1, description="Overall confidence")
    contradictory_evidence: Optional[str] = Field(default=None)
    future_research: Optional[List[str]] = Field(default=None)
    sources_consulted: List[dict] = Field(description="All sources with metadata")

async def extract_structured_findings(raw_results: List[dict], query: str) -> ResearchSynthesis:
    """
    Use structured output mode to force LLM to produce valid schema.
    """
    extraction_prompt = f"""
    Synthesize these research results into structured findings:
    
    Query: {query}
    Raw results: {json.dumps(raw_results)}
    
    Requirements:
    1. Extract ONLY claims supported by evidence in the results
    2. Assign confidence based on evidence strength and source credibility
    3. Identify any contradictions or conflicting information
    4. Provide clear context and caveats
    5. Write an executive summary that directly answers the query
    
    You must return valid JSON matching the ResearchSynthesis schema.
    """
    
    # Use structured output (Claude/GPT-4 JSON mode)
    synthesis = await coordinator.invoke_with_schema(
        model="claude-opus-4",
        prompt=extraction_prompt,
        schema=ResearchSynthesis.model_json_schema(),
        temperature=0.3  # Lower temperature for factual extraction
    )
    
    # Validate against schema
    validated_synthesis = ResearchSynthesis.model_validate(synthesis)
    
    return validated_synthesis
```

### 6. **Stopping Criteria with Multi-Metric Evaluation**

**Problem:** Your system ran 10 iterations but produced mostly empty findings.

**Solution:** Implement early stopping based on multiple signals[7][8].

```python
# In services/brain/src/brain/research/metrics/stopping_criteria.py

class MultiMetricStoppingCriteria:
    def __init__(self):
        self.thresholds = {
            "min_confidence": 0.75,
            "min_coverage": 0.80,
            "min_source_diversity": 0.70,
            "min_findings": 5,
            "max_cost_usd": 2.0,
            "max_iterations": 10,
            "saturation_threshold": 0.85
        }
    
    def should_stop(self, state: ResearchState) -> tuple[bool, str]:
        """
        Multi-criteria stopping decision with explanation.
        """
        # Criterion 1: Confidence threshold reached
        if state.confidence_overall >= self.thresholds["min_confidence"]:
            return True, f"High confidence reached ({state.confidence_overall:.2f})"
        
        # Criterion 2: Saturation detected (diminishing returns)
        if self._calculate_saturation(state) >= self.thresholds["saturation_threshold"]:
            return True, f"Information saturation detected"
        
        # Criterion 3: Coverage sufficient
        if self._calculate_coverage(state) >= self.thresholds["min_coverage"]:
            if len(state.findings) >= self.thresholds["min_findings"]:
                return True, f"Sufficient coverage and findings"
        
        # Criterion 4: Budget exceeded
        if state.total_cost_usd >= self.thresholds["max_cost_usd"]:
            return True, f"Budget limit reached (${state.total_cost_usd:.4f})"
        
        # Criterion 5: Max iterations
        if state.iteration >= self.thresholds["max_iterations"]:
            return True, f"Max iterations reached ({state.iteration})"
        
        # Criterion 6: Quality stagnation (last 3 iterations added no valuable findings)
        if self._detect_stagnation(state):
            return True, "Quality stagnation detected - no valuable findings in recent iterations"
        
        return False, "Continue research"
    
    def _calculate_saturation(self, state: ResearchState) -> float:
        """
        Measure information gain saturation across recent iterations.
        """
        if len(state.iteration_history) < 3:
            return 0.0
        
        recent_findings = state.iteration_history[-3:]
        
        # Calculate semantic similarity between consecutive findings
        similarities = []
        for i in range(len(recent_findings) - 1):
            sim = self._semantic_similarity(
                recent_findings[i]["findings"],
                recent_findings[i+1]["findings"]
            )
            similarities.append(sim)
        
        return np.mean(similarities) if similarities else 0.0
    
    def _calculate_coverage(self, state: ResearchState) -> float:
        """
        Measure how well findings cover the query's aspects.
        """
        query_aspects = state.query_decomposition["aspects"]
        covered_aspects = set()
        
        for finding in state.findings:
            for aspect in query_aspects:
                if self._finding_covers_aspect(finding, aspect):
                    covered_aspects.add(aspect)
        
        return len(covered_aspects) / len(query_aspects) if query_aspects else 0.0
    
    def _detect_stagnation(self, state: ResearchState) -> bool:
        """
        Detect if recent iterations are producing low-quality findings.
        """
        if len(state.iteration_history) < 3:
            return False
        
        recent_findings = state.iteration_history[-3:]
        quality_scores = [
            np.mean([f.get("confidence", 0) for f in iteration["findings"]])
            for iteration in recent_findings
        ]
        
        # Stagnation if all recent iterations have low avg confidence
        return all(score < 0.5 for score in quality_scores)
```

## Implementation Priority Roadmap

### Phase 1: Immediate Fixes (Week 1)
1. **Fix template selection** - Implement better query classification
2. **Add reflection node** - Stop producing garbage findings
3. **Structured extraction** - Force valid output schema

### Phase 2: Parallel Architecture (Week 2-3)
4. **Implement orchestrator-worker pattern** - Decompose queries
5. **Parallel subagents** - Run 3-5 workers simultaneously
6. **Parallel tool calling** - 3-5 tools per subagent

### Phase 3: Quality Ensemble (Week 4)
7. **Multi-critic synthesis** - 3-5 model ensemble with voting
8. **Enhanced stopping criteria** - Multi-metric with saturation detection
9. **Confidence calibration** - Align confidence scores with actual quality

## Specific Code Changes

### In `services/brain/src/brain/research/graph/graph.py`

```python
# Replace linear graph with orchestrator-worker pattern
def build_research_graph() -> StateGraph:
    workflow = StateGraph(ResearchState)
    
    # Orchestrator layer (lead agent)
    workflow.add_node("analyze_query", analyze_query_node)
    workflow.add_node("select_template", improved_template_selection_node)
    workflow.add_node("decompose_query", decompose_and_delegate_node)
    
    # Worker layer (parallel subagents)
    workflow.add_node("parallel_research", run_parallel_subagents_node)
    
    # Synthesis layer (multi-critic ensemble)
    workflow.add_node("reflect_and_evaluate", reflection_and_gap_analysis_node)
    workflow.add_node("multi_critic_synthesis", multi_critic_synthesis_node)
    workflow.add_node("structure_output", structured_extraction_node)
    
    # Graph edges with conditional routing
    workflow.add_edge(START, "analyze_query")
    workflow.add_edge("analyze_query", "select_template")
    workflow.add_edge("select_template", "decompose_query")
    workflow.add_edge("decompose_query", "parallel_research")
    workflow.add_edge("parallel_research", "reflect_and_evaluate")
    
    # Conditional: continue or synthesize
    workflow.add_conditional_edges(
        "reflect_and_evaluate",
        lambda state: "synthesize" if not state.should_continue else "decompose_query",
        {
            "decompose_query": "decompose_query",  # More research needed
            "synthesize": "multi_critic_synthesis"  # Ready to synthesize
        }
    )
    
    workflow.add_edge("multi_critic_synthesis", "structure_output")
    workflow.add_edge("structure_output", END)
    
    return workflow.compile()
```

### In `services/brain/src/brain/research/models/coordinator.py`

```python
# Add ensemble coordinator
class MultiModelCoordinator:
    def __init__(self):
        self.lead_model = "claude-opus-4"  # or "gptoss-120b"
        self.worker_model = "claude-sonnet-4"
        self.critic_ensemble = [
            "claude-opus-4",
            "gpt-4-turbo",
            "gemini-1.5-pro",
            "gptoss-120b"
        ]
    
    async def invoke_parallel_workers(self, tasks: List[dict]) -> List[dict]:
        """Run multiple worker agents in parallel."""
        worker_tasks = [
            self._run_worker(task, self.worker_model)
            for task in tasks
        ]
        return await asyncio.gather(*worker_tasks)
    
    async def ensemble_critique(self, findings: List[dict], query: str) -> dict:
        """Get critiques from multiple models and aggregate."""
        critique_tasks = [
            self._critique_with_model(findings, query, model)
            for model in self.critic_ensemble
        ]
        critiques = await asyncio.gather(*critique_tasks)
        return self._aggregate_critiques(critiques)
```

## Key Performance Metrics to Track

Based on evaluation best practices[7][9]:

1. **Precision@N**: Of top N findings, how many are actually relevant?
2. **Hallucination rate**: Findings contradicted by sources
3. **Coverage**: Percentage of query aspects addressed
4. **Efficiency**: Cost per high-quality finding
5. **Consensus score**: Agreement between critic models
6. **Source diversity**: Unique domains/perspectives

Your current system would score poorly on all these metrics. The multi-agent ensemble approach addresses each one systematically.

***

**Bottom Line:** Your pipeline needs to move from linear single-agent iteration to parallel orchestrator-worker architecture with multi-model ensembles. The research is clear: this architecture produces 60-90% better results[1][2][3]. Start with Phase 1 fixes to stop producing garbage, then implement the parallel architecture for transformative improvement.

Sources
[1] How we built our multi-agent research system - Anthropic https://www.anthropic.com/engineering/multi-agent-research-system
[2] LLM Ensemble is a Winning Approach for Content Categorization https://arxiv.org/html/2511.15714v1
[3] Large Language Model Synergy for Ensemble Learning in Medical ... https://www.jmir.org/2025/1/e70080
[4] Many Heads Are Better Than One: Improved Scientific Idea Generation by A
  LLM-Based Multi-Agent System http://arxiv.org/pdf/2410.09403.pdf
[5] [PDF] Exploring Design of Multi-Agent LLM Dialogues for Research Ideation https://arxiv.org/pdf/2507.08350.pdf
[6] IMPROVE: Iterative Model Pipeline Refinement and Optimization Leveraging
  LLM Agents http://arxiv.org/pdf/2502.18530.pdf
[7] A Comprehensive Guide to Evaluating Multi-Agent LLM Systems https://orq.ai/blog/multi-agent-llm-eval-system
[8] Understanding the 4 Main Approaches to LLM Evaluation (From ... https://magazine.sebastianraschka.com/p/llm-evaluation-4-approaches
[9] LLM evaluation: Metrics, frameworks, and best practices - Wandb https://wandb.ai/onlineinference/genai-research/reports/LLM-evaluation-Metrics-frameworks-and-best-practices--VmlldzoxMTMxNjQ4NA
[10] fd3a8ec4-d7df-4a92-951b-952c985bf2fb.md https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/43046750/22a55ab1-f7d0-41c4-98dc-f67c049f7b76/fd3a8ec4-d7df-4a92-951b-952c985bf2fb.md
[11] MALT: Improving Reasoning with Multi-Agent LLM Training https://arxiv.org/pdf/2412.01928.pdf
[12] Training Language Models to Critique With Multi-agent Feedback http://arxiv.org/pdf/2410.15287.pdf
[13] SagaLLM: Context Management, Validation, and Transaction Guarantees for
  Multi-Agent LLM Planning http://arxiv.org/pdf/2503.11951.pdf
[14] Large Language Model based Multi-Agents: A Survey of Progress and
  Challenges https://arxiv.org/pdf/2402.01680.pdf
[15] Multi-Agent Collaborative Data Selection for Efficient LLM Pretraining https://arxiv.org/html/2410.08102v1
[16] Multi-Agent Collaboration: Harnessing the Power of Intelligent LLM
  Agents https://arxiv.org/pdf/2306.03314.pdf
[17] Introducing Agentic Research: A New Era for Scientific Decision ... https://www.causaly.com/blog/introducing-agentic-research-a-new-era-for-scientific-decision-making
[18] The (R)evolution of Scientific Workflows in the Agentic AI Era - arXiv https://arxiv.org/html/2509.09915v1
[19] [PDF] Evaluating Ensemble LLMs with Label Refinement in Inductive Coding https://aclanthology.org/2025.findings-acl.563.pdf
[20] What Are Agentic Workflows? Patterns, Use Cases, Examples, and ... https://weaviate.io/blog/what-are-agentic-workflows
[21] Designing Multi-Agent Intelligence - Microsoft for Developers https://developer.microsoft.com/blog/designing-multi-agent-intelligence
[22] High-performance automated abstract screening with large ... https://pmc.ncbi.nlm.nih.gov/articles/PMC12012331/
[23] Seizing the agentic AI advantage - McKinsey https://www.mckinsey.com/capabilities/quantumblack/our-insights/seizing-the-agentic-ai-advantage
[24] How to Build Multi Agent AI Systems With Context Engineering https://www.vellum.ai/blog/multi-agent-systems-building-with-context-engineering
[25] Agentic AI Workflows: Benefits, Risks and What's Next | Sprinklr https://www.sprinklr.com/blog/agentic-ai-workflow/
[26] Best practices for deploying multi-agent AI systems with distributed ... https://www.reddit.com/r/AI_Agents/comments/1mhi8xp/best_practices_for_deploying_multiagent_ai/
[27] Platform Identify ways to improve services agentic workflow https://www.servicenow.com/docs/bundle/zurich-intelligent-experiences/page/administer/now-assist-ai-agents/concept/service-improvement.html
[28] Real-Time Decision Pipelines for Multi-Agent LLMs | newline https://www.newline.co/@zaoyang/real-time-decision-pipelines-for-multi-agent-llms--d7ea23a6
[29] Merge, Ensemble, and Cooperate! A Survey on Collaborative LLM ... https://arize.com/blog/merge-ensemble-and-cooperate-a-survey-on-collaborative-llm-strategies/
