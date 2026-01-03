# KITT Autonomous Dataset Generation & Fine-Tuning System

## Objective
Extend KITT's existing autonomous research infrastructure to continuously harvest 
structured datasets from free academic sources, evaluate findings via collective 
reasoning, and produce domain-expert fine-tuned models—optimized for a Mac Studio 
M3 Ultra with 256GB unified memory.

## Phase 1: Architecture Planning (Output First)

Before implementation, generate comprehensive documentation including:

### 1.1 System Design Document
- **Integration Points**: Map new capabilities to existing infrastructure:
  - `services/brain/src/brain/research/graph/` (LangGraph research pipeline)
  - `services/brain/src/brain/research/extraction.py` (claim extraction)
  - `services/brain/src/brain/orchestration/parallel_manager.py` (agent coordination)
  - PostgreSQL checkpointing (fault tolerance)
  - Qdrant (semantic memory & deduplication)
  
- **Memory Budget Allocation** (256GB total):
  | Component | Allocation | Purpose |
  |-----------|------------|---------|
  | Research Model (GPTOSS 120B) | 80GB | Deep reasoning, paper analysis |
  | Collective (Q4 + GPTOSS 120B) | 100GB | Multi-agent evaluation |
  | Embeddings (BGE-M3) | 8GB | Semantic dedup & retrieval |
  | OS + Overhead | 40GB | System stability buffer |
  | Fine-tuning (QLoRA) | 28GB | On-demand, exclusive mode |

- **Disk Space Management**:
  - Set `RESEARCH_DISK_QUOTA_GB=500` soft limit
  - Monitor via `shutil.disk_usage()` before each harvest cycle
  - Alert at 80% quota, pause at 95%
  - Implement rolling compression: datasets older than 30 days → gzip
  - Store raw papers in MinIO with lifecycle policies

### 1.2 Data Flow Architecture
```
┌────────────────────────────────────────────────────────────────┐
│                    USER TOPIC SUBMISSION                        │
│   "quantum error correction", "sustainable battery chemistry"   │
└───────────────────────────┬────────────────────────────────────┘
                            ▼
┌────────────────────────────────────────────────────────────────┐
│              RESEARCH HARVESTER ( Deep Reasoner)             │
│                                                                  │
│  Sources (Free, Academic Priority):                             │
│  1. arXiv API (arxiv.org/api) - Papers, preprints              │
│  2. Semantic Scholar API (api.semanticscholar.org) - Citations │
│  3. PubMed Central (ncbi.nlm.nih.gov/pmc) - Biomedical         │
│  4. CORE API (core.ac.uk/api) - Open access aggregator         │
│  5. SearXNG (self-hosted) - Web fallback                       │
│                                                                  │
│  Extraction Pipeline:                                           │
│  Paper → PDF Parse → Section Extract → Claim Extract → Schema  │
└───────────────────────────┬────────────────────────────────────┘
                            ▼
┌────────────────────────────────────────────────────────────────┐
│              STRUCTURED DATASET ACCUMULATOR                     │
│                                                                  │
│  PostgreSQL Tables:                                             │
│  - research_papers (id, arxiv_id, title, abstract, full_text)  │
│  - extracted_claims (id, paper_id, claim, evidence, confidence)│
│  - dataset_entries (id, topic_id, instruction, input, output)  │
│  - training_batches (id, topic_id, entries[], status, created) │
│                                                                  │
│  Qdrant Collections:                                            │
│  - paper_embeddings (deduplication, semantic search)           │
│  - claim_embeddings (cross-reference, conflict detection)      │
└───────────────────────────┬────────────────────────────────────┘
                            ▼
┌────────────────────────────────────────────────────────────────┐
│         COLLECTIVE EVALUATION GATE (Context: 31,999 tokens)    │
│                                                                  │
│  Trigger: accumulated_tokens >= 28,000 (buffer for prompt)     │
│                                                                  │
│  Pre-Evaluation Protocol:                                       │
│  1. Research model saves state to PostgreSQL checkpoint        │
│  2. Research model unloads from memory (llama-server --unload) │
│  3. Wait 5s for memory release confirmation                    │
│  4. Load Collective agents (Q4 orchestrator + Deep evaluator)   │
│                                                                  │
│  Evaluation Criteria:                                           │
│  - Factual accuracy (cross-reference claims)                   │
│  - Novelty score (Jaccard distance from existing dataset)      │
│  - Coherence (internal consistency)                            │
│  - Citation quality (peer-reviewed preference)                 │
│                                                                  │
│  Output: ACCEPT (add to dataset) | REFINE (re-extract) | REJECT│
└───────────────────────────┬────────────────────────────────────┘
                            ▼
┌────────────────────────────────────────────────────────────────┐
│              DATASET MATURATION & FINE-TUNING                   │
│                                                                  │
│  Maturation Threshold:                                          │
│  - Minimum 5,000 high-quality instruction-output pairs         │
│  - Topic coverage score > 0.85 (knowledge gap detector)        │
│  - Claim conflict rate < 5%                                    │
│                                                                  │
│  Fine-Tuning Pipeline (Exclusive Memory Mode):                  │
│  1. Export dataset to Alpaca/ShareGPT JSON format              │
│  2. Unload ALL inference models                                │
│  3. Run QLoRA fine-tune via mlx-lm or llama.cpp train          │
│  4. Base model: Llama 3.3 8B (fits in 28GB with QLoRA)         │
│  5. Output: LoRA adapter → merge → GGUF Q4_K_M                 │
│  6. Register new expert model in KITT model registry           │
└────────────────────────────────────────────────────────────────┘
```

## Phase 2: Implementation Specifications

### 2.1 Academic Source Integration

Create `services/brain/src/brain/research/sources/` with:
```python
# academic_sources.py
class AcademicSourceRegistry:
    """Priority-ordered academic paper sources (all free tier)."""
    
    SOURCES = [
        ArxivSource(
            base_url="http://export.arxiv.org/api/query",
            rate_limit=3,  # requests per second
            categories=["cs.AI", "cs.LG", "cs.CL", "q-bio", "cond-mat"],
        ),
        SemanticScholarSource(
            base_url="https://api.semanticscholar.org/graph/v1",
            api_key=os.getenv("SEMANTIC_SCHOLAR_API_KEY"),  # Free tier: 100/5min
            fields=["title", "abstract", "year", "citationCount", "openAccessPdf"],
        ),
        PubMedCentralSource(
            base_url="https://eutils.ncbi.nlm.nih.gov/entrez/eutils",
            api_key=os.getenv("NCBI_API_KEY"),  # Free: 10/sec with key
        ),
        CORESource(
            base_url="https://api.core.ac.uk/v3",
            api_key=os.getenv("CORE_API_KEY"),  # Free tier available
        ),
    ]
```

### 2.2 Structured Extraction Schema
```python
# extraction_schemas.py
from pydantic import BaseModel, Field
from typing import List, Optional
from enum import Enum

class ClaimType(str, Enum):
    FINDING = "finding"           # Experimental result
    METHOD = "method"             # Technique description
    DEFINITION = "definition"     # Concept explanation
    COMPARISON = "comparison"     # A vs B analysis
    LIMITATION = "limitation"     # Known constraints

class ExtractedClaim(BaseModel):
    claim: str = Field(..., description="Atomic factual statement")
    claim_type: ClaimType
    evidence: str = Field(..., description="Supporting quote from paper")
    section: str = Field(..., description="Paper section: abstract|intro|methods|results|discussion")
    confidence: float = Field(ge=0.0, le=1.0)
    citations: List[str] = Field(default_factory=list)

class DatasetEntry(BaseModel):
    """Alpaca-format training example."""
    instruction: str = Field(..., description="Task description or question")
    input: str = Field(default="", description="Optional context")
    output: str = Field(..., description="Expected response")
    source_paper_ids: List[str]
    topic: str
    quality_score: float
```

### 2.3 Memory-Aware Scheduling
```python
# memory_scheduler.py
import subprocess
import asyncio

class ResearchMemoryScheduler:
    """Coordinates model loading/unloading for memory-constrained execution."""
    
    RESEARCH_MODE_MODELS = ["GPTOSS 120B"]  # 80GB
    COLLECTIVE_MODE_MODELS = ["athene-q4", "GPTOSS 120B"]  # 100GB total
    FINETUNE_MODE_MODELS = []  # All unloaded, mlx-lm uses Metal directly
    
    async def enter_collective_mode(self):
        """Unload research model, prepare for collective evaluation."""
        # 1. Checkpoint current research state
        await self.checkpoint_research_state()
        
        # 2. Unload Deep research model
        await self._unload_model("kitty-Deep")
        
        # 3. Wait for memory release
        await asyncio.sleep(5)
        
        # 4. Verify memory available
        available_gb = self._get_available_memory_gb()
        if available_gb < 100:
            raise MemoryError(f"Insufficient memory for collective: {available_gb}GB")
        
        # 5. Load collective agents
        await self._load_model("kitty-q4", port=8082)
        await self._load_model("kitty-Deep",)
    
    async def enter_finetune_mode(self):
        """Unload ALL models for exclusive fine-tuning."""
        for port in [8082, 8084, 8085, 8086]:
            await self._unload_model(f"port-{port}", port=port)
        
        await asyncio.sleep(10)  # Allow full memory release
        
        available_gb = self._get_available_memory_gb()
        if available_gb < 200:
            raise MemoryError(f"Need 200GB for fine-tuning, have {available_gb}GB")
```

### 2.4 Collective Evaluation Protocol
```python
# collective_evaluator.py
class CollectiveDatasetEvaluator:
    """Multi-agent evaluation of harvested research data."""
    
    CONTEXT_LIMIT = 31999
    PROMPT_OVERHEAD = 4000  # System prompt + formatting
    BATCH_TOKEN_TARGET = 28000
    
    async def evaluate_batch(self, claims: List[ExtractedClaim]) -> List[EvaluationResult]:
        """Evaluate claims via mixture-of-agents debate."""
        
        # Pack claims into context-limited batches
        batches = self._pack_into_batches(claims, self.BATCH_TOKEN_TARGET)
        
        results = []
        for batch in batches:
            # Round 1: Independent evaluation by each agent
            evaluations = await asyncio.gather(
                self._evaluate_accuracy(batch),      # Q4 agent
                self._evaluate_novelty(batch),       # Q4 agent  
                self._evaluate_coherence(batch),     # Deep agent
            )
            
            # Round 2: Synthesis and final judgment
            final = await self._synthesize_judgments(batch, evaluations)
            results.extend(final)
        
        return results
    
    async def _evaluate_novelty(self, claims: List[ExtractedClaim]) -> dict:
        """Check claims against existing dataset for novelty."""
        existing_embeddings = await self.qdrant.search(
            collection="dataset_claims",
            query_vectors=[c.embedding for c in claims],
            limit=5
        )
        
        novelty_scores = []
        for claim, matches in zip(claims, existing_embeddings):
            max_similarity = max(m.score for m in matches) if matches else 0
            novelty = 1.0 - max_similarity  # Higher = more novel
            novelty_scores.append(novelty)
        
        return {"novelty_scores": novelty_scores}
```

### 2.5 Fine-Tuning Integration
```python
# finetune_pipeline.py
class LocalFineTuningPipeline:
    """QLoRA fine-tuning on Mac Studio via mlx-lm or llama.cpp."""
    
    BASE_MODEL = "mlx-community/Llama-3.2-8B-Instruct-4bit"
    OUTPUT_DIR = "/Users/Shared/KITT/models/experts"
    
    async def train_expert(self, topic: str, dataset_path: str):
        """Fine-tune a domain expert model."""
        
        # 1. Enter exclusive fine-tuning mode
        await self.memory_scheduler.enter_finetune_mode()
        
        # 2. Validate dataset
        dataset = self._load_and_validate(dataset_path)
        if len(dataset) < 5000:
            raise ValueError(f"Dataset too small: {len(dataset)} < 5000 required")
        
        # 3. Run QLoRA training via mlx-lm
        model_name = f"kitt-expert-{topic.replace(' ', '-')}"
        
        cmd = [
            "python", "-m", "mlx_lm.lora",
            "--model", self.BASE_MODEL,
            "--train",
            "--data", dataset_path,
            "--batch-size", "4",
            "--lora-layers", "16",
            "--iters", "1000",
            "--adapter-path", f"{self.OUTPUT_DIR}/{model_name}/adapters",
        ]
        
        process = await asyncio.create_subprocess_exec(*cmd)
        await process.wait()
        
        # 4. Fuse adapters and export GGUF
        await self._fuse_and_export(model_name)
        
        # 5. Register in KITT model registry
        await self._register_expert_model(model_name, topic)
```

### 2.6 Disk Space Management
```python
# disk_manager.py
class ResearchDiskManager:
    """Prevent disk exhaustion during long-running research."""
    
    QUOTA_GB = int(os.getenv("RESEARCH_DISK_QUOTA_GB", 500))
    WARN_THRESHOLD = 0.80
    PAUSE_THRESHOLD = 0.95
    
    STORAGE_PATHS = {
        "papers": "/Users/Shared/KITT/data/papers",
        "datasets": "/Users/Shared/KITT/data/datasets", 
        "models": "/Users/Shared/KITT/models/experts",
        "checkpoints": "/Users/Shared/KITT/data/checkpoints",
    }
    
    def check_quota(self) -> tuple[float, str]:
        """Returns (usage_ratio, status)."""
        total_used_gb = sum(
            self._get_dir_size_gb(path) 
            for path in self.STORAGE_PATHS.values()
        )
        
        ratio = total_used_gb / self.QUOTA_GB
        
        if ratio >= self.PAUSE_THRESHOLD:
            return ratio, "PAUSE"
        elif ratio >= self.WARN_THRESHOLD:
            return ratio, "WARN"
        return ratio, "OK"
    
    async def cleanup_old_data(self, days_old: int = 30):
        """Compress papers older than threshold."""
        # Implementation: gzip old PDFs, prune checkpoint history
```

## Phase 3: Configuration & Environment

### 3.1 Environment Variables
```bash
# .env additions for research-to-finetune pipeline
RESEARCH_DISK_QUOTA_GB=500
RESEARCH_CONTEXT_LIMIT=31999
RESEARCH_BATCH_TOKEN_TARGET=28000
RESEARCH_MIN_DATASET_SIZE=5000
RESEARCH_MATURATION_THRESHOLD=0.85

# Academic API keys (all free tier)
SEMANTIC_SCHOLAR_API_KEY=your_key_here
NCBI_API_KEY=your_key_here
CORE_API_KEY=your_key_here

# Fine-tuning config
FINETUNE_BASE_MODEL=mlx-community/Llama-3.2-8B-Instruct-4bit
FINETUNE_LORA_RANK=16
FINETUNE_BATCH_SIZE=4
```

### 3.2 Database Migrations
```sql
-- migrations/007_dataset_generation.sql
CREATE TABLE research_topics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    status VARCHAR(50) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT NOW(),
    papers_harvested INTEGER DEFAULT 0,
    claims_extracted INTEGER DEFAULT 0,
    dataset_entries INTEGER DEFAULT 0,
    maturation_score FLOAT DEFAULT 0.0
);

CREATE TABLE training_datasets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    topic_id UUID REFERENCES research_topics(id),
    format VARCHAR(50) DEFAULT 'alpaca',
    entry_count INTEGER,
    file_path TEXT,
    quality_score FLOAT,
    created_at TIMESTAMP DEFAULT NOW(),
    fine_tuned_model TEXT
);

CREATE TABLE expert_models (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,
    topic_id UUID REFERENCES research_topics(id),
    base_model TEXT,
    adapter_path TEXT,
    gguf_path TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    registered_in_kitt BOOLEAN DEFAULT FALSE
);
```

## Phase 4: Operational Workflows

### 4.1 Starting a Research Topic
```bash
# Via KITT CLI
kitty research topic create "quantum error correction" \
  --sources arxiv,semantic_scholar \
  --categories cs.IT,quant-ph \
  --min-citations 10 \
  --max-papers 500

# Via API
POST /api/research/topics
{
  "name": "quantum error correction",
  "sources": ["arxiv", "semantic_scholar"],
  "filters": {
    "categories": ["cs.IT", "quant-ph"],
    "min_citations": 10,
    "date_range": "2020-01-01:2025-01-01"
  },
  "target_papers": 500,
  "auto_finetune": true
}
```

### 4.2 Monitoring Progress
```bash
# Check topic status
kitty research topic status "quantum error correction"

# Output:
# Topic: quantum error correction
# Status: harvesting
# Papers: 347/500
# Claims: 4,892
# Dataset Entries: 3,421
# Maturation: 0.68 (target: 0.85)
# Disk Usage: 2.3 GB
# Next Collective Eval: 1,579 tokens remaining
```

### 4.3 Triggering Fine-Tuning
```bash
# Manual trigger (if auto_finetune=false)
kitty research topic finetune "quantum error correction"

# Status check
kitty models list --experts
# Output:
# kitt-expert-quantum-error-correction  (8B Q4_K_M, trained 2025-01-02)
```

## Success Criteria

1. **Harvesting**: 500+ papers/topic from free academic sources
2. **Extraction**: 90%+ claim extraction success rate
3. **Evaluation**: Collective approves >70% of claims
4. **Dataset**: 5,000+ high-quality instruction-output pairs per topic
5. **Fine-Tuning**: Successfully produces working GGUF expert model
6. **Memory**: No OOM errors during mode transitions
7. **Disk**: Never exceeds 95% quota threshold
8. **Recovery**: Resumes from checkpoint after any interruption

## References

- Existing research architecture: `Research/AutonomousResearch_COMPLETE.md`
- Parallel execution: `Research/ParallelAgentExecution.md`
- Free search tools: `Research/Web_searchTooloptions.md`
- Memory patterns: `Research/mcp-memory-server-guide.md`