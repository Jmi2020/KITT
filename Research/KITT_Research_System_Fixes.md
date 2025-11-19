# KITT Research System — Evidence‑First Fixes & Code Patches

**Version:** 1.0  
**Date:** 2025-11-18

This document provides **concrete, drop‑in fixes** to make KITT’s outputs *usable, verifiable, and decision‑ready*.  
It’s organized as: Quick‑Start checklist → Architecture changes → Code patches → Prompts → SQL migrations → Scoring/Stopping → UI/Observability → Local evaluation harness → References.

---

## ⚠️ Current State & Critical Blockers

**Status as of 2025-11-18:** The research pipeline executes but has a **critical blocker** that must be fixed before implementing enhancements below.

### 🔴 BLOCKER: Claim Extraction Not Executing

**File:** `services/brain/src/brain/research/graph/nodes.py` (lines 840-895)

**Symptom:** Research sessions complete with **0 claims extracted** despite:
- Fetching 7,000+ chars of content per session ✅
- Web search working correctly ✅
- Webpage fetching working correctly ✅
- Code changes to `extraction.py` being ignored ❌

**Evidence:**
```
[INFO] 🔬 Starting claim extraction for finding...    ✅ Line 846 executes
[DEBUG] DEBUG_CLAIM_2: source_id = ...                ✅ Line 853 executes

MISSING (physically impossible):
❌ Line 847: print("PRINT: Line 847 executing")
❌ Line 848: logger.info("DEBUG_CLAIM_1")
❌ Line 849: logger.info("DEBUG_CLAIM_1b")
❌ Lines 857-897: All subsequent debug logs
❌ extraction.py never executes (no logs from extract_claims_from_content)
```

**Investigation Completed:**
- ✅ Python 3.13 upgrade (container and host aligned)
- ✅ Bytecode files deleted (all `__pycache__` removed)
- ✅ Container restarted multiple times
- ✅ Code verified in both host and container filesystems
- ✅ Bind mount working (`/Users/Shared/Coding/KITT/services/brain` → `/app/services/brain`)

**Root Cause Hypothesis:**
1. **Uvicorn worker module caching** - Container runs with `--workers 2`; workers may cache imports
2. **Python sys.modules caching** - Module cache persists across requests
3. **Hidden code path** - Execution jumping from line 846 → 853 suggests alternative code being run

**Next Steps to Unblock:**
1. Try single worker: Change docker command to remove `--workers 2`
2. Force rebuild: `docker compose build --no-cache brain`
3. Add module reload logic to force Python to reload changed files
4. Investigate if LangGraph has its own code caching mechanism

**Impact:** Cannot implement evidence-first extraction (§ Extraction & Verification) until base claim extraction works.

**References:**
- Full debugging details: `Research/claim_extraction_investigation_session2.md`
- Architecture documentation: `Research/research_pipeline_architecture.md`

---

## 🔌 Quick‑Start PR Checklist

Apply changes in the following order (each item links to a section with code):

1. **Introduce a structured `Claim` & `EvidenceSpan` type** → enables quote‑first, verifiable findings.  
   Path: `services/brain/src/brain/research/types.py` → [§ Types](#-types-claim--evidence)
2. **Upgrade query generation** with operator‑rich patterns and diversification.  
   Path: `.../graph/nodes.py` (`generate_queries`) → [§ Prompt: Query Generation](#-prompt-query-generation)
3. **Hybrid retrieval with cross‑encoder reranking** + domain dedupe.  
   Path: `.../graph/nodes.py` (`execute_tools`) → [§ Retrieval Enhancements](#-retrieval-enhancements-hybrid--reranking)
4. **Evidence‑first extraction** (atomic claims with verbatim quotes) + **NLI entailment verifier**.  
   Path: `.../graph/nodes.py` (`analyze_results`) → [§ Extraction & Verification](#-extraction--verification-evidence-first--nli)
5. **Hierarchical decomposition with deliverables** (`expected_artifacts`, `answerability`).  
   Path: `.../graph/nodes.py` (`decompose`) → [§ Prompt: Decomposition](#-prompt-decomposition-with-artifacts)
6. **Composite confidence & stronger stopping criteria** (coverage & novelty).  
   Path: `.../graph/nodes.py` (`check_stopping_criteria`) → [§ Scoring & Stopping](#-scoring--stopping-criteria)
7. **Structured synthesis** (bullets, quotes, citations, gaps).  
   Path: `.../graph/nodes.py` (`synthesize_sub_question`, `meta_synthesize`) → [§ Prompt: Synthesis](#-prompt-synthesis-structure--citations)
8. **Persist the claim graph** (claims & evidence tables).  
   Path: `.../sql/020_claim_graph.sql` + `session_manager.py` → [§ SQL Migrations](#-sql-migrations-claim-graph)
9. **Task‑aware model routing & temperature schedule**.  
   Path: `.../strategy/*` + `ModelCoordinator` → [§ Task‑Aware Routing](#-task-aware-model-routing)
10. **Results UI**: claim bullets with citation badges; artifacts tabs; gaps card.  
    Path: `services/ui/src/pages/Research.tsx` → [§ Results UI](#-results-ui-for-usable-answers)

---

## 🧱 Types (Claim & Evidence)

**File:** `services/brain/src/brain/research/types.py`

```python
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class EvidenceSpan:
    source_id: str
    url: str
    title: str
    quote: str
    char_start: Optional[int] = None
    char_end: Optional[int] = None

@dataclass
class Claim:
    id: str
    session_id: str
    sub_question_id: Optional[str]
    text: str
    evidence: List[EvidenceSpan]
    entailment_score: float           # 0..1 (NLI)
    provenance_score: float           # quote coverage / lexical overlap
    dedupe_fingerprint: str           # for clustering identical claims
    confidence: float = 0.0
```

---

## 🔎 Prompt: Query Generation

**File:** `services/brain/src/brain/research/graph/nodes.py` (`generate_queries`)

**Goal:** diversify with patterns & operators; add temporal filters.

```python
QUERY_GEN_SYSTEM = """Generate 6–12 diverse, operator-rich queries for the sub-question.
Patterns: definition, metrics/measurement, confounders, comparison, timeline, site:, filetype:, after:/before:.
Return strict JSON: { "queries":[ { "text":"...", "intent":"definition|metrics|compare|timeline|site|filetype|news" } ] }.
Avoid duplicates; vary vocabulary; target authoritative sources."""
```

Example pattern expansion:

```python
def make_queries(topic: str) -> list[dict]:
    patterns = [
        "{t} definition operationalize",
        "{t} measurement metrics framework",
        "{t} confounders control variables",
        "{t} comparison alternatives pros cons",
        "site:.gov {t}",
        "site:.edu {t} review",
        "filetype:pdf literature review {t}",
        "{t} after:2022 methodology"
    ]
    base = [{ "text": p.format(t=topic), "intent": "pattern" } for p in patterns]
    return diversify(base, beam=3, jitter=True)  # implement small beam/jitter
```

Helpful research operator guides: 🔎 [Advanced operators](https://www.google.com/search?q=advanced+google+operators+site+filetype+after+before).

---

## 🛰 Retrieval Enhancements (Hybrid + Reranking)

**File:** `services/brain/src/brain/research/graph/nodes.py` (`execute_tools`)

**Goal:** combine lexical (BM25) + dense; **cross‑encoder rerank**; domain dedupe.

```python
# Pseudocode inside execute_tools
candidates = []
for q in queries:
    r = await tool_executor.execute_tool("web_search", {"query": q["text"]})
    candidates.extend(r)

# Limit initial pool, then rerank via cross encoder
pool = dedupe_urls(candidates)[:150]
scored = cross_encoder_rerank(user_query, pool)  # local CE (e.g., ms-marco MiniLM)
ranked = dedupe_by_domain(scored)[:k]            # e.g., k=12; avoid host bias
```

References: 🔍 [BM25 + dense + cross‑encoder reranking](https://www.google.com/search?q=hybrid+search+bm25+dense+reranking+best+practices).

---

## 🧲 Extraction & Verification (Evidence‑First + NLI)

**File:** `services/brain/src/brain/research/graph/nodes.py` (`analyze_results`)

**Goal:** extract **atomic claims with verbatim quotes**; verify with local NLI; compute fingerprints.

```python
import hashlib, uuid

def fingerprint(text: str) -> str:
    return hashlib.sha1(text.strip().lower().encode()).hexdigest()[:16]

def provenance(claim_text: str, quotes: list[str]) -> float:
    # simple lexical coverage proxy 0..1
    import re
    key = set([w for w in re.findall(r"[a-z0-9]+", claim_text.lower()) if len(w) > 3])
    hits = sum(1 for w in key if any(w in q.lower() for q in quotes))
    return hits / max(1, len(key))

def extract_claims_with_quotes(doc) -> list[Claim]:
    prompt = f"""
Extract atomic claims **only** when directly supported by verbatim quotes from the passage.
Return JSON: [{{"claim":"...", "quotes":[{{"text":"...", "char_start":0, "char_end":10}}]}}]
PASSAGE:
{doc.text}
"""
    out = call_llm("extractor", prompt, temp=0)
    claims = []
    for c in out:
        quotes = [q["text"] for q in c["quotes"]]
        claims.append(Claim(
            id=uuid.uuid4().hex,
            session_id=state["session_id"],
            sub_question_id=state.get("current_sub_question_id"),
            text=c["claim"],
            evidence=[EvidenceSpan(source_id=doc.id, url=doc.url, title=doc.title,
                                   quote=q["text"], char_start=q.get("char_start"),
                                   char_end=q.get("char_end")) for q in c["quotes"]],
            entailment_score=0.0,
            provenance_score=provenance(c["claim"], quotes),
            dedupe_fingerprint=fingerprint(c["claim"])
        ))
    return claims

def verify_claims_entailment(claims: list[Claim]) -> list[Claim]:
    for cl in claims:
        premise = " ".join([e.quote for e in cl.evidence])[:4000]
        cl.entailment_score = nli_entails(premise=premise, hypothesis=cl.text)  # local NLI
    return claims

# In analyze_results:
all_claims = []
for doc in ranked_docs:
    all_claims += extract_claims_with_quotes(doc)
all_claims = cluster_and_dedupe(all_claims)               # merge by fingerprint
all_claims = verify_claims_entailment(all_claims)
state["claims"].extend(all_claims)
```

NLI background: 🧪 [Entailment for verification](https://www.google.com/search?q=roberta+mnli+entailment+verification+rag).

---

## 🧭 Prompt: Decomposition with Artifacts

**File:** `services/brain/src/brain/research/graph/nodes.py` (`decompose`)

```python
DECOMP_SYSTEM = """Decompose the research problem into 2–5 sub-questions.
For each sub-question output strict JSON with:
- question_text
- rationale
- expected_artifacts: one or more of [definition, metric_list, table(schema: ...), timeline, comparison_matrix, checklist]
- answerability: "yes" | "no" + what evidence would be sufficient
- priority: 0..1
"""
```

This keeps sub-loops focused on **deliverables**, not prose.

---

## 🧷 Prompt: Synthesis (Structure & Citations)

**Files:** `synthesize_sub_question`, `meta_synthesize`

```python
SYNTH_SYSTEM = """You write concise, structured answers using only VERIFIED_CLAIMS.
Rules:
- Bullet each claim; add [#] citation indices mapping to SOURCES_TABLE.
- Include ONE short verbatim quote per bullet.
- Add a 'Gaps' section for missing expected_artifacts.
- No claims without quotes.
"""
# USER payload includes: SUB_QUESTION, VERIFIED_CLAIMS_JSON, SOURCES_TABLE, EXPECTED_ARTIFACTS
```

Style guide: 🧩 [Pyramid principle](https://www.google.com/search?q=pyramid+principle+executive+summary+examples).

---

## 🧮 Scoring & Stopping Criteria

**File:** `services/brain/src/brain/research/graph/nodes.py` (`check_stopping_criteria`)

**Composite confidence:**
```python
confidence = (
    0.35*avg_entailment(state["claims"]) +
    0.25*avg_provenance(state["claims"]) +
    0.15*domain_diversity(state["sources"]) +
    0.15*cluster_consensus(state["claims"]) +
    0.10*recency_score(state["sources"])
)
```

**Coverage & novelty:**
```python
novelty = new_claim_clusters / max(1, total_clusters)
coverage_gap = 1 - satisfied_artifacts / max(1, total_expected_artifacts)

stop = (
    (confidence >= 0.75 and coverage_gap <= 0.20)
    or (novelty < 0.05 and iterations >= 4)
    or budget_exhausted
)
```

Defaults:
```
min_entailment = 0.70
min_provenance = 0.50
min_domains = 3
```

RAGAS note: run on **verified claims only**. 🍥 [RAGAS best practices](https://www.google.com/search?q=ragas+best+practices+github).

---

## 🗄 SQL Migrations (Claim Graph)

**File:** `services/brain/src/brain/research/sql/020_claim_graph.sql`

```sql
CREATE TABLE research_claims(
  id TEXT PRIMARY KEY,
  session_id TEXT REFERENCES research_sessions(id),
  sub_question_id TEXT,
  claim_text TEXT NOT NULL,
  entailment_score REAL NOT NULL,
  provenance_score REAL NOT NULL,
  dedupe_fingerprint TEXT NOT NULL,
  confidence REAL NOT NULL
);
CREATE TABLE research_evidence(
  id TEXT PRIMARY KEY,
  claim_id TEXT REFERENCES research_claims(id),
  url TEXT NOT NULL,
  title TEXT,
  quote TEXT NOT NULL,
  char_start INT,
  char_end INT
);
CREATE INDEX idx_claims_session ON research_claims(session_id);
CREATE INDEX idx_evidence_claim ON research_evidence(claim_id);
```

**Persistence changes** (`session_manager.py`): persist structured claims and evidence when storing findings.

---

## 🧠 Task‑Aware Model Routing

**Files:** `services/brain/src/brain/research/strategy/*`, `ModelCoordinator`

```python
TASK2MODEL = {
  "query_gen": "local-small",
  "extraction": "local-medium",
  "verification": "local-nli",     # deterministic
  "synthesis": "local-large"       # or external if coverage>=0.6 and budget permits
}
TASK2TEMP = {"query_gen":0.4, "extraction":0.1, "verification":0.0, "synthesis":0.3}

# Include `metadata={"task": ...}` in ConsultationRequest; set temp accordingly.
```

---

## 🪟 Results UI (for usable answers)

**File:** `services/ui/src/pages/Research.tsx`

- **Claim bullets** with confidence badge and `[n citations]` (expand to show quotes).
- **Artifacts tabs**: tables for `metric_list`, `confounders`, `comparison_matrix`.
- **Gaps** card: remaining `expected_artifacts`.
- **Methodology** accordion: queries used, reranker scores, novelty/coverage graphs.

---

## 🔭 Observability & Trace

- Add `GET /api/research/sessions/{id}/trace` returning: queries issued, docs kept/dropped, reranker top‑k, claim counts, novelty, coverage, budget.
- Log prompts/outputs per node for post‑mortems.

---

## 🧪 Local Evaluation Harness

Create `eval/` with YAML queries and gold artifacts.

**File:** `eval/run_eval.py`
```python
"""
Compute: faithfulness (on verified claims), citation accuracy, coverage, novelty, iterations, cost.
Run A/B: baseline vs evidence-first; ±reranker; ±entailment gate.
"""
```

**Metrics to track:**
- Citation accuracy: % claims with ≥1 exact quote; % quotes that entail claim (NLI).
- Coverage: satisfied_artifacts / expected_artifacts.
- Novelty rate per iteration.
- Source diversity: unique domains & entropy.

Resources:
- 🔎 [Hybrid search patterns](https://www.google.com/search?q=hybrid+search+bm25+dense+reranking+best+practices)  
- 🧪 [NLI models](https://www.google.com/search?q=best+lightweight+NLI+models+for+entailment)  
- 🍥 [RAGAS pitfalls](https://www.google.com/search?q=ragas+faithfulness+limitations+retrieval+augmented+generation)  
- 🧷 [Chain of verification](https://www.google.com/search?q=chain+of+verification+LLM+technique)  
- 🧩 [Pyramid principle writing](https://www.google.com/search?q=pyramid+principle+executive+summary+examples)

---

## 📜 Changelog Template (fill during PR)
- [ ] Types added
- [ ] Query generation updated
- [ ] Retrieval reranker added
- [ ] Evidence-first extractor
- [ ] NLI verification
- [ ] Composite scoring & stopping
- [ ] SQL migrations
- [ ] Synthesis prompts
- [ ] UI changes
- [ ] Trace endpoint
- [ ] Eval harness

---
