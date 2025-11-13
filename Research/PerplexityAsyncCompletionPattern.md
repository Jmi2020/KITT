# Perplexity Async Completion Endpoint Pattern

**Status**: Future Enhancement (Low Priority)
**Use Case**: Multi-hour deep research tasks with `sonar-deep-research` model
**Created**: 2025-11-13

---

## Overview

The Perplexity API provides an asynchronous completion endpoint (`/async/chat/completions`) for long-running research queries that may take hours to complete. This pattern is designed for exhaustive multi-source research tasks.

**Current KITTY Implementation**: Uses synchronous `/chat/completions` endpoint only
**Future Enhancement**: Implement async pattern for high-value research goals

---

## When to Use Async Completions

Use async completions when:
- Research query requires exhaustive multi-source analysis (>30 minutes)
- Using `sonar-deep-research` model for comprehensive reports
- Goal impact score > 90 (critical strategic research)
- Budget allocated > $10.00 for single research task

**DO NOT use for:**
- Standard research gather tasks (< 5 minutes)
- Real-time user-facing queries
- Budget-constrained autonomous workflows

---

## API Pattern

### 1. **Submit Async Job**

```python
import httpx

async def submit_async_research(query: str, api_key: str) -> str:
    """Submit async research job to Perplexity.

    Returns:
        job_id: Unique identifier for polling
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    request_body = {
        "model": "sonar-deep-research",
        "messages": [{"role": "user", "content": query}],
        # Optional: Add search parameters
        "search_domain_filter": ["edu", "gov", "org"],
        "search_recency_filter": "month",
        "return_related_questions": True
    }

    async with httpx.AsyncClient(base_url="https://api.perplexity.ai", timeout=30) as client:
        response = await client.post("/async/chat/completions", json=request_body, headers=headers)
        response.raise_for_status()
        result = response.json()

        return result["job_id"]  # Job ID for status polling
```

### 2. **Poll for Completion**

```python
async def poll_async_job(job_id: str, api_key: str, poll_interval: int = 30) -> dict:
    """Poll async job until completion.

    Args:
        job_id: Job identifier from submit
        api_key: Perplexity API key
        poll_interval: Seconds between polls (default: 30s)

    Returns:
        Final result dict with research output
    """
    headers = {"Authorization": f"Bearer {api_key}"}

    async with httpx.AsyncClient(base_url="https://api.perplexity.ai", timeout=10) as client:
        while True:
            response = await client.get(f"/async/jobs/{job_id}", headers=headers)
            response.raise_for_status()
            status = response.json()

            if status["status"] == "completed":
                return status["result"]
            elif status["status"] == "failed":
                raise RuntimeError(f"Async job failed: {status.get('error')}")

            # Still processing, wait and retry
            await asyncio.sleep(poll_interval)
```

### 3. **Integration Pattern**

```python
async def execute_deep_research_task(task: Task) -> dict:
    """Execute deep research task with async completion.

    Workflow:
    1. Submit async job
    2. Update task status to in_progress
    3. Poll for completion (with progress logging)
    4. Return final research output
    """
    query = task.description
    api_key = settings.perplexity_api_key

    # Submit job
    job_id = await submit_async_research(query, api_key)
    logger.info(f"Async research job submitted: {job_id}")

    # Update task with job_id for recovery
    task.task_metadata["async_job_id"] = job_id
    task.task_metadata["job_status"] = "polling"

    # Poll for completion
    try:
        result = await poll_async_job(job_id, api_key, poll_interval=60)

        # Extract research output
        output = result["choices"][0]["message"]["content"]
        citations = result.get("citations", [])
        usage = result.get("usage", {})

        return {
            "task_type": "research_deep_async",
            "job_id": job_id,
            "output": output,
            "citations": citations,
            "usage": usage,
            "status": "completed"
        }

    except Exception as exc:
        logger.error(f"Async research job failed: {exc}")
        task.task_metadata["job_status"] = "failed"
        task.task_metadata["error"] = str(exc)
        raise
```

---

## Implementation Checklist

When implementing async completions in KITTY, follow this checklist:

### Phase 1: Infrastructure
- [ ] Add async job submission to `MCPClient` class
- [ ] Add async job polling method with exponential backoff
- [ ] Create background task handler for long-running polls
- [ ] Add job recovery mechanism (resume polling after restart)

### Phase 2: Task Executor Integration
- [ ] Add `research_deep_async` task type
- [ ] Update project_generator to create async tasks for high-impact goals
- [ ] Implement job status tracking in task metadata
- [ ] Add progress logging to reasoning.jsonl

### Phase 3: Error Handling
- [ ] Implement retry logic for failed jobs
- [ ] Add timeout handling (max 12 hours for deep research)
- [ ] Handle API rate limits and quota errors
- [ ] Implement graceful degradation (fallback to sync endpoint)

### Phase 4: Observability
- [ ] Add metrics for async job duration
- [ ] Track completion rate and failure reasons
- [ ] Monitor cost per async job
- [ ] Alert on jobs stuck in polling state

---

## Task Metadata Schema

For async research tasks, store the following in `task.task_metadata`:

```python
{
    "task_type": "research_deep_async",
    "search_queries": ["query 1", "query 2"],
    "perplexity_model": "sonar-deep-research",
    "max_duration_hours": 12,
    "async_job_id": "job_abc123",      # Set after submission
    "job_status": "polling",           # polling | completed | failed
    "poll_start_time": "2025-01-15T04:30:00Z",
    "poll_count": 24,                   # Number of polls executed
    "last_poll_time": "2025-01-15T05:54:00Z"
}
```

---

## Cost Considerations

**Async completions with sonar-deep-research are expensive:**
- Estimated cost: $5-$50 per query depending on depth
- Only use for critical strategic research
- Set strict budget limits in task metadata

**Budget Enforcement:**
```python
if task.task_metadata.get("perplexity_model") == "sonar-deep-research":
    max_cost = task.task_metadata.get("max_cost_usd", 10.0)
    if max_cost < 5.0:
        logger.warning(f"Budget too low for deep research: ${max_cost}")
        # Fallback to sonar-pro instead
        task.task_metadata["perplexity_model"] = "sonar-pro"
```

---

## Example: High-Value Research Goal

```python
# Goal identified by autonomous system
goal = Goal(
    id=str(uuid.uuid4()),
    goal_type=GoalType.research,
    description="Comprehensive analysis of sustainable 3D printing materials and supply chains",
    rationale="Critical for Phase 4 sustainability initiative. 15+ print failures due to material inconsistencies.",
    estimated_budget=25.00,  # High budget triggers deep research
    estimated_duration_hours=48,
    status=GoalStatus.approved,
    goal_metadata={
        "source": "strategic_initiative",
        "impact_score": 95,  # Very high impact
        "use_async_research": True,
        "priority": "critical"
    }
)

# Project generator creates async research task
task = Task(
    id=str(uuid.uuid4()),
    project_id=project.id,
    title="Deep research: Sustainable 3D printing materials",
    description="Exhaustive multi-source analysis of sustainable filament options, supplier reliability, cost trends, and material properties.",
    status=TaskStatus.pending,
    priority=TaskPriority.critical,
    task_metadata={
        "task_type": "research_deep_async",
        "perplexity_model": "sonar-deep-research",
        "max_cost_usd": 25.00,
        "max_duration_hours": 12,
        "search_domain_filter": ["edu", "gov", "ieee.org", "nature.com"],
        "search_recency_filter": "year",
        "return_related_questions": True
    }
)
```

---

## Testing Strategy

**Unit Tests:**
```python
@pytest.mark.asyncio
async def test_async_job_submission():
    """Test async job submission returns job_id."""
    client = MCPClient(base_url="https://api.perplexity.ai", api_key="test_key")
    job_id = await client.submit_async_job(query="test query", model="sonar-deep-research")
    assert job_id.startswith("job_")

@pytest.mark.asyncio
async def test_async_job_polling_completion():
    """Test polling completes when job finishes."""
    # Mock API responses
    pass

@pytest.mark.asyncio
async def test_async_job_timeout():
    """Test polling times out after max duration."""
    pass
```

**Integration Tests:**
```bash
# Test with real Perplexity API (requires API key and credits)
pytest tests/integration/test_async_research.py -v --perplexity-api-key=$PERPLEXITY_API_KEY
```

---

## References

- [Perplexity API Documentation](https://docs.perplexity.ai/)
- [Async Completion Endpoint Spec](https://docs.perplexity.ai/llms-full.txt)
- KITTY Implementation: `services/brain/src/brain/autonomous/task_executor.py`
- Cost Tracking: `Research/PerplexityIntegrationAnalysis.md`

---

**Status**: Documentation complete. Implementation deferred to future sprint when high-value deep research use case emerges.

**Estimated Implementation Effort**: 8-12 hours (Infrastructure + Integration + Testing)
