
# Collective Meta-Agent — Operator Notes

**Routes**
- Gateway: `POST /api/collective/run`
- Agent Runtime: `POST /api/collective/run` (internal)

**Patterns**
- `pipeline` — uses coding graph if present, then judge synthesizes a final verdict
- `council` — K independent proposals (Q4/Athene), judged/summarized by F16 (GPT-OSS 120B)
- `debate` — PRO vs CON one-round debate, judged by F16

**Usage (CLI)**
```bash
kitty-cli say "/collective What's the best material for a 3D printed part at 80°C: PETG, ABS, or ASA?"
```

## Architecture (Option A: Token Budget System)

**Quality-First Strategy**: Prioritizes accuracy over speed. Designed for deep, recursive reasoning with 20-60 minute query times.

### Token Budgets

**Athene-V2 Specialists (Q4)** — 32k training context:
- Total: 24k prompt + 6-8k output = 30-32k
- System prompt: ~4k tokens
- Conversation summary: ~2k tokens
- KB chunks (auto-trimmed): ~10k tokens
- Task framing: ~2k tokens
- Output: 6-8k tokens

**GPT-OSS 120B Judge (F16)** — 128k context:
- Total: 100k prompt + 6-8k output = 106-108k
- Full KB context: ~35k tokens (no tag filtering)
- Specialist proposals: ~25k tokens (auto-trimmed)
- Conversation summary: ~2k tokens
- Tools: ~10k tokens
- System + task: ~6k tokens
- Output: 6-8k tokens

### Key Features

1. **KB Chunk Tagging**: All knowledge base chunks tagged with `[KB#id]` for evidence traceability
2. **Auto-Trimming**: Automatically trims KB context and proposals to fit token budgets
3. **Evidence Deduplication**: Judge tracks unique KB chunks cited by specialists
4. **Structured Synthesis**: 6-section prompt format for optimal judge reasoning:
   - Conversation Context
   - Task Description
   - Full Knowledge Base
   - Specialist Proposals (with KB citations)
   - Planning Context
   - Synthesis Instructions

### Models

- **Q4 (Athene-V2-Agent-Q4_K_M)**: Tool orchestrator, specialist proposals
  - Port: 8083
  - Context: 32k (training limit, strictly enforced)
  - Quantization: Q4_K_M

- **F16 (GPT-OSS 120B via Ollama)**: Deep reasoning judge with thinking mode
  - Model: `gpt-oss-120b-judge` (custom Modelfile with 131k context)
  - Context: 128k usable
  - Thinking mode: Enabled for deep synthesis

### Implementation Files

- `services/brain/src/brain/token_budgets.py` — Token budget management
- `services/brain/src/brain/agents/collective/graph_async.py` — Main graph with budget-aware nodes
- `services/brain/src/brain/agents/collective/context_policy.py` — KB context fetching with budgets
- `services/brain/src/brain/agents/collective/judge_prompts.py` — Structured prompt builder
- `ops/ollama/Modelfile.gpt-oss-120b-judge` — Judge model configuration

**Notes**
- Uses hybrid architecture: llama.cpp (Q4) + Ollama (GPT-OSS 120B)
- All proposals/judgments logged via existing Gateway/Brain audit patterns
- Token budgets prevent context overflow errors (HTTP 400/500)
