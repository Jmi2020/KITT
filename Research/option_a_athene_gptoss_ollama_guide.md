| Expert(s) | LLM Systems Architect; llama.cpp / C++ Inference Engineer; RAG & Context-Engineering Architect |
|:--|:--|
| Question | Implement Option A: Athene-V2 specialists constrained to 32k tokens plus a GPT-OSS 120B judge on Ollama, with robust token budgeting, RAG, and context management. |
| Plan | Define the architecture, specify token budgets, outline graph/orchestrator nodes, describe GPT-OSS 120B setup on Ollama (including num_ctx and parallelism), and provide implementation-oriented examples suitable for a coding agent. |

# Implementation Guide: **Option A – Bounded-Context Athene-V2 Specialists + GPT-OSS 120B Judge on Ollama**

This document explains how to implement **Option A**:

- Treat **Athene-V2** specialists as **32k-context bounded agents**.
- Use **GPT-OSS 120B** as a **high-context judge** running on **Ollama**.
- Use a graph/orchestrator (e.g. LangGraph / custom DAG) to:
  - Fan out to multiple Athene specialists in parallel.
  - Aggregate their work and evidence.
  - Let GPT-OSS 120B perform final synthesis and verification with a much larger context window.

---

## 1. High-Level Architecture

At a high level, a single request flows like this:

1. **User Query Ingest**
   - Receive the user’s task (possibly multi-turn conversation).
   - Append to conversation store.

2. **Global State Summarization**
   - Summarize the **full conversation history** into a compact state (≈ 1–2k tokens).
   - Optionally include a compact “working memory” summary of long-running tasks.

3. **Retrieval from Knowledge Base**
   - Use vector search and/or keyword search to pull **KB chunks** relevant to the current query.
   - Limit to a **token budget** suitable for Athene (e.g. 6–12k tokens per specialist).

4. **Parallel Athene-V2 Specialists (≤ 32k each)**
   - For each specialist persona (e.g. “Researcher”, “Tool-Caller”, “Critic”):
     - Build a prompt: system + tools + global summary + KB slices + user query.
     - Ensure prompt + expected completion stay under ~28k tokens.
   - Run all specialists in parallel (separate HTTP requests).

5. **Intermediate Artifact Store**
   - Store:
     - Specialist answers.
     - Short reasoning traces / bullet chains-of-thought (for *internal* use only).
     - IDs of KB chunks used and tool calls invoked.

6. **GPT-OSS 120B Judge on Ollama**
   - Build a large-context prompt including:
     - User query and a short conversation summary.
     - Specialist outputs (distilled).
     - The **union** of KB chunks they used (plus any extra context you want).
   - Let GPT-OSS 120B:
     - Cross-check specialist claims.
     - Optionally re-call tools.
     - Produce a final answer + explanation + citations.

7. **Response & Logging**
   - Return the final answer to the user.
   - Log metadata (used KB IDs, tools, token counts) for evaluation and debugging.

A simple conceptual diagram:

```text
User Query
   │
   ▼
[ Conversation Store ]──►[ Global Summary Node ]
                               │
                               ▼
                        [ Retrieval Node ] ──► KB chunks
                               │
                               ▼
          ┌───────────────────────────────────────────┐
          │       Parallel Athene-V2 Specialists      │
          │                                           │
          │   [Specialist A] [Specialist B] [...]     │
          └───────────────────────────────────────────┘
                               │
                               ▼
                      [ Artifact Store ]
                               │
                               ▼
                     [ GPT-OSS 120B Judge ]
                               │
                               ▼
                           Final Answer
```

---

## 2. Components and Responsibilities

### 2.1 Athene-V2 Specialists (bounded 32k)

- Run via your existing **llama.cpp / llama-server** pipeline with a **hard 32k slot limit**.
- Each call:
  - Receives:
    - A short conversation summary.
    - A subset of KB chunks.
    - A persona-specific system prompt.
    - Tool schema if tools are available.
  - Produces:
    - An answer draft.
    - A concise reasoning trace (few hundred–few thousand tokens).
    - References to any KB chunk IDs and tool calls it used.

Key rule: **No single Athene call may exceed ~28–30k total tokens (prompt + output)**.

### 2.2 GPT-OSS 120B Judge (Ollama)

- Runs as a **separate model** in Ollama (e.g. `gpt-oss-120b`).
- Supports up to **~128k–131k token context** (architecture supports ~131k tokens according to OpenAI’s gpt-oss docs). citeturn0news38turn0search18
- Takes responsibility for:
  - Cross-checking specialist claims.
  - Reconciling disagreements.
  - Producing final user-facing answers with higher reliability.
  - Optionally re-calling tools if evidence is unclear.

### 2.3 Orchestrator / Graph Runtime

You can implement this with:

- 🧩 [LangGraph-style DAG](https://www.google.com/search?q=LangGraph+Python+multi-agent+DAG+LLM+orchestration)
- 🧱 [Custom orchestration layer](https://www.google.com/search?q=custom+LLM+orchestrator+DAG+python+asyncio) using `asyncio` and OpenAI-compatible clients.

Responsibilities:

- Track **node state** (conversation summary, KB slices, agent outputs).
- Enforce **token budgets** per node.
- Fan-out/fan-in between specialists and judge.
- Handle retries and tool call execution.

### 2.4 Knowledge Base / Retrieval

- Vector store (e.g. FAISS, Qdrant, Milvus, pgvector) plus metadata filters.
- Chunk documents into ~500–1500 token chunks.
- During retrieval, select **top-N** chunks per specialist, obeying their token budgets.

---

## 3. Token Budgeting for Athene Specialists

### 3.1 Budget targets

Given Athene’s effective 32k cap, define explicit budgets:

- `MAX_CTX_ATHENE = 32000`
- Reserve **some context for output** to avoid overflow, e.g.:

  ```text
  PROMPT_BUDGET_ATHENE = 24000      # tokens for input
  OUTPUT_BUDGET_ATHENE = 6000–8000  # tokens for completion
  ```

- Within the prompt budget, allocate:

  ```text
  System + persona + tools:    ~4000
  Global conversation summary: ~2000
  KB chunks:                   ~8000–12000
  User query + framing:        ~2000
  Margin / overhead:           ~2000
  ```

These numbers are guidelines—tune them with real tokenization measurements.

### 3.2 Context preparation pipeline for each Athene call

For each specialist:

1. **Build system prompt**
   - Persona, role, tool usage instructions, and safety policies.

2. **Compute conversation summary**
   - Use a **separate summarizer node** (can be Athene or GPT-OSS with a small prompt) to compress full history into ≤ 2k tokens.

3. **Select KB slices**
   - Query RAG backend with `(summary, current_user_query)`.
   - Rank by similarity + recency + any custom scoring.
   - Add chunks until you reach `KB_BUDGET` (e.g. 8–12k tokens).

4. **Assemble messages**
   - System: instructions, persona, tools.
   - “Memory” message: global summary.
   - “Context” message: KB slices (with IDs).
   - User message: the latest user query and any direct followups.

5. **Token count & trimming**
   - Use your tokenizer (Qwen/Athene compatible) to count tokens.
   - If `prompt_tokens > PROMPT_BUDGET_ATHENE`:
     - First trim KB chunks (drop lowest-ranked).
     - If still too large, compress summary further (ask summarizer to output ≤ 1k tokens).
     - As a last resort, prune older parts of the summary.

6. **Invoke Athene**
   - Set `max_tokens = OUTPUT_BUDGET_ATHENE`.
   - Ask for:
     - An “answer” section.
     - A compact “internal reasoning” section that you mark as not user-facing.

### 3.3 Example pseudo-code for a specialist call

```python
def build_athene_prompt(state, specialist_config, tokenizer, budgets):
    system = specialist_config.system_prompt  # persona + tools instructions
    summary = state.conversation_summary      # precomputed
    kb_chunks = select_kb_chunks(state, specialist_config, budgets.kb_budget)

    messages = [
        {"role": "system", "content": system},
        {
            "role": "system",
            "content": (
                "Conversation summary (for context only, do not quote verbatim):
"
                f"{summary}"
            ),
        },
        {
            "role": "system",
            "content": format_kb_chunks_for_llm(kb_chunks),
        },
        {"role": "user", "content": state.current_user_query},
    ]

    token_count = count_tokens_athene(messages, tokenizer)

    while token_count > budgets.prompt_budget:
        # First trim KB
        if len(kb_chunks) > budgets.min_kb_chunks:
            kb_chunks = kb_chunks[:-1]  # drop least relevant
        else:
            # As last resort, compress summary further
            summary = compress_summary(summary, target_tokens=budgets.summary_floor)
        messages[1]["content"] = (
            "Conversation summary (for context only):
" + summary
        )
        messages[2]["content"] = format_kb_chunks_for_llm(kb_chunks)
        token_count = count_tokens_athene(messages, tokenizer)

    return messages
```

---

## 4. Orchestrator / Graph Blueprint

This section outlines a minimal graph-style architecture that a coding agent can implement using LangGraph or a similar library.

### 4.1 Node types

1. **`ConversationStore`**
   - Input: `(user_id, message)`
   - Output: updated conversation history.

2. **`ConversationSummarizer`**
   - Input: full history.
   - Output: compressed summary (≤ 2k tokens).

3. **`RetrievalNode`**
   - Input: `(summary, user_question)`
   - Output: `kb_candidates` (ranked list of KB chunks with IDs and token counts).

4. **`AtheneSpecialistNode`**
   - Input: `(summary, kb_candidates, user_question, specialist_config)`
   - Output: `specialist_result`:
     - `answer_draft`
     - `internal_trace`
     - `used_kb_ids`
     - `tool_calls`

5. **`ArtifactAggregator`**
   - Input: results from all specialists.
   - Output: aggregated view for the judge:
     - `specialist_summaries`
     - `evidence_kb_ids`
     - `tool_results`

6. **`GPTOSSJudgeNode`**
   - Input: `(conversation_summary, user_question, specialist_summaries, evidence_kb_chunks, tool_results)`
   - Output: final answer + explanation.

### 4.2 Example graph wiring (pseudo-code)

```python
def build_graph():
    # Pseudo-API; adapt to LangGraph or your orchestrator of choice
    graph = Graph()

    conv_store = graph.add_node("conversation_store", ConversationStore())
    summarizer = graph.add_node("conversation_summarizer", ConversationSummarizer())
    retriever = graph.add_node("retrieval", RetrievalNode())

    specialists = [
        graph.add_node("researcher", AtheneSpecialistNode(config=RESEARCHER_CONFIG)),
        graph.add_node("critic", AtheneSpecialistNode(config=CRITIC_CONFIG)),
        graph.add_node("tool_user", AtheneSpecialistNode(config=TOOL_USER_CONFIG)),
    ]

    aggregator = graph.add_node("artifact_aggregator", ArtifactAggregator())
    judge = graph.add_node("gptoss_judge", GPTOSSJudgeNode())

    # Wiring
    graph.edge(conv_store, summarizer)
    graph.edge(summarizer, retriever)

    for s in specialists:
        graph.edge(summarizer, s)
        graph.edge(retriever, s)

    graph.edge_many(specialists, aggregator)
    graph.edge(summarizer, aggregator)

    graph.edge(aggregator, judge)
    graph.edge(summarizer, judge)

    graph.set_entry(conv_store)
    graph.set_output(judge)

    return graph
```

---

## 5. GPT-OSS 120B on Ollama – Setup & Best Practices

### 5.1 Model and context capabilities

OpenAI’s **gpt-oss-120b**:

- Is an open-weight **mixture-of-experts** transformer with ~117B parameters, ~5.1B active per token. citeturn0search18turn0news40  
- Supports **context lengths up to ~131,072 tokens**, making it suitable as a long-context judge. citeturn0news38turn0news42  
- Is distributed via platforms including **Hugging Face** and **Ollama**, and can be run locally with sufficient GPU memory (e.g. 80GB GPU) or quantized variants on CPU+GPU. citeturn0search3turn0news40  

In Ollama:

- Each model has a **model-native context length**, and you control the runtime context via `num_ctx` in the `Modelfile` or request options. citeturn0search4turn0search12  

### 5.2 Install and basic Ollama setup

On a machine with Ollama installed:

```bash
# Pull the GPT-OSS 120B model, assuming Ollama supports it under this name
ollama pull gpt-oss-120b
```

Check configuration:

```bash
ollama show gpt-oss-120b
```

This displays:

- The model’s **native context length**.
- Default parameters like temperature, top_p, etc.

To ensure Ollama is reachable by other services:

```bash
# Example: bind to all interfaces
OLLAMA_HOST=0.0.0.0:11434 ollama serve
```

Environment variables for configuration are documented in Ollama’s FAQ and docs. citeturn0search1turn0search13  

### 5.3 Setting context length via `num_ctx`

You can set **per-model** context length in a `Modelfile`:

```text
FROM gpt-oss-120b

# Allow large context for the judge (assuming hardware supports it)
PARAMETER num_ctx 131072

# Reasonably sized batches; tune per hardware
PARAMETER num_batch 512

# Sampling parameters
PARAMETER temperature 0.4
PARAMETER top_p 0.9
PARAMETER repeat_penalty 1.1
```

Build the model:

```bash
ollama create gpt-oss-120b-judge -f Modelfile
```

Now you can run:

```bash
ollama run gpt-oss-120b-judge
```

At runtime, you can also override `num_ctx` in request `options`:

```jsonc
{
  "model": "gpt-oss-120b-judge",
  "prompt": "...",
  "options": {
    "num_ctx": 131072,
    "num_predict": 4096
  }
}
```

**Note:** Some experiments show that in practice `num_ctx` acts mainly as an **input prompt limit**, but the effective context is bounded by model training and implementation. citeturn0search4turn0search12  

### 5.4 Concurrency and resource tuning

Ollama offers server-level environment variables:

- `OLLAMA_NUM_PARALLEL` – max parallel requests per model. citeturn0search19turn0search21  
- `OLLAMA_MAX_LOADED_MODELS` – max models loaded concurrently.
- `OLLAMA_MAX_QUEUE` – max queued requests.

Example (Linux, single judge model, moderate parallelism):

```bash
OLLAMA_NUM_PARALLEL=2 OLLAMA_MAX_LOADED_MODELS=2 OLLAMA_MAX_QUEUE=128 OLLAMA_HOST=0.0.0.0:11434 ollama serve
```

For a **heavy judge** like GPT-OSS 120B:

- Start with `OLLAMA_NUM_PARALLEL=1` or `2` to avoid thrashing GPU memory.
- Keep `OLLAMA_MAX_LOADED_MODELS` low (1–2) if the judge is the main load.

To inspect context and memory:

```bash
ollama ps
```

This shows, for each model:

- `PROCESSOR` (CPU vs GPU split).
- `CONTEXT` – allocated context length. citeturn0search4  

### 5.5 HTTP usage patterns

Typical JSON request for the judge:

```bash
curl http://localhost:11434/v1/chat/completions   -H "Content-Type: application/json"   -d '{
    "model": "gpt-oss-120b-judge",
    "messages": [
      {"role": "system", "content": "You are the final judge in a multi-agent system..."},
      {"role": "user", "content": "Here is the question and the specialists outputs..."}
    ],
    "max_tokens": 4096,
    "temperature": 0.4,
    "stream": true
  }'
```

From Python:

```python
import requests

def call_gptoss_judge(messages, max_tokens=4096):
    payload = {
        "model": "gpt-oss-120b-judge",
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.4,
    }
    r = requests.post("http://localhost:11434/v1/chat/completions", json=payload, timeout=600)
    r.raise_for_status()
    data = r.json()
    return data["choices"][0]["message"]["content"]
```

---

## 6. Context Management Strategies for GPT-OSS 120B

Even with a large context (e.g. 128k), it’s important to **structure** input for reliability and efficiency.

### 6.1 Judge prompt structure

A good pattern:

1. **System message** – role, evaluation criteria, tool usage.
2. **Task section** – the user’s original question and any explicit requirements.
3. **Conversation section** – a compact summary of prior conversation (≤ 2k tokens).
4. **Specialist summaries section** – per specialist:
   - Role.
   - Short summary of their reasoning.
   - Their final recommendation.
   - IDs of KB chunks and tools used.
5. **Evidence section** – concatenated KB chunks, grouped and tagged by ID.
6. **Tool results section** – outputs from any external tools.
7. **Instructions for output format** – how the judge should structure the final answer.

### 6.2 Evidence referencing and chunk IDs

When Athene specialists use KB chunks, always tag them:

```text
[KB#123] Title: ...
Content: ...

[KB#124] Title: ...
Content: ...
```

Specialists should write things like:

> According to [KB#123], …

Then the judge can:

- See exactly which chunk a claim is based on.
- Re-weight or discard claims based on conflicting evidence.

### 6.3 Token budgeting for the judge

Define:

```text
MAX_CTX_JUDGE = 131072
PROMPT_BUDGET_JUDGE = 100000   # leave room for output
OUTPUT_BUDGET_JUDGE = 4096–8192
```

Within the prompt:

```text
System + task + instructions:     ~4000
Conversation summary:             ~2000
Specialist summaries:             ~6000–10000
KB evidence (chunks):             ~60000–80000
Tool results:                     ~5000–10000
Margin / overhead:                ~5000
```

Use a similar trimming strategy:

- If prompt exceeds `PROMPT_BUDGET_JUDGE`:
  - First compress specialist summaries.
  - Then drop lowest-priority KB chunks.
  - As a last resort, compress conversation summary further.

### 6.4 Hierarchical summarization

For extremely large KBs:

- **First level**: store embeddings and chunk-level summaries.
- **Second level**: when many chunks are retrieved, group them and create group-summaries (e.g. 1–2k tokens per group).
- The judge sees:
  - A mix of detailed chunks (for critical evidence).
  - Group summaries (for broad context).

This keeps the judge’s context dense with information but bounded.

---

## 7. Example Prompts

### 7.1 Athene specialist system prompt (template)

```text
You are Athene-V2 Specialist: {{role_name}}.

Your job:
- Analyze the user question using the conversation summary and KB context.
- Use tools when needed (see tool schema below).
- Produce:
  1) A clear, concise answer.
  2) A short internal reasoning trace (for other agents, not the user).

Constraints:
- DO NOT assume access to information not present in the KB, tools, or your own knowledge.
- Prefer citing specific KB IDs like [KB#123] when you rely on them.
- Be explicit about uncertainty.

Tools:
{{tool_schema}}

Output format (JSON in a fenced code block):

```json
{
  "answer": "string",
  "reasoning_trace": "string",
  "used_kb_ids": ["KB#123", "KB#124"],
  "tool_calls": [
    {"tool": "web_search", "args": {"query": "..."}},
    {"tool": "code_exec", "args": {"language": "python", "code": "..."}}
  ]
}
```
```

### 7.2 GPT-OSS 120B judge system prompt (template)

```text
You are the final judge in a collective reasoning system.

You receive:
- The user task.
- A summary of the prior conversation.
- Outputs from several specialist models.
- Evidence from a knowledge base (KB chunks, tagged as [KB#ID]).
- Tool results.

Your job:
1. Evaluate the specialists' reasoning and conclusions.
2. Cross-check their claims against the KB and tool outputs.
3. If evidence is missing or conflicting, explicitly note it.
4. Produce a final answer that:
   - Is accurate and grounded in the evidence you see.
   - Clearly references KB IDs where appropriate.
   - Explains your reasoning at a high level.
5. If tools are available to you, you may suggest or perform additional tool calls to resolve ambiguity.

You must not reveal chain-of-thought in detail to the user; summarize your reasoning.

Output format:

```json
{
  "final_answer": "string",
  "high_level_reasoning": "string",
  "supporting_kb_ids": ["KB#..."],
  "disagreements_between_specialists": [
    {
      "specialists": ["researcher", "critic"],
      "issue": "string",
      "resolution": "string"
    }
  ]
}
```
```

---

## 8. End-to-End Execution Flow (Step-by-Step)

1. **Receive user request**.
2. **Append** to conversation history in a durable store.
3. **Run `ConversationSummarizer`**:
   - If tokenized history > threshold (e.g. 4k tokens), produce/update a summary.
4. **Run `RetrievalNode`** using `(summary, latest_user_query)`:
   - Fetch top K KB chunks and their metadata.
5. **Dispatch Athene specialists in parallel**:
   - For each specialist:
     - Build prompt with budgets.
     - Call Athene (OpenAI-compatible endpoint).
     - Parse JSON output.
6. **Store artifacts**:
   - Write `answer_draft`, `reasoning_trace`, `used_kb_ids`, `tool_calls` to a central store.
7. **Optional: Execute tool calls triggered by specialists**:
   - Aggregate tool requests.
   - Execute them (e.g. web search, code execution, DB queries).
   - Attach results as `tool_results`.
8. **Run `ArtifactAggregator`**:
   - Build a concise summary per specialist.
   - Collect all referenced KB IDs.
   - Fetch union of KB chunks + tool results.
9. **Invoke GPT-OSS 120B judge on Ollama**:
   - Build judge prompt with:
     - Task.
     - Conversation summary.
     - Specialist summaries.
     - KB evidence.
     - Tool results.
   - Ensure token budget is respected.
10. **Return final answer**:
    - Send `final_answer` to the user.
    - Optionally log `high_level_reasoning` internally.

---

## 9. Operational Considerations

### 9.1 Logging and observability

- Log for each request:
  - Token counts per node (input, output).
  - KB chunk IDs used.
  - Tool calls and results.
  - Latency per node and total.
- Sample a subset of requests and store:
  - Specialist outputs.
  - Judge prompt and output.
  - Ground-truth labels if you have them.

### 9.2 Evaluation loops

Implement evaluation modes:

- **Offline batch evaluation**:
  - Run recorded queries through the full pipeline.
  - Compare final answers against ground-truth or high-quality references.
- **A/B testing**:
  - Compare:
    - Different KB budgets.
    - Different specialist personas.
    - Different judge configurations (e.g. shorter vs longer context).

### 9.3 Failure modes

Typical issues and mitigations:

- **Context overflow at Athene**:
  - Make budgets stricter (e.g. `PROMPT_BUDGET_ATHENE = 20k`).
  - Make KB more selective and compress summaries more aggressively.
- **Judge running out of context**:
  - Ensure chunk deduplication.
  - Use hierarchical summarization for large KB slices.
- **Latency too high**:
  - Cache retrieval and summaries when possible.
  - Use partial parallelism for judge and tools if safe.

---

## 10. Summary

Option A does **not** fight Athene’s **32k training context**. Instead:

- Athene-V2 specialists act as **high-IQ, bounded-context workers**.
- GPT-OSS 120B on Ollama acts as a **long-context judge** with a carefully managed 100k+ token prompt.
- A token-budget-aware orchestrator ensures:
  - Each node stays within its context window.
  - The judge sees a dense, evidence-rich, but bounded view of the conversation and KB.

This document provides enough structure (budgets, node types, prompt templates, Ollama config) for a coding agent to implement the system end-to-end.
