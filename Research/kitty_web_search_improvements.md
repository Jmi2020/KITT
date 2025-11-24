# Improving KITTY’s Web‑Search Reasoning Loop

## 1. Objective

KITTY sometimes repeats nearly identical **Thought** and **Action** steps, re‑running the same `web_search` query until it hits the maximum reasoning‑iteration limit. This guide explains how to:

- Make each reasoning step add genuinely new information.
- Avoid redundant tool calls and loops.
- Recognize when a question is unanswerable or needs approximation.
- Produce useful answers earlier, with clear caveats.

Patterns from 🤖 [ReAct‑style prompting](https://www.google.com/search?q=ReAct+prompting+reasoning+and+acting+llm+agents) and 🧠 [tool‑using LLM agents](https://www.google.com/search?q=tool+using+llm+agents+design+patterns) are adapted here for KITTY.

---

## 2. The Current Failure Mode

From the trace, KITTY:

1. Repeats the same interpretation of the question every step.
2. Calls `web_search` with the **exact same query** many times.
3. Never updates its **beliefs** or **plan** based on new observations.
4. Eventually hits **max iterations** and fails with no answer.

Example pattern (simplified):

```text
Thought: I need to search for "current adoption rates Ollama vs Llama.cpp".
Action: web_search("current adoption rates Ollama vs Llama.cpp")
Observation: <some results>

Thought: I need to search for "current adoption rates Ollama vs Llama.cpp".
Action: web_search("current adoption rates Ollama vs Llama.cpp")
...
```

This indicates:

- No explicit **state** across steps.
- No requirement that steps show **progress**.
- No notion of **answerability** (e.g., “this exact metric doesn’t exist”).
- No **runtime guardrail** against duplicate tool calls.

The rest of this document describes concrete changes to fix those issues.

---

## 3. Design Principles

### 3.1. Statefulness

Each step should operate over an explicit **scratchpad**, not just free‑form text.

The scratchpad tracks:

- The **question** and its current **interpretation**.
- Any **assumptions** you’re making.
- The **plan** (sub‑steps).
- A history of **tool calls** and **observations**.
- Collected **facts**.
- Current **uncertainties** or open sub‑questions.
- A **candidate answer** and its confidence.
- An **answerability status**.

### 3.2. Progressful Steps

Every reasoning step should:

1. Add new information **or**
2. Change the plan **or**
3. Move closer to a final answer.

If a step simply restates the same thought and proposes the same action, it should be rejected.

### 3.3. Search Diversification

Multiple web calls must not all be the same. Instead, they should explore **different angles**, e.g.:

- General overview
- Side A only (e.g., Ollama)
- Side B only (e.g., llama.cpp)
- Proxies (GitHub stats, downloads, enterprise case studies, etc.)

### 3.4. Answerability and Graceful Degradation

KITTY must regularly answer:

> Is the user’s **exact** question answerable with available web data?

Possible answers:

- **(a)** Yes, directly.
- **(b)** Only approximately (via proxies).
- **(c)** Probably not (data doesn’t exist or isn’t public).

For (b) and (c), it should stop searching and:

- Explain what is and isn’t available.
- Provide the best qualitative / proxy‑based answer it can.

This is similar in spirit to 🧪 [LLM self‑reflection](https://www.google.com/search?q=self+reflection+llm+agents+answerability) techniques.

---

## 4. Scratchpad Structure

You can model the scratchpad as a JSON‑like object stored in memory for the task:

```json
{
  "question": "",
  "interpretation": "",
  "assumptions": [],
  "plan": [],
  "tool_calls": [],
  "facts": [],
  "uncertainties": [],
  "candidate_answer": null,
  "answerability": "unknown"
}
```

**Suggested fields:**

- `question`: Original user query.
- `interpretation`: KITTY’s current paraphrase / understanding.
- `assumptions`: Explicit guesses (e.g., “‘magnificent 7’ = big tech mega‑caps”).
- `plan`: High‑level steps (2–4 bullets).
- `tool_calls`: List of `{tool, args, result_summary}`.
- `facts`: Normalized, de‑duplicated facts extracted from observations.
- `uncertainties`: Important unknowns (e.g., “No direct adoption metrics found”).
- `candidate_answer`: Best current answer + rationale.
- `answerability`: `"unknown" | "direct" | "proxy_only" | "unlikely"`.

The orchestration layer can persist and pass this scratchpad to each reasoning step.

---

## 5. Per‑Step Prompt Template (“Delta‑Only”)

To avoid repetition, each step should **only talk about what changed** since the previous step.

### 5.1. Template

You can embed this template in KITTY’s internal prompt:

```text
You are at reasoning step {n} for the current question.

You are given a scratchpad with:
- question
- interpretation
- assumptions
- plan
- tool_calls
- facts
- uncertainties
- candidate_answer
- answerability

Your job at this step:

1. Briefly list only the NEW evidence since the last step (max 3 bullets).
2. Briefly list what remains uncertain (max 2 bullets).
3. Update the answerability status:
   - Choose one: (a) direct, (b) proxy_only, (c) unlikely.
4. Decide the next move:
   - If (b) or (c): DO NOT call web_search again; move toward a final answer.
   - If (a) and more data is needed:
       - Propose ONE new action that is materially different from prior actions
         (new query terms, a different site focus, or a summarization step).
5. Update the scratchpad accordingly.
6. If you believe you can now answer the question well enough, stop and draft the final answer instead of calling more tools.
```

At the end of each step, the model must output both:

- The updated scratchpad, and
- Either a tool call or a draft answer.

---

## 6. Web‑Search Strategy for KITTY

### 6.1. Search Phases

Define simple phases for search:

1. **Phase 1 – Broad scan**

   - 1–2 general queries.
   - Goal: identify main concepts, existing metrics, obvious limitations.

2. **Phase 2 – Focused probes**

   - Separate queries for each key component:
     - Ollama adoption / ecosystem
     - llama.cpp adoption / ecosystem
   - Additional queries for **proxies**, such as:
     - GitHub stars / commits
     - Package downloads
     - Enterprise case studies / blog posts
   - Example: 📈 [Ollama GitHub stars and usage](https://www.google.com/search?q=Ollama+GitHub+stars+usage+statistics)  
     Example: 🐑 [llama.cpp adoption GitHub stats](https://www.google.com/search?q=llama.cpp+adoption+github+stars+usage)

3. **Phase 3 – Synthesis**

   - No more web calls.
   - Aggregate facts, confront uncertainties.
   - Produce final answer with clear caveats.

### 6.2. Query Diversification Rules

Add explicit rules for KITTY when calling `web_search`:

- Each new query must:
  - Differ by at least **3 meaningful tokens** from previous queries, and
  - Target a **different angle** (general vs proxies vs one side vs the other).

For example, instead of repeatedly calling:

```text
"current adoption rates Ollama vs Llama.cpp"
```

KITTY would evolve through:

```text
"ollama adoption stats github stars downloads"
"llama.cpp usage metrics github stars downloads"
"ollama vs llama.cpp production usage comparison"
"ollama enterprise case studies vs llama.cpp"
```

If none of these yield a quantitative “adoption rate,” KITTY should decide that **direct numbers are unavailable** and move to a qualitative comparison.

---

## 7. Orchestrator‑Side Guardrails

You can catch many issues outside the model by adding simple checks in the orchestrator.

### 7.1. Duplicate Tool‑Call Filter

Before executing a tool call, compare it to recent history:

```python
def should_execute_tool_call(tool_name, args, recent_calls, k=5):
    for call in recent_calls[-k:]:
        if call["tool_name"] == tool_name and call["args"] == args:
            return False  # duplicate
    return True
```

If `should_execute_tool_call` returns `False`, ask the model to:

- Change its query,
- Move to synthesis, or
- Declare the question unanswerable as asked.

This prevents the “stuck loop” where the same query is used 10 times.

### 7.2. Reasoning‑Step Budget with Early “Best Effort”

Instead of just a hard max‑step failure, define:

- A **soft budget** (e.g., 3–5 steps) after which the model is encouraged to answer.
- A **hard budget** (e.g., 8–10 steps) at which the model must:
  - Use whatever it has gathered, and
  - Return a best‑effort answer that explicitly explains limitations.

Sketch:

```python
if step >= soft_budget:
    # Nudge toward answering
    system_msg = (
        "You have already used several reasoning steps. "
        "Prefer synthesizing and answering now using what you have."
    )

if step >= hard_budget:
    # Force answering instead of another tool call
    system_msg = (
        "You have reached the maximum reasoning steps. "
        "Do NOT call tools again. Synthesize the best possible answer "
        "from available facts, and clearly state any missing data."
    )
```

---

## 8. Handling Ambiguous / Ill‑Posed Questions

For queries like:

> “Current rate of adoption for Ollama vs llama.cpp in the magnificent 7”

KITTY should:

1. **Identify ambiguity**

   - “magnificent 7” is unclear:
     - S&P “Magnificent 7” mega‑cap stocks?
     - Some internal group of 7 companies?
     - Something else entirely?

2. **Check if a metric exists**

   - There is no public, standardized “adoption rate of tools X and Y within group Z” metric.
   - Proxies will have to be used.

3. **Respond explicitly**

   Rather than forcing more search, KITTY should say:

   - It couldn’t find any direct “adoption rate” data for that specific cohort.
   - It can, however, compare:
     - Overall popularity,
     - GitHub stats,
     - Blog posts and production use reports, etc.
   - Then provide a **qualitative** comparison backed by the data it *does* have.

Encourage this behavior via instructions similar to:

```text
If you cannot find direct numerical data after 2–3 distinct web_search calls,
you MUST stop searching for that exact number.

Instead, use proxies (GitHub activity, downloads, case studies, etc.) to
form a qualitative or approximate answer, and clearly state that the exact
metric is unavailable.
```

This aligns with best practices for 🕵️ [handling ambiguous queries](https://www.google.com/search?q=handling+ambiguous+user+queries+in+chatbots).

---

## 9. Example: Rewritten Flow for the Ollama vs llama.cpp Query

Below is a sketch of how KITTY should behave after the changes.

### Step 0 – Initialization

- Interpretation:
  - Compare adoption of **Ollama** vs **llama.cpp**.
  - “Magnificent 7” is ambiguous → assume it refers to major tech firms unless otherwise specified.
- Plan:
  1. Broad scan for any published adoption metrics or surveys.
  2. Focused search for proxies (GitHub stats, blog posts, case studies).
  3. Synthesize qualitative comparison and note ambiguity.

### Step 1 – Broad Scan

- Query: `"ollama vs llama.cpp adoption comparison"`
- Observation: articles comparing features and usage contexts but no numeric “adoption rate”.
- Facts:
  - Both are widely used for local LLM inference.
  - Ollama focuses on easy local use; llama.cpp is a lower‑level inference engine.

Update:

- Uncertainty: no direct adoption metrics yet.
- Answerability: `proxy_only`.

### Step 2 – Focused Proxies (Ollama)

- Query: `"Ollama GitHub stars downloads active users"`
- Collect:
  - GitHub stars, release activity, mentions in blogs, etc.

### Step 3 – Focused Proxies (llama.cpp)

- Query: `"llama.cpp GitHub stars usage examples production"`
- Collect:
  - GitHub stars, forks, ecosystem notes.

### Step 4 – Synthesis

- No more `web_search`.
- Compare:
  - Age of projects.
  - Ecosystem maturity.
  - Typical use cases.
- Final answer:
  - Explain absence of precise “adoption rate”.
  - Provide a reasoned qualitative comparison.
  - State assumptions about “magnificent 7”.

This is a far more informative outcome than “Maximum reasoning iterations reached without finding an answer.”

---

## 10. Rollout Checklist

Use this as a quick checklist when you implement and tune KITTY:

1. **Scratchpad**
   - [ ] Added a structured scratchpad object.
   - [ ] Each step reads and updates the scratchpad.

2. **Per‑Step Template**
   - [ ] Steps are “delta‑only” (new evidence + changed uncertainties).
   - [ ] Answerability status is updated regularly.

3. **Search Behavior**
   - [ ] Queries are diversified by design (different angles).
   - [ ] There’s a clear pivot to proxies if direct data is missing.

4. **Orchestrator Guardrails**
   - [ ] Duplicate tool calls with identical args are blocked.
   - [ ] A soft budget nudges synthesis.
   - [ ] A hard budget forbids further tool calls and forces a best‑effort answer.

5. **Ambiguity Handling**
   - [ ] Ambiguous terms (e.g., “magnificent 7”) are explicitly identified.
   - [ ] KITTY either states its assumption or asks for clarification (if the environment permits).
   - [ ] Non‑existent metrics result in a clear explanation plus a proxy‑based answer, not an infinite search loop.

By combining these changes, KITTY’s web‑search reasoning loop becomes:

- More **efficient** (fewer wasted steps),
- More **robust** (less likely to get stuck),
- More **transparent** (clear about what is and isn’t knowable), and
- More **useful** to the user, even when the “perfect” data simply doesn’t exist.
