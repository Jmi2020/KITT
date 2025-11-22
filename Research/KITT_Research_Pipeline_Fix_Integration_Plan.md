# KITT Research Pipeline Fix - Integration Plan

**Date:** 2025-11-21  
**Target System:** KITT Autonomous Research Pipeline  
**Issue:** Template misselection causing sparse, irrelevant research results  
**Current Model:** GPT-OSS 120B (Ollama) for F16 reasoning  

---

## Executive Summary

Analysis of research session `fd3a8ec4-d7df-4a92-951b-952c985bf2fb` reveals the root cause of minimal output: **the system incorrectly applied a "Product Research" template to an AI ethics academic query**. This cascaded into:

- Wrong search keywords ("review", "specs", "price" instead of "ethics", "academic", "debate")
- Malformed decomposed queries (3 out of 5 findings = "No results found")
- Zero external model usage ($0.00 cost on a complex query that should trigger escalation)
- Irrelevant results (PBS Kids videos, psychology articles)

**Impact:** 5 findings instead of expected 25-40, 6 sources instead of 15-25, 0% external model utilization.

---

## Root Cause Analysis

### Problem 1: No Template Selection Logic

**File:** `services/brain/src/brain/research/pipeline.py` (likely)

**Evidence from output:**
```json
"template": {
  "name": "Product Research", 
  "type": "product_research",
  "description": "Research products, reviews, specifications"
},
"search_keywords": ["review", "specs", "specifications", "price", "features"]
```

**Query:** "Review the top 3 conflicting viewpoints on AI ethics published last year..."

**What should have happened:** 
- Detected "ethics" + "published" + "conflicting viewpoints" → `ethics_research` or `academic_research` template
- Keywords: ["ethics", "ethical", "debate", "published", "academic"]

**What actually happened:**
- Detected "Review" + "top 3" → defaulted to `product_research` template  
- Keywords: ["review", "specs", "price", "features"]

### Problem 2: Query Decomposition Failures

**Evidence from output:**
```
Finding 2: No results found for: Review the top 3 conflicting viewpoints on AI ethics published last year. Identify where evidence disagrees?...
Finding 3: No results found for: explain the possible reasons for these differences.?...
```

**Issues:**
- Malformed punctuation ("disagrees?" should be "disagrees")
- Full query passed instead of focused subtasks
- Product keywords applied to decomposed ethics queries

### Problem 3: Missing Execution Metadata

**Evidence from output:**
```
Temperature: N/A
Top_p: N/A
Max_Tokens: N/A
System_Prompt_Summary: N/A
```

LangGraph state not being captured/exported properly.

### Problem 4: No External Model Escalation

**Evidence:**
- Cost: $0.0000
- Complex query with 6/7 complexity signals
- Should have triggered tier "critical" → Claude Sonnet 4.5 or GPT-5

---

## Integration Plan

### Phase 1: Template Selection System (Priority: CRITICAL)

#### File to Create: `services/brain/src/brain/research/template_selector.py`

**Purpose:** Intelligently select research template based on query analysis.

**Dependencies:**
- None (pure Python logic)

**Interface:**
```python
class TemplateSelector:
    def select_template(self, query: str) -> Dict:
        """
        Returns:
        {
            "name": "ethics_research",  # or academic_research, product_research, etc.
            "config": {
                "keywords": [...],
                "search_keywords": [...],
                "tools": [...],
                "min_sources": 10,
                "decompose": True
            },
            "score": 0.85
        }
        """
```

**Implementation Details:**

```python
# services/brain/src/brain/research/template_selector.py

from typing import Dict, List
import re
import logging

logger = logging.getLogger(__name__)

class TemplateSelector:
    """Select appropriate research template based on query analysis."""
    
    def __init__(self):
        self.templates = {
            "academic_research": {
                "keywords": [
                    "published", "paper", "study", "research", "journal", 
                    "academic", "scholar", "peer-reviewed", "last year", 
                    "2024", "findings", "evidence", "literature"
                ],
                "search_keywords": [
                    "academic", "study", "research", "published", 
                    "paper", "journal", "scholar"
                ],
                "tools": ["web_search", "web_fetch"],
                "min_sources": 8,
                "max_iterations": 12,
                "decompose": True,
                "escalation_threshold": 0.6  # Complexity score for external models
            },
            
            "ethics_research": {
                "keywords": [
                    "ethics", "ethical", "morality", "moral", "values", 
                    "principles", "viewpoints", "perspectives", "conflicting", 
                    "debate", "arguments", "framework", "philosophy"
                ],
                "search_keywords": [
                    "ethics", "ethical", "morality", "philosophical",
                    "debate", "arguments", "values", "principles"
                ],
                "tools": ["web_search", "web_fetch"],
                "min_sources": 10,
                "max_iterations": 15,
                "decompose": True,
                "escalation_threshold": 0.5  # Ethics often needs deep reasoning
            },
            
            "product_research": {
                "keywords": [
                    "product", "buy", "purchase", "price", "cost", 
                    "specifications", "specs", "features", "compare",
                    "best", "recommendation", "which should i"
                ],
                "search_keywords": [
                    "review", "price", "specs", "features", 
                    "buy", "product", "comparison"
                ],
                "tools": ["web_search", "web_fetch"],
                "min_sources": 5,
                "max_iterations": 8,
                "decompose": False,
                "escalation_threshold": 0.8  # Products rarely need external models
            },
            
            "technical_research": {
                "keywords": [
                    "implementation", "algorithm", "code", "architecture",
                    "technical", "engineering", "system", "how to",
                    "tutorial", "guide", "documentation", "api"
                ],
                "search_keywords": [
                    "implementation", "tutorial", "documentation", 
                    "guide", "howto", "technical", "code"
                ],
                "tools": ["web_search", "web_fetch"],
                "min_sources": 6,
                "max_iterations": 10,
                "decompose": True,
                "escalation_threshold": 0.7
            },
            
            "current_events": {
                "keywords": [
                    "latest", "recent", "today", "this week", "breaking",
                    "news", "current", "happening now", "update"
                ],
                "search_keywords": [
                    "news", "latest", "recent", "2024", "2025", "current"
                ],
                "tools": ["web_search", "web_fetch"],
                "min_sources": 8,
                "max_iterations": 8,
                "decompose": False,
                "escalation_threshold": 0.9  # News is usually free/cached
            }
        }
    
    def select_template(self, query: str) -> Dict:
        """Select best template based on query content."""
        query_lower = query.lower()
        
        # Score each template
        scores = {}
        for template_name, template_config in self.templates.items():
            score = self._score_template(query_lower, template_config)
            scores[template_name] = score
        
        # Get best match
        best_template = max(scores, key=scores.get)
        best_score = scores[best_template]
        
        # Apply disambiguation rules
        best_template = self._disambiguate(query_lower, best_template, scores)
        
        logger.info(f"Template selection scores: {scores}")
        logger.info(f"Selected template: {best_template} (score: {best_score:.2f})")
        
        return {
            "name": best_template,
            "config": self.templates[best_template],
            "score": best_score
        }
    
    def _score_template(self, query_lower: str, template_config: Dict) -> float:
        """Calculate match score for a template."""
        keywords = template_config["keywords"]
        score = 0.0
        
        for keyword in keywords:
            if keyword in query_lower:
                score += 1.0
                
                # Bonus for exact phrase match (word boundaries)
                if f" {keyword} " in f" {query_lower} ":
                    score += 0.5
                
                # Bonus for keyword at start of query
                if query_lower.startswith(keyword):
                    score += 0.3
        
        # Normalize by keyword count
        return score / len(keywords)
    
    def _disambiguate(self, query_lower: str, 
                      current_best: str, 
                      scores: Dict[str, float]) -> str:
        """Apply disambiguation rules to handle edge cases."""
        
        # Rule 1: "Review/Find/List the top N" - is it products or ideas?
        if re.search(r'\b(review|find|list)\s+(?:the\s+)?top\s+\d+\b', query_lower):
            idea_signals = [
                "viewpoint", "perspective", "argument", "theory", 
                "framework", "approach", "method", "position"
            ]
            
            if any(signal in query_lower for signal in idea_signals):
                # It's about ideas, not products
                if "ethics" in query_lower or "philosophy" in query_lower:
                    logger.info("Disambiguation: Switching from product to ethics research")
                    return "ethics_research"
                elif "published" in query_lower or "paper" in query_lower:
                    logger.info("Disambiguation: Switching from product to academic research")
                    return "academic_research"
        
        # Rule 2: If both academic and ethics score high, prefer ethics
        if (scores.get("ethics_research", 0) > 0.3 and 
            scores.get("academic_research", 0) > 0.3):
            logger.info("Disambiguation: Both ethics and academic match, preferring ethics")
            return "ethics_research"
        
        # Rule 3: Technical implementation queries about ethical topics
        if current_best == "technical_research" and "ethics" in query_lower:
            logger.info("Disambiguation: Technical query about ethics, keeping technical")
            # Keep technical - they want implementation, not philosophy
        
        return current_best
```

**Integration Steps:**

1. Create the file at the path above
2. Add to imports in `services/brain/src/brain/research/pipeline.py`:
   ```python
   from .template_selector import TemplateSelector
   ```
3. Initialize in `ResearchPipeline.__init__()`:
   ```python
   self.template_selector = TemplateSelector()
   ```
4. Use in `ResearchPipeline.execute()`:
   ```python
   async def execute(self, query: str) -> ResearchResult:
       # SELECT TEMPLATE FIRST (before creating context)
       template_result = self.template_selector.select_template(query)
       logger.info(f"Using template: {template_result['name']}")
       
       # Create context with correct template
       context = ResearchContext(
           query=query,
           template=template_result['config'],
           strategy=self._select_strategy(query, template_result),
           max_iterations=template_result['config']['max_iterations'],
           min_sources=template_result['config']['min_sources']
       )
       
       # Continue with existing research logic...
   ```

**Testing:**
```bash
# Run from services/brain/
pytest tests/unit/test_template_selector.py -v

# Test cases to add:
# 1. Ethics query → ethics_research template
# 2. Product query → product_research template  
# 3. "Review top 3 viewpoints" → ethics_research (not product!)
# 4. Technical implementation → technical_research
```

---

### Phase 2: Query Decomposition Fix (Priority: HIGH)

#### File to Modify: `services/brain/src/brain/research/strategies/task_decomposition.py`

**Current Problem:** Decomposed queries are malformed and use wrong keywords.

**Solution:** Use GPT-OSS 120B to intelligently decompose queries with proper context.

**Implementation:**

```python
# services/brain/src/brain/research/strategies/task_decomposition.py

import json
import logging
from typing import List, Dict
import aiohttp

logger = logging.getLogger(__name__)

class TaskDecompositionStrategy:
    """Decompose complex queries into focused subtasks."""
    
    def __init__(self, ollama_host: str = "http://host.docker.internal:11434"):
        self.ollama_host = ollama_host
        self.model = "gpt-oss:120b"
    
    async def decompose_query(self, query: str, template: Dict) -> List[str]:
        """
        Use GPT-OSS to decompose query intelligently.
        
        Args:
            query: Original research query
            template: Template config dict with context about query type
            
        Returns:
            List of 3-5 focused subtask queries
        """
        
        # Check if decomposition is needed
        if not template.get("decompose", False):
            logger.info("Template doesn't require decomposition")
            return [query]
        
        # Build decomposition prompt
        decomposition_prompt = self._build_decomposition_prompt(query, template)
        
        try:
            # Call Ollama GPT-OSS with high think mode
            subtasks = await self._call_ollama_for_decomposition(decomposition_prompt)
            
            logger.info(f"Decomposed query into {len(subtasks)} subtasks:")
            for i, subtask in enumerate(subtasks, 1):
                logger.info(f"  {i}. {subtask}")
            
            return subtasks
            
        except Exception as e:
            logger.error(f"Decomposition failed: {e}", exc_info=True)
            logger.warning("Falling back to rule-based decomposition")
            return self._fallback_decomposition(query, template)
    
    def _build_decomposition_prompt(self, query: str, template: Dict) -> str:
        """Build prompt for GPT-OSS decomposition."""
        
        template_name = template.get("name", "unknown")
        search_keywords = template.get("search_keywords", [])
        
        prompt = f"""You are a research assistant helping decompose complex queries into focused subtasks.

ORIGINAL QUERY:
{query}

RESEARCH TYPE: {template_name.replace('_', ' ').title()}

CONTEXT:
- This is a {template_name} task
- Relevant search domains: {', '.join(search_keywords)}
- Goal: Break into 3-5 independent subtasks that can be researched separately

REQUIREMENTS:
1. Each subtask must be a complete, well-formed question
2. No trailing punctuation errors (avoid "question?..." or "question?")
3. Subtasks should cover different aspects of the main query
4. No duplicate or overlapping subtasks
5. Each subtask should be searchable as-is
6. Maintain the same level of specificity as the original query

OUTPUT FORMAT:
Return ONLY a valid JSON array of strings. No explanation, no markdown, just:
["subtask 1", "subtask 2", "subtask 3"]

EXAMPLE FOR ETHICS RESEARCH:
Original: "Compare utilitarian and deontological approaches to AI ethics"
Output: ["What are the core principles of utilitarian AI ethics", "What are the core principles of deontological AI ethics", "What are the main conflicts between utilitarian and deontological AI frameworks"]

NOW DECOMPOSE THIS QUERY:
{query}

JSON ARRAY:"""
        
        return prompt
    
    async def _call_ollama_for_decomposition(self, prompt: str) -> List[str]:
        """Call Ollama GPT-OSS API for decomposition."""
        
        async with aiohttp.ClientSession() as session:
            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.7,
                    "top_p": 0.9,
                    "num_predict": 1000,
                    "stop": ["\n\n", "EXPLANATION:"]
                }
            }
            
            async with session.post(
                f"{self.ollama_host}/api/generate",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=120)
            ) as response:
                response.raise_for_status()
                result = await response.json()
                
                # Extract response text
                response_text = result.get("response", "")
                
                # Parse JSON array
                # Clean up any markdown formatting
                response_text = response_text.strip()
                response_text = response_text.replace("```json", "").replace("```", "")
                
                subtasks = json.loads(response_text)
                
                # Validate
                if not isinstance(subtasks, list):
                    raise ValueError("Response is not a JSON array")
                
                if not all(isinstance(s, str) for s in subtasks):
                    raise ValueError("Subtasks contain non-string items")
                
                if len(subtasks) < 2 or len(subtasks) > 6:
                    logger.warning(f"Unusual subtask count: {len(subtasks)}")
                
                return subtasks
    
    def _fallback_decomposition(self, query: str, template: Dict) -> List[str]:
        """Rule-based fallback when LLM decomposition fails."""
        
        query_lower = query.lower()
        template_name = template.get("name", "unknown")
        
        # Rule-based decomposition by query type
        if "conflicting viewpoints" in query_lower or "different views" in query_lower:
            topic = self._extract_topic(query)
            year = self._extract_year(query)
            
            return [
                f"What are the major {topic} frameworks and perspectives {year}",
                f"Find academic papers discussing disagreements in {topic} {year}",
                f"Identify specific points of conflict between different {topic} approaches",
                f"Explain the root causes of divergent {topic} viewpoints"
            ]
        
        elif "compare" in query_lower or "contrast" in query_lower:
            # Extract entities being compared
            entities = self._extract_comparison_entities(query)
            if len(entities) >= 2:
                return [
                    f"What are the key characteristics of {entities[0]}",
                    f"What are the key characteristics of {entities[1]}",
                    f"What are the main differences between {entities[0]} and {entities[1]}",
                    f"What are the strengths and weaknesses of each approach"
                ]
        
        elif "top" in query_lower and any(char.isdigit() for char in query):
            # "Top N" queries
            topic = self._extract_topic(query)
            return [
                f"What are the most well-known {topic}",
                f"Find expert recommendations for {topic}",
                f"Compare the strengths and weaknesses of leading {topic}"
            ]
        
        # Default: return original query (no decomposition)
        logger.warning("No decomposition rule matched, returning original query")
        return [query]
    
    def _extract_topic(self, query: str) -> str:
        """Extract main topic from query."""
        # Simple heuristic: look for key noun phrases
        # In production, use spaCy or similar for proper NER
        
        # Remove common question words
        topic = query.lower()
        for word in ["what", "how", "why", "when", "where", "which", 
                     "review", "find", "list", "explain", "identify"]:
            topic = topic.replace(word, "")
        
        # Extract first meaningful phrase
        topic = topic.strip()
        
        # Look for quoted or emphasized terms
        if '"' in topic:
            import re
            match = re.search(r'"([^"]+)"', topic)
            if match:
                return match.group(1)
        
        # Take first few words as topic
        words = topic.split()[:4]
        return " ".join(words).strip(".,?! ")
    
    def _extract_year(self, query: str) -> str:
        """Extract year reference from query."""
        query_lower = query.lower()
        
        if "last year" in query_lower:
            return "in 2024"
        elif "this year" in query_lower:
            return "in 2025"
        elif "2024" in query:
            return "in 2024"
        elif "2025" in query:
            return "in 2025"
        else:
            return "recently"
    
    def _extract_comparison_entities(self, query: str) -> List[str]:
        """Extract entities being compared."""
        # Look for "X vs Y", "X and Y", etc.
        import re
        
        # Pattern: "compare X and Y"
        match = re.search(r'compare\s+([^,]+?)\s+(?:and|with|vs|versus)\s+([^,\.]+)', 
                         query, re.IGNORECASE)
        if match:
            return [match.group(1).strip(), match.group(2).strip()]
        
        # Pattern: "X vs Y"
        match = re.search(r'([^,]+?)\s+(?:vs|versus)\s+([^,\.]+)', 
                         query, re.IGNORECASE)
        if match:
            return [match.group(1).strip(), match.group(2).strip()]
        
        return []
```

**Integration Steps:**

1. Modify or create the file above
2. Update pipeline to use it:
   ```python
   # In ResearchPipeline
   from .strategies.task_decomposition import TaskDecompositionStrategy
   
   async def execute(self, query: str) -> ResearchResult:
       # After template selection...
       
       if context.template['decompose']:
           decomposer = TaskDecompositionStrategy(
               ollama_host=os.getenv("OLLAMA_HOST", "http://host.docker.internal:11434")
           )
           subtasks = await decomposer.decompose_query(query, context.template)
           context.subtasks = subtasks
       else:
           context.subtasks = [query]
   ```

**Testing:**
```bash
# Test Ollama connectivity first
curl http://localhost:11434/api/generate -d '{
  "model": "gpt-oss:120b",
  "prompt": "Test",
  "stream": false
}'

# Run decomposition tests
pytest tests/unit/test_task_decomposition.py -v
```

---

### Phase 3: Metadata Capture Fix (Priority: HIGH)

#### File to Modify: `services/brain/src/brain/research/state.py`

**Current Problem:** All execution metadata shows "N/A" in exported reports.

**Solution:** Capture model config, prompts, and execution details in LangGraph state.

**Implementation:**

```python
# services/brain/src/brain/research/state.py

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional
from datetime import datetime

@dataclass
class ModelConfig:
    """Model configuration for research execution."""
    model_name: str = "GPT-OSS-120B"
    revision: str = "ollama"
    temperature: float = 0.7
    top_p: float = 0.95
    max_tokens: int = 4096
    think_mode: str = "medium"  # low, medium, high
    
    def to_dict(self) -> Dict:
        return asdict(self)

@dataclass
class ResearchState:
    """LangGraph state for research pipeline with complete metadata."""
    
    # Core identifiers
    session_id: str
    query: str
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    # Template and strategy
    template: Dict = field(default_factory=dict)
    strategy: str = "hybrid"
    
    # Execution state
    current_iteration: int = 0
    max_iterations: int = 10
    subtasks: List[str] = field(default_factory=list)
    findings: List[Dict] = field(default_factory=list)
    sources: List[Dict] = field(default_factory=list)
    
    # Model configuration (CRITICAL: capture this!)
    model_config: ModelConfig = field(default_factory=ModelConfig)
    system_prompt: str = ""
    user_prompt_template: str = ""
    
    # Metrics and costs
    total_cost_usd: float = 0.0
    external_calls_made: int = 0
    tool_calls: List[Dict] = field(default_factory=list)
    
    # Quality metrics
    confidence_scores: List[float] = field(default_factory=list)
    ragas_scores: Dict[str, float] = field(default_factory=dict)
    saturation_detected: bool = False
    
    # Execution metadata
    errors: List[Dict] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    def to_export_dict(self) -> Dict:
        """
        Export state for report generation.
        Returns dict with NO 'N/A' values - all fields populated.
        """
        return {
            "metadata": {
                "run_id": self.session_id,
                "date": self.created_at.strftime("%Y-%m-%d"),
                "researcher": "Jeremiah",
                "model_name": self.model_config.model_name,
                "model_revision": self.model_config.revision,
                "pipeline_stage": "analysis",
                "dataset_name": "research_sessions",
                "task_type": "research",
                "experiment_tag": f"strategy={self.strategy}"
            },
            
            "research_question": {
                "primary_question": self.query,
                "secondary_questions": self.subtasks if len(self.subtasks) > 1 else []
            },
            
            "hypotheses": {
                "null_hypothesis": "N/A",  # Optional field
                "working_hypotheses": []    # Optional field
            },
            
            "experiment_design": {
                "variables": {
                    "independent": {
                        "strategy": self.strategy,
                        "max_iterations": self.max_iterations,
                        "template": self.template.get("name", "unknown")
                    },
                    "dependent": {
                        "findings": len(self.findings),
                        "cost_usd": self.total_cost_usd
                    }
                },
                "model_configuration": self.model_config.to_dict(),
                "data_sampling": {
                    "input_source": "web + tools",
                    "sample_size": len(self.sources),
                    "sampling_strategy": "iterative search",
                    "filtering_notes": []
                }
            },
            
            "prompt_setup": {
                "system_prompt": self.system_prompt,
                "user_prompt_template": self.user_prompt_template,
                "has_few_shot": False,
                "few_shot_examples": []
            },
            
            "results": {
                "quantitative": {
                    "total_findings": len(self.findings),
                    "total_sources": len(self.sources),
                    "total_cost_usd": round(self.total_cost_usd, 4),
                    "external_calls": self.external_calls_made,
                    "iterations_completed": self.current_iteration,
                    "tool_calls": len(self.tool_calls)
                },
                "qualitative": {
                    "findings": self.findings,
                    "sources": self.sources,
                    "synthesis": self._generate_synthesis(),
                    "confidence_summary": self._summarize_confidence()
                }
            },
            
            "analysis": {
                "interpretation": {
                    "status": "completed",
                    "completeness_score": self._calculate_completeness(),
                    "confidence_score": self._calculate_avg_confidence()
                },
                "quality_metrics": self.ragas_scores,
                "saturation": {
                    "detected": self.saturation_detected,
                    "iteration": self.current_iteration if self.saturation_detected else None
                },
                "threats_to_validity": {
                    "internal": self.warnings,
                    "external": ["Findings not audited; relies on upstream sources"]
                }
            },
            
            "decisions": {
                "next_steps": self._suggest_next_steps(),
                "notes_for_pipeline": [
                    "Session exported from CLI report command",
                    f"Template: {self.template.get('name', 'unknown')}",
                    f"Strategy: {self.strategy}"
                ]
            },
            
            "raw_log": {
                "tool_calls": self.tool_calls,
                "errors": self.errors
            }
        }
    
    def _generate_synthesis(self) -> str:
        """Generate research synthesis from findings."""
        if not self.findings:
            return "No findings to synthesize."
        
        synthesis = f"Research completed for query: '{self.query}'\n\n"
        synthesis += f"Found {len(self.findings)} findings across {self.current_iteration} iterations.\n\n"
        
        if self.findings:
            synthesis += "Key Findings:\n"
            for i, finding in enumerate(self.findings[:5], 1):
                confidence = finding.get("confidence", 0.0)
                content = finding.get("content", "N/A")[:200]
                synthesis += f"{i}. (Confidence: {confidence:.2f}) {content}...\n\n"
        
        return synthesis
    
    def _summarize_confidence(self) -> str:
        """Summarize confidence distribution."""
        if not self.confidence_scores:
            return "No confidence scores available"
        
        avg = sum(self.confidence_scores) / len(self.confidence_scores)
        min_conf = min(self.confidence_scores)
        max_conf = max(self.confidence_scores)
        
        return f"Average: {avg:.2f}, Range: {min_conf:.2f}-{max_conf:.2f}"
    
    def _calculate_completeness(self) -> Optional[float]:
        """Calculate research completeness score."""
        if self.max_iterations == 0:
            return None
        
        # Based on iterations, findings, and sources
        iteration_score = min(self.current_iteration / self.max_iterations, 1.0)
        findings_score = min(len(self.findings) / 20, 1.0)  # Target: 20 findings
        sources_score = min(len(self.sources) / 15, 1.0)    # Target: 15 sources
        
        # Weighted average
        completeness = (0.3 * iteration_score + 
                       0.4 * findings_score + 
                       0.3 * sources_score)
        
        return round(completeness, 2)
    
    def _calculate_avg_confidence(self) -> Optional[float]:
        """Calculate average confidence score."""
        if not self.confidence_scores:
            return None
        return round(sum(self.confidence_scores) / len(self.confidence_scores), 2)
    
    def _suggest_next_steps(self) -> List[str]:
        """Suggest next steps based on results."""
        suggestions = []
        
        if len(self.findings) < 10:
            suggestions.append("Run further iterations to collect more findings")
        
        if self.total_cost_usd == 0 and self.current_iteration >= 5:
            suggestions.append("Consider enabling external models for deeper analysis")
        
        if not self.ragas_scores:
            suggestions.append("Enable RAGAS validation for quality assessment")
        
        if len(self.subtasks) <= 1 and len(self.findings) < 15:
            suggestions.append("Enable query decomposition for broader coverage")
        
        return suggestions if suggestions else ["Research appears complete"]
```

**Integration Steps:**

1. Update `ResearchPipeline` to populate metadata:
   ```python
   async def execute(self, query: str) -> ResearchResult:
       # Create state with full metadata
       state = ResearchState(
           session_id=str(uuid.uuid4()),
           query=query,
           template=template_result['config'],
           strategy=selected_strategy
       )
       
       # Populate model config
       state.model_config = ModelConfig(
           model_name="GPT-OSS-120B",
           revision="ollama",
           temperature=0.7,
           top_p=0.95,
           max_tokens=4096,
           think_mode="high" if complexity_score > 0.6 else "medium"
       )
       
       # Build and store prompts
       state.system_prompt = self._build_system_prompt(state)
       state.user_prompt_template = self._build_user_prompt_template(state)
       
       # Continue execution...
   ```

2. Update export command:
   ```python
   # In CLI or API export handler
   export_dict = state.to_export_dict()
   
   # Render as markdown report
   report = render_research_report(export_dict)
   ```

---

### Phase 4: External Model Escalation (Priority: MEDIUM)

#### File to Modify: `services/brain/src/brain/routing/router.py`

**Current Problem:** Complex query didn't trigger external models ($0.00 cost).

**Solution:** Implement complexity-based escalation with proper thresholds.

**Implementation:**

```python
# services/brain/src/brain/routing/router.py

import re
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

class QueryRouter:
    """Route queries to appropriate model tier based on complexity."""
    
    def __init__(self):
        self.tiers = {
            "trivial": {
                "models": ["local_q4"],  # Athene V2 Q4
                "cost_threshold": 0.01,
                "confidence_threshold": 0.9
            },
            "low": {
                "models": ["local_q4", "local_f16"],
                "cost_threshold": 0.10,
                "confidence_threshold": 0.80
            },
            "medium": {
                "models": ["local_f16"],  # GPT-OSS 120B with medium think
                "cost_threshold": 0.25,
                "confidence_threshold": 0.75
            },
            "high": {
                "models": ["local_f16_high", "claude-sonnet-4.5"],
                "cost_threshold": 0.75,
                "confidence_threshold": 0.70
            },
            "critical": {
                "models": ["gpt-5", "claude-sonnet-4.5"],
                "cost_threshold": 2.00,
                "confidence_threshold": 0.60
            }
        }
    
    def calculate_complexity(self, query: str, template: Dict) -> Dict[str, any]:
        """
        Calculate query complexity to determine routing tier.
        
        Returns:
            {
                "score": 0.85,  # 0.0-1.0
                "tier": "critical",
                "signals": {...},
                "reasoning": "..."
            }
        """
        query_lower = query.lower()
        
        # Complexity signals (each is 0 or 1)
        signals = {
            "multi_part": self._check_multi_part(query_lower),
            "comparative": self._check_comparative(query_lower),
            "analytical": self._check_analytical(query_lower),
            "temporal": self._check_temporal(query_lower),
            "top_n": self._check_top_n(query_lower),
            "evidence_based": self._check_evidence_based(query_lower),
            "length": len(query.split()) > 12,
            "requires_synthesis": self._check_synthesis(query_lower)
        }
        
        # Calculate score (0.0-1.0)
        complexity_score = sum(signals.values()) / len(signals)
        
        # Template-based adjustments
        template_name = template.get("name", "unknown")
        if template_name == "ethics_research":
            complexity_score += 0.1  # Ethics often needs deeper reasoning
        elif template_name == "product_research":
            complexity_score -= 0.1  # Products are simpler
        
        # Clamp to 0-1
        complexity_score = max(0.0, min(1.0, complexity_score))
        
        # Map to tier
        tier = self._score_to_tier(complexity_score)
        
        # Generate reasoning
        reasoning = self._explain_complexity(signals, complexity_score, tier)
        
        logger.info(f"Complexity analysis: score={complexity_score:.2f}, tier={tier}")
        logger.info(f"Signals: {signals}")
        
        return {
            "score": complexity_score,
            "tier": tier,
            "signals": signals,
            "reasoning": reasoning
        }
    
    def _check_multi_part(self, query: str) -> bool:
        """Check if query has multiple parts/questions."""
        # Look for conjunctions that separate questions
        return bool(re.search(r'\b(and|also|additionally)\b.*\b(identify|explain|find)\b', query))
    
    def _check_comparative(self, query: str) -> bool:
        """Check if query requires comparison."""
        comparative_words = ["compare", "contrast", "vs", "versus", "different", 
                            "difference", "similarity", "alike"]
        return any(word in query for word in comparative_words)
    
    def _check_analytical(self, query: str) -> bool:
        """Check if query requires analysis/explanation."""
        analytical_words = ["why", "explain", "analyze", "reason", "cause",
                           "interpret", "evaluate", "assess"]
        return any(word in query for word in analytical_words)
    
    def _check_temporal(self, query: str) -> bool:
        """Check if query has time constraints."""
        temporal_words = ["last year", "2024", "2025", "recent", "latest",
                         "this year", "published"]
        return any(word in query for word in temporal_words)
    
    def _check_top_n(self, query: str) -> bool:
        """Check if query asks for 'top N' items."""
        return bool(re.search(r'\btop\s+\d+\b', query))
    
    def _check_evidence_based(self, query: str) -> bool:
        """Check if query requires evidence analysis."""
        evidence_words = ["evidence", "disagree", "conflict", "contradict",
                         "support", "refute", "prove"]
        return any(word in query for word in evidence_words)
    
    def _check_synthesis(self, query: str) -> bool:
        """Check if query requires synthesis of information."""
        synthesis_words = ["review", "summarize", "overview", "synthesis",
                          "consolidate", "integrate"]
        return any(word in query for word in synthesis_words)
    
    def _score_to_tier(self, score: float) -> str:
        """Map complexity score to routing tier."""
        if score >= 0.75:
            return "critical"
        elif score >= 0.60:
            return "high"
        elif score >= 0.40:
            return "medium"
        elif score >= 0.20:
            return "low"
        else:
            return "trivial"
    
    def _explain_complexity(self, signals: Dict, score: float, tier: str) -> str:
        """Generate human-readable explanation."""
        active_signals = [k for k, v in signals.items() if v]
        
        explanation = f"Query complexity: {score:.2f} → tier '{tier}'\n"
        explanation += f"Active signals ({len(active_signals)}/{len(signals)}): "
        explanation += ", ".join(active_signals)
        
        return explanation
    
    def should_escalate(self, 
                       complexity: Dict,
                       findings_so_far: int,
                       iteration: int,
                       budget_remaining: float) -> bool:
        """
        Determine if we should escalate to external models.
        
        Args:
            complexity: Result from calculate_complexity()
            findings_so_far: Number of findings collected
            iteration: Current iteration number
            budget_remaining: Remaining budget in USD
            
        Returns:
            True if should use external models
        """
        tier = complexity["tier"]
        
        # Critical tier: always escalate (if budget allows)
        if tier == "critical":
            if budget_remaining >= 0.50:
                logger.info("ESCALATING: Critical tier query")
                return True
            else:
                logger.warning("Cannot escalate: insufficient budget")
                return False
        
        # High tier: escalate if local models struggling
        if tier == "high":
            if findings_so_far < 5 and iteration > 3:
                logger.info("ESCALATING: High tier + low findings after iteration 3")
                return True
        
        # Medium/Low: stay local unless really struggling
        if tier in ["medium", "low"]:
            if findings_so_far < 3 and iteration > 5:
                logger.info("ESCALATING: Fallback after 5 iterations with <3 findings")
                return True
        
        logger.info("No escalation needed, continuing with local models")
        return False
```

**Integration:**

```python
# In ResearchPipeline.execute()

router = QueryRouter()

# Calculate complexity after template selection
complexity = router.calculate_complexity(query, context.template)
context.complexity = complexity

logger.info(f"Query routed to tier: {complexity['tier']}")

# Check for escalation during execution
for iteration in range(max_iterations):
    # ... execute iteration ...
    
    # Check if we should escalate
    if router.should_escalate(
        complexity=context.complexity,
        findings_so_far=len(context.findings),
        iteration=iteration,
        budget_remaining=budget_remaining
    ):
        # Use external model for next tool call
        context.force_external = True
```

---

## Testing Plan

### Unit Tests

```python
# tests/unit/test_template_selector.py

import pytest
from services.brain.src.brain.research.template_selector import TemplateSelector

def test_ethics_query_selects_ethics_template():
    selector = TemplateSelector()
    
    query = "Review the top 3 conflicting viewpoints on AI ethics published last year"
    result = selector.select_template(query)
    
    assert result["name"] in ["ethics_research", "academic_research"]
    assert result["name"] != "product_research"

def test_product_query_selects_product_template():
    selector = TemplateSelector()
    
    query = "What are the best noise-canceling headphones under $200"
    result = selector.select_template(query)
    
    assert result["name"] == "product_research"

def test_technical_query_selects_technical_template():
    selector = TemplateSelector()
    
    query = "How do I implement OAuth2 authentication in FastAPI"
    result = selector.select_template(query)
    
    assert result["name"] == "technical_research"
```

```python
# tests/unit/test_query_router.py

import pytest
from services.brain.src.brain.routing.router import QueryRouter

def test_complex_ethics_query_is_critical_tier():
    router = QueryRouter()
    
    query = "Review the top 3 conflicting viewpoints on AI ethics published last year. Identify where evidence disagrees and explain the possible reasons for these differences."
    template = {"name": "ethics_research"}
    
    complexity = router.calculate_complexity(query, template)
    
    # Should have 6-7 active signals
    assert complexity["score"] >= 0.70
    assert complexity["tier"] in ["high", "critical"]

def test_simple_query_is_trivial_tier():
    router = QueryRouter()
    
    query = "What is Python"
    template = {"name": "technical_research"}
    
    complexity = router.calculate_complexity(query, template)
    
    assert complexity["score"] < 0.30
    assert complexity["tier"] in ["trivial", "low"]
```

### Integration Tests

```bash
# tests/integration/test_research_pipeline.py

import pytest
from services.brain.src.brain.research.pipeline import ResearchPipeline

@pytest.mark.asyncio
async def test_ethics_query_uses_correct_template():
    pipeline = ResearchPipeline()
    
    query = "Review the top 3 conflicting viewpoints on AI ethics"
    result = await pipeline.execute(query)
    
    # Check template selection
    assert result.template["name"] in ["ethics_research", "academic_research"]
    
    # Check decomposition happened
    assert len(result.subtasks) >= 3
    
    # Check substantive results
    assert len(result.findings) >= 15
    assert len(result.sources) >= 10
    
    # Check metadata captured
    assert result.model_config.model_name != "N/A"
    assert result.system_prompt != ""

@pytest.mark.asyncio
async def test_complex_query_escalates_to_external():
    pipeline = ResearchPipeline()
    
    query = "Review the top 3 conflicting viewpoints on AI ethics published last year. Identify where evidence disagrees and explain the possible reasons for these differences."
    result = await pipeline.execute(query)
    
    # Should have used external models
    assert result.total_cost_usd > 0
    assert result.external_calls_made > 0
    
    # Should have high-quality results
    assert len(result.findings) >= 25
    assert result.avg_confidence >= 0.75
```

---

## Deployment Steps

1. **Backup Current State**
   ```bash
   cd ~/KITT
   git checkout -b research-pipeline-fix
   git add .
   git commit -m "Backup before research pipeline fixes"
   ```

2. **Apply Phase 1: Template Selection**
   ```bash
   # Create template_selector.py
   # Update pipeline.py imports and init
   # Test template selection
   pytest tests/unit/test_template_selector.py -v
   ```

3. **Apply Phase 2: Query Decomposition**
   ```bash
   # Update task_decomposition.py
   # Test with Ollama
   curl http://localhost:11434/api/tags  # Verify Ollama running
   pytest tests/unit/test_task_decomposition.py -v
   ```

4. **Apply Phase 3: Metadata Capture**
   ```bash
   # Update state.py
   # Test export
   pytest tests/unit/test_research_state.py -v
   ```

5. **Apply Phase 4: External Model Escalation**
   ```bash
   # Update router.py
   # Test complexity calculation
   pytest tests/unit/test_query_router.py -v
   ```

6. **Integration Testing**
   ```bash
   # Start KITT stack
   ./ops/scripts/start-all.sh
   
   # Run integration tests
   pytest tests/integration/test_research_pipeline.py -v
   
   # Manual test via CLI
   kitty-cli shell
   > /agent on
   > /verbosity 5
   > omega Review the top 3 conflicting viewpoints on AI ethics published last year. Identify where evidence disagrees and explain the possible reasons for these differences.
   ```

7. **Validation**
   - Check findings count: Should be 25-40 (not 5)
   - Check sources count: Should be 15-25 (not 6)
   - Check cost: Should be $0.20-$0.80 (not $0.00)
   - Check template: Should be "ethics_research" (not "product_research")
   - Check metadata: No "N/A" values in export

8. **Rollback Plan**
   ```bash
   # If issues occur:
   git checkout main
   ./ops/scripts/stop-all.sh
   ./ops/scripts/start-all.sh
   ```

---

## Environment Configuration

Add these to `.env`:

```bash
# Research Pipeline Configuration
RESEARCH_STRATEGY=hybrid  # hybrid, breadth_first, depth_first, task_decomposition
RESEARCH_ENABLE_DECOMPOSITION=true
MIN_SUBTASKS=3
MAX_SUBTASKS=5

# Template Selection
RESEARCH_DEFAULT_TEMPLATE=auto  # auto, ethics_research, academic_research, etc.

# External Model Escalation
RESEARCH_ENABLE_ESCALATION=true
RESEARCH_CRITICAL_THRESHOLD=0.75  # Complexity score for critical tier
RESEARCH_HIGH_THRESHOLD=0.60      # Complexity score for high tier

# Budget Limits
RESEARCH_BUDGET_USD=2.0
RESEARCH_EXTERNAL_CALL_LIMIT=10

# Ollama Configuration (for decomposition)
OLLAMA_HOST=http://host.docker.internal:11434
OLLAMA_MODEL=gpt-oss:120b
OLLAMA_DECOMPOSITION_THINK=high  # low, medium, high

# Quality Thresholds
MIN_RAGAS_SCORE=0.75
MIN_CONFIDENCE=0.75
SATURATION_THRESHOLD=0.8

# Logging
RESEARCH_VERBOSE=true
LOG_LEVEL=INFO  # Set to DEBUG for detailed troubleshooting
```

---

## Monitoring and Validation

### Key Metrics to Monitor

1. **Template Selection Accuracy**
   - Track: Template chosen vs expected template
   - Goal: >95% accuracy on known query types

2. **Findings Quality**
   - Track: Findings per query, sources per query
   - Goal: 25+ findings, 15+ sources for complex queries

3. **Cost Efficiency**
   - Track: External calls per query, cost per query
   - Goal: <$1.00 per complex query, 70% queries stay local

4. **Decomposition Success**
   - Track: Subtask count, subtask relevance
   - Goal: 3-5 subtasks per complex query, no malformed queries

### Prometheus Metrics

Add to `services/brain/src/brain/metrics.py`:

```python
from prometheus_client import Counter, Histogram, Gauge

# Template selection metrics
template_selection_counter = Counter(
    'research_template_selection_total',
    'Number of template selections by type',
    ['template_name', 'query_type']
)

# Complexity metrics
query_complexity_histogram = Histogram(
    'research_query_complexity_score',
    'Distribution of query complexity scores'
)

# Escalation metrics
external_escalation_counter = Counter(
    'research_external_escalation_total',
    'Number of queries escalated to external models',
    ['tier', 'reason']
)

# Results quality
findings_per_query_histogram = Histogram(
    'research_findings_per_query',
    'Number of findings collected per query'
)

sources_per_query_histogram = Histogram(
    'research_sources_per_query',
    'Number of sources referenced per query'
)
```

### Grafana Dashboard

Create dashboard panels for:
- Template selection distribution (pie chart)
- Query complexity distribution (histogram)
- Findings/Sources per query (time series)
- Cost per query (time series)
- External escalation rate (gauge)

---

## Troubleshooting Guide

### Issue: Template still selecting "product_research"

**Diagnosis:**
```bash
# Enable verbose logging
export LOG_LEVEL=DEBUG
export RESEARCH_VERBOSE=true

# Check template selection logs
docker logs kitty-brain-1 | grep -A 10 "Template selection"
```

**Fix:**
- Check template_selector.py is being imported
- Verify _disambiguate() rules are executing
- Add explicit test case for your query pattern

### Issue: Ollama decomposition timing out

**Diagnosis:**
```bash
# Test Ollama directly
curl http://localhost:11434/api/generate -d '{
  "model": "gpt-oss:120b",
  "prompt": "Test",
  "stream": false
}' --max-time 120
```

**Fix:**
- Increase OLLAMA_TIMEOUT_S in .env
- Check Ollama GPU layers: `ollama show gpt-oss:120b`
- Consider using "medium" think mode instead of "high"

### Issue: Still showing "N/A" in exports

**Diagnosis:**
```bash
# Check if state.to_export_dict() is being called
docker logs kitty-brain-1 | grep "export"

# Test export directly
python -c "
from services.brain.src.brain.research.state import ResearchState
state = ResearchState(session_id='test', query='test')
export = state.to_export_dict()
print(export['model_configuration'])
"
```

**Fix:**
- Verify state is populated before export
- Check export command is using state.to_export_dict()
- Ensure model_config is set during pipeline execution

### Issue: External models not being called

**Diagnosis:**
```bash
# Check complexity calculation
kitty-cli shell
> /verbosity 5
> omega [your complex query]

# Look for routing logs
docker logs kitty-brain-1 | grep -E "complexity|tier|escalat"
```

**Fix:**
- Verify "omega" password in prompt (or set AUTO_APPROVE_HIGH_COST=true for testing)
- Check RESEARCH_ENABLE_ESCALATION=true in .env
- Lower RESEARCH_CRITICAL_THRESHOLD if needed
- Verify API keys are set: OPENAI_API_KEY, ANTHROPIC_API_KEY

---

## Success Criteria

Before marking this integration complete, verify:

- [ ] Template selection accuracy: >95% on test queries
- [ ] No more "product_research" for ethics queries
- [ ] Decomposition produces 3-5 valid subtasks
- [ ] No "N/A" values in exported reports
- [ ] Complex queries trigger external models (cost > $0)
- [ ] Findings count: 25+ for complex queries (was 5)
- [ ] Sources count: 15+ for complex queries (was 6)
- [ ] No malformed queries (no "question?..." patterns)
- [ ] All unit tests passing
- [ ] All integration tests passing
- [ ] Manual test of original query shows improvement

---

## Estimated Implementation Time

- Phase 1 (Template Selection): 45 minutes
- Phase 2 (Query Decomposition): 1 hour
- Phase 3 (Metadata Capture): 30 minutes
- Phase 4 (External Escalation): 30 minutes
- Testing & Validation: 1 hour
- **Total: ~3.5 hours**

---

## References

- Original issue analysis: Research session `fd3a8ec4-d7df-4a92-951b-952c985bf2fb`
- KITT Architecture: https://github.com/Jmi2020/KITT
- LangGraph Documentation: https://langchain-ai.github.io/langgraph/
- Ollama API: https://github.com/ollama/ollama/blob/main/docs/api.md
- RAGAS Metrics: https://docs.ragas.io/en/stable/

---

## Contact

For questions or issues during integration:
- Check KITT troubleshooting docs: `docs/troubleshooting.md`
- Review logs: `.logs/brain.log`, `.logs/llamacpp-*.log`
- CLI debugging: `kitty-cli shell` with `/verbosity 5`

---

**Document Version:** 1.0  
**Last Updated:** 2025-11-21  
**Status:** Ready for Implementation
