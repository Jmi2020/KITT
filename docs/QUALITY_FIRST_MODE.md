# Quality-First Mode Configuration

## Overview

KITTY can be configured to prioritize **answer quality over speed**, allowing extensive research, multi-step reasoning, and lengthy tool iterations without timing out. This mode is ideal when you need the best possible answer regardless of latency.

---

## Philosophy

**Quality > Speed**: The system will take as long as needed to:
- Conduct thorough research using all available tools
- Iterate on CAD designs until printability is optimized
- Run multiple reasoning cycles to ensure accuracy
- Gather comprehensive context from memory and external sources

**Timeout Strategy**: Tasks only timeout if GPU/CPU are idle (not processing), preventing premature cancellation of active inference.

---

## Configuration

### 1. Environment Variables (.env)

```bash
# ===== Quality-First Mode =====

# LangGraph Configuration
BRAIN_USE_LANGGRAPH=true
BRAIN_LANGGRAPH_ROLLOUT_PERCENT=100  # Route all traffic through LangGraph

# Timeout Settings (in seconds)
# Set very high to allow long-running inference
BRAIN_REQUEST_TIMEOUT=600            # 10 minutes for brain requests
LLAMACPP_TIMEOUT=300                 # 5 minutes per llama.cpp call
LLAMACPP_Q4_TIMEOUT=180              # 3 minutes for Q4 (fast model)
LLAMACPP_F16_TIMEOUT=600             # 10 minutes for F16 (deep reasoning)

# Tool Execution Timeouts
TOOL_EXECUTION_TIMEOUT=300           # 5 minutes per tool
CAD_GENERATION_TIMEOUT=600           # 10 minutes for CAD generation
FABRICATION_TIMEOUT=120              # 2 minutes for printer queries

# Deep Reasoning Configuration
MAX_REASONING_STEPS=10               # Allow up to 10 reasoning iterations (default: 5)
MAX_TOOL_RETRIES=5                   # Retry failed tools up to 5 times (default: 2)
ENABLE_TOOL_REFINEMENT=true          # Re-execute tools with refined params on F16

# Research Depth
ENABLE_DEEP_SEARCH=true              # Always use deep memory search
MEMORY_DEEP_THRESHOLD=0.50           # Lower threshold = more deep searches (default: 0.60)
MEMORY_INITIAL_LIMIT=5               # Retrieve more memories initially (default: 3)
MEMORY_DEEP_LIMIT=10                 # Retrieve many memories on deep search (default: 5)
```

### 2. Docker Compose Overrides

Update `infra/compose/docker-compose.yml` to pass timeout env vars:

```yaml
services:
  brain:
    environment:
      # ... existing vars ...
      BRAIN_REQUEST_TIMEOUT: ${BRAIN_REQUEST_TIMEOUT:-600}
      LLAMACPP_TIMEOUT: ${LLAMACPP_TIMEOUT:-300}
      LLAMACPP_Q4_TIMEOUT: ${LLAMACPP_Q4_TIMEOUT:-180}
      LLAMACPP_F16_TIMEOUT: ${LLAMACPP_F16_TIMEOUT:-600}
      MAX_REASONING_STEPS: ${MAX_REASONING_STEPS:-10}
      MAX_TOOL_RETRIES: ${MAX_TOOL_RETRIES:-5}
```

### 3. Nginx/Gateway Timeout (if applicable)

If using Nginx or API Gateway, increase proxy timeouts:

```nginx
location /api/ {
    proxy_read_timeout 600s;    # 10 minutes
    proxy_connect_timeout 30s;
    proxy_send_timeout 600s;
}
```

---

## Monitoring Active Inference

Use the monitoring scripts to verify inference is progressing (not stuck):

### Real-Time Monitoring

```bash
# Start continuous monitoring (5-second intervals)
./ops/scripts/monitor-inference.sh 5

# Output shows:
# - GPU power usage
# - CPU/Memory per llama-server
# - Active network connections
# - Recent log activity
# - "⚡ INFERENCE IN PROGRESS" when models are working
```

### Check if Model is Active (Not Stuck)

```bash
# Check Q4 server
./ops/scripts/check-inference-active.sh q4
# Exit 0 = active, Exit 1 = idle/stuck

# Check F16 server
./ops/scripts/check-inference-active.sh f16
```

### Integrate with Timeout Logic (Future Enhancement)

```python
# Pseudo-code for adaptive timeout in brain service
import subprocess

def is_inference_active(model="q4"):
    """Check if llama.cpp is actively processing (not stuck)."""
    result = subprocess.run(
        ["./ops/scripts/check-inference-active.sh", model],
        capture_output=True
    )
    return result.returncode == 0

async def call_llama_with_adaptive_timeout(prompt, model="q4"):
    """Call llama.cpp with timeout that extends while inference is active."""
    base_timeout = 180  # 3 minutes baseline
    max_timeout = 600   # 10 minutes maximum
    check_interval = 30 # Check every 30 seconds

    elapsed = 0
    while elapsed < max_timeout:
        try:
            # Try inference with incremental timeout
            result = await asyncio.wait_for(
                llama_client.generate(prompt, model=model),
                timeout=check_interval
            )
            return result
        except asyncio.TimeoutError:
            # Check if still processing
            if is_inference_active(model):
                logger.info(f"Inference still active after {elapsed}s, extending timeout...")
                elapsed += check_interval
                continue
            else:
                raise TimeoutError(f"Inference stuck after {elapsed}s (CPU idle)")

    raise TimeoutError(f"Max timeout {max_timeout}s exceeded")
```

---

## Performance Expectations

### Quality-First Mode (Default Config Above)

| Query Type | Expected Latency | Max Iterations | Tools Used |
|------------|------------------|----------------|------------|
| Simple | 5-30 seconds | 1 | 0-1 |
| Medium | 30-120 seconds | 2-3 | 1-3 |
| Complex | 2-10 minutes | 5-10 | 3-8 |
| CAD Design | 5-15 minutes | 3-5 | 4-10 |
| Multi-Step Research | 10-30 minutes | 8-15 | 10+ |

### Speed-First Mode (Traditional)

| Query Type | Expected Latency | Max Iterations | Tools Used |
|------------|------------------|----------------|------------|
| Simple | 1-5 seconds | 1 | 0 |
| Medium | 5-15 seconds | 1 | 0-1 |
| Complex | 15-60 seconds | 2 | 1-2 |

---

## SLO Adjustments

When running in Quality-First mode, adjust SLOs accordingly:

**Original SLOs** (Speed-Optimized):
- Q4 P95 latency: < 2 seconds
- F16 P95 latency: < 10 seconds
- Tool success rate: > 80%

**Quality-First SLOs**:
- Q4 P95 latency: < 30 seconds (15x slower, but more thorough)
- F16 P95 latency: < 5 minutes (30x slower, allows deep reasoning)
- Tool success rate: > 95% (more retries = higher success)
- Answer quality score: > 0.9 (measured by self-evaluation)

**Update Prometheus Alerts**:

```yaml
# infra/prometheus/alerts/langgraph-alerts-quality-mode.yml

- alert: Q4LatencyDegradation
  expr: histogram_quantile(0.95, ...) > 30  # Changed from 2s
  for: 5m

- alert: F16LatencyDegradation
  expr: histogram_quantile(0.95, ...) > 300  # Changed from 10s
  for: 10m

- alert: LowQualityResponses
  expr: avg(brain_self_evaluation_score) < 0.9
  for: 15m
  annotations:
    summary: "Responses not meeting quality threshold"
```

---

## Grafana Dashboard Adjustments

Update dashboard time ranges and thresholds for Quality-First mode:

```json
{
  "panels": [
    {
      "title": "Q4 Latency (P95)",
      "yaxes": [
        {
          "max": 30,  // Changed from 2
          "label": "seconds"
        }
      ],
      "thresholds": [
        {
          "value": 30,
          "color": "red"
        }
      ]
    },
    {
      "title": "F16 Latency (P95)",
      "yaxes": [
        {
          "max": 300,  // Changed from 10
          "label": "seconds"
        }
      ],
      "thresholds": [
        {
          "value": 300,
          "color": "red"
        }
      ]
    },
    {
      "title": "Answer Quality Score",
      "yaxes": [
        {
          "min": 0.5,
          "max": 1.0,
          "label": "score"
        }
      ],
      "thresholds": [
        {
          "value": 0.9,
          "color": "green"
        }
      ]
    }
  ]
}
```

---

## Testing Quality-First Mode

### Test Case 1: Deep Research Query

```bash
# Query requiring extensive research
kitty-cli say "Compare the thermodynamic efficiency of heat exchangers in HVAC systems across different refrigerants (R-410A, R-32, R-454B), considering environmental impact, cost, and performance in both heating and cooling modes. Provide detailed analysis with citations."

# Expected behavior:
# - F16 escalation triggered (complexity > 0.7)
# - Multiple research tools invoked
# - 5-10 reasoning iterations
# - Latency: 5-15 minutes
# - Self-evaluation score: > 0.9
```

### Test Case 2: Iterative CAD Design

```bash
# Query requiring design iteration
kitty-cli say "Design a parametric phone stand with adjustable viewing angles (15°-75°), cable management, optimized for FDM printing with minimal supports, iterate until printability score > 95%"

# Expected behavior:
# - CAD generation tool called
# - STL analysis tool called
# - Design refinement iterations (3-5x)
# - Each iteration improves printability
# - Final design meets spec
# - Latency: 10-20 minutes
```

### Test Case 3: Multi-Tool Workflow

```bash
# Query requiring orchestrated tool execution
kitty-cli say "Research best practices for 3D printing PETG, design a test print with those parameters, analyze for defects, queue to the best available printer"

# Expected behavior:
# - Web search for PETG best practices
# - CAD generation based on research
# - STL analysis
# - Printer selection
# - Job queuing
# - 8-12 tool calls total
# - Latency: 15-25 minutes
```

---

## Debugging Timeouts

If you see timeout errors despite Quality-First configuration:

### 1. Check Current Timeouts

```bash
# In brain container
docker exec compose-brain-1 printenv | grep TIMEOUT

# Should show high values:
# BRAIN_REQUEST_TIMEOUT=600
# LLAMACPP_TIMEOUT=300
# LLAMACPP_F16_TIMEOUT=600
```

### 2. Monitor llama.cpp During Query

```bash
# Terminal 1: Start monitoring
./ops/scripts/monitor-inference.sh 2

# Terminal 2: Submit query
kitty-cli say "Your complex query here"

# Watch Terminal 1 for:
# - "⚡ INFERENCE IN PROGRESS" (good!)
# - CPU usage > 50% (actively processing)
# - Active connections > 0
```

### 3. Check llama.cpp Logs

```bash
# See if inference is completing or erroring
tail -100 .logs/llamacpp-f16.log

# Look for:
# - "completion finished" (success)
# - "connection closed" (client timeout)
# - "error" (model error)
```

### 4. Adjust Timeouts Higher

```bash
# If still timing out, increase further
export LLAMACPP_F16_TIMEOUT=1200  # 20 minutes
export MAX_REASONING_STEPS=15     # More iterations

# Restart brain service
docker compose restart brain
```

---

## Trade-offs

**Advantages of Quality-First Mode**:
- ✅ Best possible answers with thorough research
- ✅ Higher tool success rate (more retries)
- ✅ Deep reasoning on complex queries
- ✅ Iterative refinement until quality threshold met

**Disadvantages**:
- ❌ Much higher latency (10-30 minutes for complex queries)
- ❌ Increased GPU/CPU utilization
- ❌ Higher memory usage (longer context windows)
- ❌ Cannot serve many concurrent users (1-2 at a time)

**Best For**:
- Personal assistant (single user)
- Design iteration workflows
- Research and analysis tasks
- Critical decision support
- CAD/fabrication preparation

**Not Suitable For**:
- Public API with many users
- Real-time chat applications
- Simple Q&A that needs instant response
- High-throughput production systems

---

## Rollback to Speed-First Mode

To revert to speed-optimized mode:

```bash
# Edit .env
BRAIN_REQUEST_TIMEOUT=60             # 1 minute
LLAMACPP_TIMEOUT=30                  # 30 seconds
LLAMACPP_F16_TIMEOUT=60              # 1 minute
MAX_REASONING_STEPS=5                # Fewer iterations
MAX_TOOL_RETRIES=2                   # Fewer retries

# Restart services
docker compose restart brain
```

---

**Document Version**: 1.0
**Last Updated**: 2025-11-12
**Compatible With**: LangGraph Multi-Agent v1.0+
