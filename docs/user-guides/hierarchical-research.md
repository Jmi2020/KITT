# Hierarchical Research Mode

## Overview

Hierarchical research is an advanced research mode that breaks down complex, multi-faceted questions into focused sub-questions, researches each independently, and then synthesizes the findings into a comprehensive answer.

## When to Use Hierarchical Mode

### ✅ Use Hierarchical Mode For:

1. **Complex comparison questions**
   - "Compare React vs Vue.js vs Angular"
   - "Evaluate three conflicting expert opinions on climate tipping points"

2. **Multi-aspect questions**
   - "Explain the causes, effects, and solutions to climate change"
   - "What are the technical, business, and ethical implications of AI?"

3. **Deep investigative queries**
   - "How does quantum computing work and what are its practical applications?"
   - "Analyze the economic, political, and social factors behind the 2008 financial crisis"

### ❌ Use Flat Mode For:

1. **Simple factual queries**
   - "What is the capital of France?"
   - "When was Python created?"

2. **Single-aspect questions**
   - "What are the key features of Rust?"
   - "How does JWT authentication work?"

3. **Quick lookups**
   - "Latest version of Node.js"
   - "Syntax for Python list comprehension"

## How It Works

### 1. Query Decomposition

When you submit a query with hierarchical mode enabled, an LLM analyzes your question and breaks it into 2-5 meaningful sub-questions:

```
Original: "Three experts disagree on climate tipping points:
           Expert A cites 2030 deadline, Expert B cites 2050,
           Expert C says timelines are unknowable.
           Evaluate each position and explain which evidence is stronger."

Decomposed into:
1. What is Expert A's position and evidence? (priority: 0.9)
2. What is Expert B's position and evidence? (priority: 0.9)
3. What is Expert C's position and evidence? (priority: 0.9)
4. What does scientific literature say about climate tipping points? (priority: 1.0)
```

### 2. Priority-Based Research

Each sub-question gets:
- **Priority score** (0.0-1.0): Importance to answering the main question
- **Iteration budget**: Weighted by priority
- **Independent research**: Dedicated findings and sources

### 3. Sub-Question Synthesis

After researching each sub-question, the system creates a **focused synthesis**:

```
Sub-Question: "What is Expert A's position and evidence?"

Synthesis: "Expert A argues for a 2030 climate tipping point deadline
based on Arctic ice melt acceleration and IPCC temperature projections.
Key evidence includes [specific studies]. Confidence: Medium.
Limitations: [caveats]."
```

### 4. Meta-Synthesis

Finally, all sub-question syntheses are integrated into a **comprehensive answer**:

```
Meta-Synthesis: "Evaluating the three positions against scientific
literature, Expert B's 2050 timeline has stronger empirical support
because [reasons]. However, Expert A's urgency is partially validated
by [evidence]. Expert C's skepticism highlights [valid concerns] but
overlooks [counterpoints]..."
```

## Configuration

### Enable Hierarchical Mode

Add to your research session configuration:

```json
{
  "query": "Your complex question here",
  "config": {
    "enable_hierarchical": true,
    "max_iterations": 20,
    "min_sub_questions": 2,
    "max_sub_questions": 5,
    "sub_question_min_iterations": 2,
    "sub_question_max_iterations": 5,
    "max_total_cost_usd": 3.0
  }
}
```

### Key Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `enable_hierarchical` | `false` | Enable hierarchical mode |
| `min_sub_questions` | `2` | Minimum decomposition |
| `max_sub_questions` | `5` | Maximum decomposition |
| `sub_question_min_iterations` | `2` | Min research per sub-question |
| `sub_question_max_iterations` | `5` | Max research per sub-question |

### Iteration Budget

Total iterations are divided:
```
Total iterations = decomposition (1) + research + synthesis (sub_questions + 1)

Example with 20 iterations, 4 sub-questions:
- Decomposition: 1 iteration
- Research: 20 - 1 - 4 - 1 = 14 iterations
- Sub-question synthesis: 4 iterations (1 per sub-question)
- Meta-synthesis: 1 iteration

Per sub-question allocation (weighted by priority):
- Sub-Q1 (priority 0.9): 3 iterations
- Sub-Q2 (priority 0.9): 3 iterations
- Sub-Q3 (priority 0.9): 3 iterations
- Sub-Q4 (priority 1.0): 5 iterations
```

## Example Session

### API Request

```bash
curl -X POST http://localhost:8000/api/research/sessions \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Compare the advantages and disadvantages of monolithic vs microservices architecture",
    "config": {
      "enable_hierarchical": true,
      "max_iterations": 18,
      "max_sub_questions": 4
    }
  }'
```

### Expected Flow

1. **Decomposition** (1 iteration)
   ```
   Sub-questions created:
   1. What are the key characteristics and advantages of monolithic architecture?
   2. What are the key characteristics and advantages of microservices architecture?
   3. What are the disadvantages and challenges of monolithic architecture?
   4. What are the disadvantages and challenges of microservices architecture?
   ```

2. **Research Phase** (12 iterations, ~3 per sub-question)
   ```
   Researching sub-question 1...
     - Found 5 sources on monolithic advantages
     - Created 3 findings

   Synthesizing sub-question 1...

   Researching sub-question 2...
     - Found 6 sources on microservices advantages
     - Created 4 findings

   ... continues for all sub-questions
   ```

3. **Meta-Synthesis** (1 iteration)
   ```
   Integrating all sub-question analyses...
   Creating comprehensive comparison...

   Final Answer: "Monolithic and microservices architectures each
   offer distinct advantages depending on project requirements..."
   ```

## Viewing Results

Results are available in the web UI under the **Results** tab:

### Results Page Shows:
- Original query
- Decomposition strategy used
- List of sub-questions with priorities
- Findings count per sub-question
- Iteration count per sub-question
- Individual sub-question syntheses
- Final meta-synthesis

### Per Sub-Question Details:
- Sub-question text
- Priority score
- Number of findings
- Number of iterations used
- Synthesis text
- Sources consulted

## Best Practices

### 1. **Craft Clear Complex Queries**

Good hierarchical queries have distinct aspects:
- ✅ "Compare X, Y, and Z"
- ✅ "Explain the causes, effects, and solutions to [problem]"
- ✅ "Evaluate [multiple perspectives] and determine which is stronger"

Avoid overly simple queries:
- ❌ "What is X?" (unless X is genuinely complex)
- ❌ "How do I [simple task]?"

### 2. **Set Appropriate Iteration Budgets**

More complex questions need more iterations:
- **2-3 sub-questions**: 15-20 iterations
- **4-5 sub-questions**: 20-30 iterations
- **Deep research**: 30+ iterations

### 3. **Monitor Costs**

Hierarchical mode uses more:
- **LLM calls**: Decomposition + multiple syntheses
- **External API calls**: Research per sub-question
- **Time**: Sequential sub-question processing

Adjust budgets accordingly:
```json
{
  "max_total_cost_usd": 3.0,  // Higher for hierarchical
  "max_external_calls": 15,    // More calls needed
  "prefer_local": true         // Use local models when possible
}
```

### 4. **Review Decomposition**

After submission, check the decomposition:
- Are sub-questions comprehensive?
- Do priorities make sense?
- Are any aspects missing?

Future versions may allow decomposition editing.

## Troubleshooting

### Issue: "No sub-questions were created"

**Cause**: Decomposition failed or query too simple

**Solution**:
1. Check query complexity - may be too simple for hierarchical mode
2. Review logs for decomposition errors
3. Try rephrasing query to emphasize multiple aspects
4. Fall back to flat mode if appropriate

### Issue: "Synthesis failed"

**Cause**: Model coordinator unavailable or budget exhausted

**Solution**:
1. Check model coordinator status
2. Increase budget limits
3. Ensure local models are running if `prefer_local: true`

### Issue: "Too many/few sub-questions"

**Cause**: LLM decomposition didn't respect min/max limits

**Solution**:
1. Adjust `min_sub_questions` and `max_sub_questions`
2. Rephrase query to be more/less complex
3. Check logs for truncation warnings

## Performance

### Hierarchical vs Flat Comparison

| Metric | Flat Mode | Hierarchical Mode |
|--------|-----------|-------------------|
| **Iterations** | 15 | 20-30 |
| **LLM Calls** | 1 synthesis | 1 decomp + N synth + 1 meta |
| **Time** | ~30-60s | ~60-120s |
| **Cost** | $0.10-0.50 | $0.50-2.00 |
| **Quality** | Good for simple queries | Better for complex queries |

### Optimization Tips

1. **Use local models** for decomposition and sub-syntheses (MEDIUM tier)
2. **Reserve external models** for final meta-synthesis (HIGH tier)
3. **Adjust sub-question limits** based on query complexity
4. **Set realistic budgets** - don't starve sub-questions of iterations

## Future Enhancements

Planned improvements:
- [ ] Interactive decomposition editing
- [ ] Nested sub-questions (multi-level decomposition)
- [ ] Parallel sub-question research
- [ ] User-defined decomposition strategies
- [ ] Visual decomposition tree in UI
- [ ] Export hierarchical results to structured formats

## Related Documentation

- [Configuration Guide](configuration.md) - All config options
- [Research Modes](research-modes.md) - Flat vs hierarchical comparison
- [Results Viewing](results-viewing.md) - Understanding research results
- [Architecture: Hierarchical Research](../architecture/hierarchical-research.md) - Technical deep-dive
- [Planning: Implementation](../../plans/hierarchical-research-architecture.md) - Detailed implementation plan
