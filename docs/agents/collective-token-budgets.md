# Collective Meta-Agent Token Budget System (Option A)

## Overview

The collective meta-agent uses an explicit token budget system to prevent context overflow errors while maximizing accuracy. This document explains the implementation architecture.

## Problem Statement

**Original Issue**: Athene-V2-Agent has a 32k training context limit. llama-server enforces this limit at the slot level, preventing any request from exceeding the model's training context regardless of `--ctx-size` flags.

**Failed Approaches**:
- Increasing `--ctx-size` to 128k → slots capped at 32k
- RoPE scaling with YaRN → slots still capped
- `--override-kv` metadata override → ignored by slot cap

**Root Cause**: Hardcoded safety check in llama-server:
```c
if (slot_ctx > model_training_ctx) {
    slot_ctx = model_training_ctx;  // Cap at 32k
}
```

## Solution: Option A Architecture

Accept Athene's natural 32k limit and work within it using explicit token budgets, while giving GPT-OSS 120B full 128k context for synthesis.

### Design Principles

1. **Quality over Speed**: User prioritizes accuracy; willing to accept 20-60 minute query times
2. **Explicit Budgets**: Each component has defined token allocation
3. **Auto-Trimming**: Automatically trim KB chunks and proposals to fit
4. **Evidence Traceability**: Tag KB chunks with IDs for citation tracking
5. **Hybrid Architecture**: llama.cpp (Athene) + Ollama (GPT-OSS)

## Token Budget Breakdown

### Athene-V2 Specialists (32k limit)

```
Total Context: 32,768 tokens
├─ Prompt Budget: 24,000 tokens
│  ├─ System prompt:         4,000 tokens
│  ├─ Conversation summary:  2,000 tokens
│  ├─ KB chunks (trimmed):  10,000 tokens
│  ├─ Task framing:          2,000 tokens
│  ├─ Tools (if enabled):    4,000 tokens
│  └─ Safety margin:         2,000 tokens
└─ Output Budget:            6,000-8,000 tokens
   Total Used:              30,000-32,000 tokens
```

### GPT-OSS 120B Judge (128k context)

```
Total Context: 131,072 tokens
├─ Prompt Budget: 100,000 tokens
│  ├─ System prompt:         4,000 tokens
│  ├─ Conversation summary:  2,000 tokens
│  ├─ KB chunks (full):     35,000 tokens
│  ├─ Specialist proposals: 25,000 tokens
│  ├─ Evidence aggregation: 15,000 tokens
│  ├─ Task framing:          2,000 tokens
│  ├─ Tools:                10,000 tokens
│  └─ Safety margin:         7,000 tokens
└─ Output Budget:            6,000-8,000 tokens
   Total Used:             106,000-108,000 tokens
```

## Implementation Components

### 1. TokenBudgetManager (`brain/token_budgets.py`)

**Core Responsibilities**:
- Token estimation (char/4 approximation)
- Budget validation for Athene and Judge
- Auto-trimming text to fit budgets
- Conversation summarization

**Key Classes**:

```python
class BudgetAllocation:
    """Tracks token usage for a single component."""
    component: str
    allocated_tokens: int
    actual_tokens: int
    overflow: bool

class ModelBudget:
    """Complete budget for a model."""
    model_name: str
    total_context: int
    prompt_budget: int
    output_budget: int
    allocations: Dict[str, int]

class TokenBudgetManager:
    """Manages all token budgets."""
    ATHENE_BUDGET: ModelBudget
    JUDGE_BUDGET: ModelBudget

    @staticmethod
    def estimate_tokens(text: str) -> int

    @classmethod
    def check_athene_budget(...) -> Tuple[bool, List[BudgetAllocation]]

    @classmethod
    def check_judge_budget(...) -> Tuple[bool, List[BudgetAllocation]]

    @staticmethod
    def trim_to_budget(text: str, budget_tokens: int, preserve_end: bool)
```

**Token Estimation**:
- Uses simple char/4 approximation
- Conservative for English text
- Reasonably accurate for Qwen/Llama tokenizers
- TODO: Could use tiktoken for exact counts

### 2. Budget-Aware Context Fetching (`brain/agents/collective/context_policy.py`)

**Enhanced `fetch_domain_context()`**:

```python
def fetch_domain_context(
    query: str,
    limit: int = 6,
    for_proposer: bool = True,
    token_budget: Optional[int] = None  # NEW
) -> str:
    """Fetch KB context with optional token budget."""
```

**Features**:
- KB chunk ID tagging: `[KB#mem_123]`
- Smart trimming: keeps highest-scoring chunks
- Budget enforcement: auto-trims when exceeded
- Tag filtering: proposers get filtered, judge gets full access

**Example Output**:
```
[Context trimmed to 8500/10000 tokens, showing 5/20 chunks]

[KB#mem_123] [Score: 0.85] PETG has a glass transition temperature of 75-80°C...
[KB#mem_456] [Score: 0.82] ABS provides better heat resistance up to 95°C...
[KB#mem_789] [Score: 0.78] Annealing PETG can increase heat resistance...
```

### 3. Athene Specialist Nodes (`brain/agents/collective/graph_async.py`)

**Budget-Aware Council**:

```python
async def n_propose_council(s: CollectiveState) -> CollectiveState:
    # Get conversation summary (2k budget)
    conv_summary = summarize_conversation(
        conversation_history,
        max_tokens=2000
    )

    # Fetch KB context (10k budget, auto-trimmed)
    context = fetch_domain_context(
        s["task"],
        limit=10,
        for_proposer=True,
        token_budget=10000
    )

    # Check budget before calling
    budget_ok, allocations = TokenBudgetManager.check_athene_budget(
        system_prompt=system_prompt,
        conversation_summary=conv_summary,
        kb_chunks=context,
        task_query=s['task'],
        tools_json=None
    )

    if not budget_ok:
        logger.warning(f"Specialist {i+1} budget overflow detected")
        TokenBudgetManager.log_budget_status(allocations, f"Specialist_{i+1}")

    # Generate proposal (6-8k output)
    response, metadata = await chat_async([...],
        which="Q4",
        max_tokens=6000
    )
```

**Structured Output with KB Citations**:
Specialists are prompted to cite KB chunks:
```
Based on [KB#mem_123], PETG can withstand temperatures up to 75°C.
However, [KB#mem_456] indicates that ABS performs better at 80°C...
```

### 4. GPT-OSS Judge with Structured Prompts (`brain/agents/collective/judge_prompts.py`)

**6-Section Prompt Structure**:

```python
def build_judge_user_prompt(
    task: str,
    conversation_summary: str,
    kb_context: str,
    proposals: List[str],
    plan_logs: Optional[str] = None
) -> str:
    """
    1. Conversation Context  (~2k tokens)
    2. Task Description      (~2k tokens)
    3. Knowledge Base        (~35k tokens, full access)
    4. Specialist Proposals  (~25k tokens, with KB citations)
    5. Planning Context      (~variable)
    6. Synthesis Instructions
    """
```

**Evidence Deduplication**:

```python
def deduplicate_kb_references(proposals: List[str]) -> Set[str]:
    """Extract unique KB chunk IDs cited by specialists."""
    pattern = r'\[KB#([\w\-]+)\]'
    kb_refs = set()
    for proposal in proposals:
        matches = re.findall(pattern, proposal)
        kb_refs.update(matches)
    return kb_refs
```

**Judge Node Implementation**:

```python
async def n_judge(s: CollectiveState) -> CollectiveState:
    # Fetch full KB context (35k budget)
    full_context = fetch_domain_context(
        s["task"],
        limit=20,
        for_proposer=False,  # Full tag access
        token_budget=35000
    )

    # Trim proposals if needed (25k budget)
    proposals = trim_proposals_to_budget(
        s.get("proposals", []),
        max_tokens=25000
    )

    # Track KB references
    kb_refs = deduplicate_kb_references(proposals)
    logger.info(f"Judge analyzing {len(kb_refs)} unique KB chunks")

    # Build structured prompts
    system_prompt = build_judge_system_prompt(s.get("pattern"))
    user_prompt = build_judge_user_prompt(
        task=s["task"],
        conversation_summary=conv_summary,
        kb_context=full_context,
        proposals=proposals,
        plan_logs=s.get("logs")
    )

    # Validate budget
    budget_ok = check_judge_prompt_budget(
        system_prompt,
        user_prompt,
        tools_json
    )

    # Call with tools (6-8k output)
    verdict, metadata = await chat_async([...],
        which="F16",
        tools=tools_list,
        max_tokens=6000
    )
```

### 5. Ollama Judge Model (`ops/ollama/Modelfile.gpt-oss-120b-judge`)

**Model Configuration**:

```dockerfile
FROM gpt-oss:120b

# Set 131k context window
PARAMETER num_ctx 131072

# Balanced synthesis parameters
PARAMETER temperature 0.7
PARAMETER top_p 0.9

SYSTEM """You are GPT-OSS 120B Judge, KITTY's deliberation synthesizer.

Your role:
- Review all specialist proposals with full context access
- Use thinking mode to deeply analyze evidence and arguments
- Call tools to verify claims or gather additional context
- Synthesize a final verdict that integrates the best ideas
- Ensure safety, clarity, and testability in recommendations
"""
```

**Building the Model**:
```bash
ollama create gpt-oss-120b-judge -f ops/ollama/Modelfile.gpt-oss-120b-judge
```

**Environment Configuration** (`.env`):
```bash
# Ollama GPT-OSS reasoner
OLLAMA_MODEL=gpt-oss-120b-judge  # Custom model with 131k context
OLLAMA_THINK=high                # Enable thinking mode
LOCAL_REASONER_PROVIDER=ollama   # Use Ollama for F16 judge
```

## Workflow Example

1. **User Query**: `/collective What's best for 80°C parts: PETG or ABS?`

2. **Planning** (n_plan with Q4):
   - Budget: ~6k tokens total
   - Output: High-level deliberation strategy

3. **Specialist Proposals** (n_propose_council with Q4):
   - K=3 specialists run in parallel
   - Each gets:
     - Conversation summary (2k)
     - KB chunks (10k, auto-trimmed)
     - Task query (2k)
   - Each outputs 6-8k token proposal
   - KB citations: `Based on [KB#mem_456], ABS performs better...`

4. **Judge Synthesis** (n_judge with GPT-OSS 120B):
   - Receives:
     - Full KB context (35k tokens)
     - All 3 proposals (25k total, trimmed if needed)
     - Conversation summary (2k)
   - Deduplicates KB references: `{mem_123, mem_456, mem_789}`
   - Uses structured 6-section prompt
   - May call tools for verification
   - Outputs final verdict (6-8k tokens)

## Budget Enforcement Logging

**Athene Specialist Log Example**:
```
=== Specialist_1 Budget Status ===
  ✓ system_prompt: 3500/4000 (87.5%)
  ✓ conversation_summary: 1800/2000 (90.0%)
  ✓ kb_chunks: 9200/10000 (92.0%)
  ✓ task_framing: 1900/2000 (95.0%)
  Total: 16400 tokens
```

**Judge Budget Log Example**:
```
Judge prompt within budget: 98500/100000 tokens

Judge analyzing 8 unique KB chunks cited by specialists:
{mem_123, mem_456, mem_789, mem_234, mem_567, mem_890, mem_345, mem_678}
```

## Testing

### Unit Tests (`services/brain/tests/test_token_budgets.py`)

**Coverage** (21 tests, all passing):
- Token estimation
- Budget allocation tracking
- Athene budget validation
- Judge budget validation
- Text trimming (preserve beginning/end)
- Conversation summarization
- KB deduplication
- Proposal trimming
- Model budget overflow detection

**Run Tests**:
```bash
cd services/brain
python -m pytest tests/test_token_budgets.py -v
```

### Smoke Test (`tests/test_collective_smoke.sh`)

**Validates**:
1. Collective council completes without HTTP 400/500 errors
2. Budget logging appears in logs
3. Q4 server health
4. gpt-oss-120b-judge model exists

**Run Smoke Test**:
```bash
./tests/test_collective_smoke.sh
```

## Migration Notes

### From Previous Implementation

**Before** (failed with HTTP 400):
- No explicit budgets
- KB context: 6 entries (uncontrolled size)
- Tools enabled for all nodes (added 6k tokens each)
- No auto-trimming
- Total: Often exceeded 32k → HTTP 400

**After** (Option A):
- Explicit budgets per node
- KB context: Auto-trimmed to 10k (Athene) / 35k (Judge)
- Tools only for judge
- Smart trimming keeps best content
- Total: Guaranteed within limits

### Configuration Changes

**`.env` Updates**:
```bash
# Before
OLLAMA_MODEL=gpt-oss:120b

# After
OLLAMA_MODEL=gpt-oss-120b-judge  # Custom model with 131k context
```

## Future Enhancements

1. **Exact Token Counting**: Replace char/4 estimation with tiktoken
2. **Dynamic Budgets**: Adjust based on query complexity
3. **Recursive Tool Calling**: Multi-round verification for specialists
4. **Hierarchical Summarization**: LLM-based conversation compression
5. **Budget Analytics**: Track budget utilization patterns
6. **Adaptive Trimming**: Learn which KB chunks provide most value

## References

- Research Document: `/Users/Shared/Coding/KITT/Research/option_a_athene_gptoss_ollama_guide.md`
- Operator Notes: `/Users/Shared/Coding/KITT/docs/agents/collective.md`
- Implementation: `services/brain/src/brain/agents/collective/`
- Tests: `services/brain/tests/test_token_budgets.py`

## Support

For issues or questions:
1. Check logs: `.logs/llamacpp-q4.log` for Athene budget status
2. Validate model: `ollama list | grep gpt-oss-120b-judge`
3. Run tests: `pytest tests/test_token_budgets.py -v`
4. Run smoke test: `./tests/test_collective_smoke.sh`
