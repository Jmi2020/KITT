# KITT Research Pipeline Testing Guide

**Created:** 2025-01-16
**Purpose:** Guide for testing the autonomous research pipeline and permission system
**Last Updated:** 2025-01-16

---

## Quick Start: Essential Tests

### 1. Run Core Permission System Tests

```bash
# Navigate to project root
cd /home/user/KITT

# Run all permission system tests
pytest tests/unit/test_unified_permission_gate.py -v
pytest tests/unit/test_research_tool_executor.py -v
pytest tests/integration/test_research_permission_flow.py -v -m integration

# Or run all together
pytest tests/unit/test_unified_permission_gate.py \
       tests/unit/test_research_tool_executor.py \
       tests/integration/test_research_permission_flow.py -v
```

**Expected Results:**
- ✅ All tests should pass
- ✅ 50+ test cases executed
- ✅ ~95%+ coverage for permission system

**If tests fail:**
- Check Redis is running: `docker ps | grep redis`
- Check PostgreSQL is running: `docker ps | grep postgres`
- Check environment variables are set (see Configuration section below)

---

## Test Suite Overview

### Unit Tests

#### 1. UnifiedPermissionGate (`test_unified_permission_gate.py`)

**What it tests:**
- Layer 1: I/O Control checks (provider enabled/disabled, offline mode)
- Layer 2: Budget checks (sufficient/insufficient funds)
- Layer 3: Runtime approval (trivial/low/high cost tiers)
- User prompting with omega password
- Cost recording

**Run:**
```bash
pytest tests/unit/test_unified_permission_gate.py -v
```

**Key test cases:**
- `test_check_io_control_enabled` - Provider enabled
- `test_check_io_control_disabled` - Provider disabled
- `test_check_budget_sufficient` - Budget available
- `test_check_budget_insufficient` - Budget depleted
- `test_runtime_approval_trivial_auto_approve` - Auto-approve < $0.01
- `test_runtime_approval_low_prompt` - Prompt for < $0.10
- `test_runtime_approval_high_always_prompt` - Always prompt >= $0.10

#### 2. ResearchToolExecutor (`test_research_tool_executor.py`)

**What it tests:**
- Free tool execution (web_search, fetch_webpage)
- Paid tool execution with permissions (research_deep)
- Permission denied scenarios
- Memory tools (store_memory, recall_memory)
- Error handling

**Run:**
```bash
pytest tests/unit/test_research_tool_executor.py -v
```

**Key test cases:**
- `test_execute_web_search` - Free tool always works
- `test_execute_research_deep_approved` - Paid tool with approval
- `test_execute_research_deep_denied_io_control` - Blocked by I/O Control
- `test_execute_research_deep_user_denied` - User denies omega prompt
- `test_execute_store_memory` - Memory storage
- `test_execute_memory_no_server` - Graceful failure

### Integration Tests

#### 3. Complete Permission Flow (`test_research_permission_flow.py`)

**What it tests:**
- End-to-end permission flow (I/O Control → Budget → Approval → Execution)
- Multiple blocking scenarios
- Cost tracking accuracy
- Real-world usage patterns

**Run:**
```bash
pytest tests/integration/test_research_permission_flow.py -v -m integration
```

**Key test cases:**
- `test_full_flow_web_search_allowed` - Free tool happy path
- `test_full_flow_research_deep_auto_approved` - Trivial cost happy path
- `test_full_flow_blocked_by_io_control_provider_disabled` - I/O Control blocks
- `test_full_flow_blocked_by_budget_insufficient_funds` - Budget blocks
- `test_full_flow_multiple_tools_mixed_success` - Mixed tool execution
- `test_full_flow_accurate_cost_tracking` - Cost tracking verification

---

## Running Tests by Category

### All Permission Tests
```bash
pytest tests/unit/test_unified_permission_gate.py \
       tests/unit/test_research_tool_executor.py \
       tests/integration/test_research_permission_flow.py -v
```

### Only Unit Tests
```bash
pytest tests/unit/test_unified_permission_gate.py \
       tests/unit/test_research_tool_executor.py -v
```

### Only Integration Tests
```bash
pytest tests/integration/test_research_permission_flow.py -v -m integration
```

### Run with Coverage Report
```bash
pytest tests/unit/test_unified_permission_gate.py \
       tests/unit/test_research_tool_executor.py \
       tests/integration/test_research_permission_flow.py \
       --cov=brain.research.permissions \
       --cov=brain.research.tools \
       --cov-report=html \
       --cov-report=term

# View HTML report
open htmlcov/index.html
```

### Run Specific Test
```bash
# Run single test by name
pytest tests/unit/test_unified_permission_gate.py::TestUnifiedPermissionGate::test_check_io_control_enabled -v

# Run all tests in a class
pytest tests/unit/test_unified_permission_gate.py::TestUnifiedPermissionGate -v
```

---

## Manual Testing: Research Pipeline

### Prerequisites

**1. Check Services Running:**
```bash
# Redis (for I/O Control)
docker ps | grep redis
# Expected: redis container running on port 6379

# PostgreSQL (for checkpoints)
docker ps | grep postgres
# Expected: postgres container running on port 5432

# Mem0 MCP (for memory)
docker ps | grep mem0
# Expected: mem0-mcp container running on port 8765
```

**2. Check Environment Variables:**
```bash
# Required for research pipeline
echo $DATABASE_URL              # PostgreSQL connection
echo $REDIS_HOST                # Redis host (default: redis)
echo $REDIS_PORT                # Redis port (default: 6379)

# Optional for Perplexity (research_deep tool)
echo $PERPLEXITY_API_KEY        # Your Perplexity API key
echo $PERPLEXITY_BASE_URL       # Default: https://api.perplexity.ai
echo $PERPLEXITY_MODEL          # Default: sonar

# Optional for budget control
echo $RESEARCH_BUDGET_USD       # Default: 2.0
echo $RESEARCH_EXTERNAL_CALL_LIMIT  # Default: 10
echo $API_OVERRIDE_PASSWORD     # Default: omega
echo $AUTO_APPROVE_TRIVIAL      # Default: true
echo $AUTO_APPROVE_LOW_COST     # Default: false
```

**3. Check Database Schema:**
```bash
# Connect to PostgreSQL
psql $DATABASE_URL

# Check tables exist
\dt

# Expected tables:
# - checkpoints
# - checkpoint_blobs
# - checkpoint_writes
# - research_sessions
# - research_iterations
# - research_findings
# - research_strategies
# - research_saturation

# Exit psql
\q
```

### Manual Test 1: Free Web Search (No Permission Needed)

**Purpose:** Verify basic tool execution without permission checks

```bash
# Start Python shell
python3

>>> from brain.research.tools.mcp_integration import ResearchToolExecutor, ToolExecutionContext, ToolType
>>> from mcp.servers.research_server import ResearchMCPServer
>>> from decimal import Decimal
>>> import asyncio

>>> # Initialize
>>> research_server = ResearchMCPServer()
>>> executor = ResearchToolExecutor(
...     research_server=research_server,
...     memory_server=None,
...     permission_gate=None,
...     budget_manager=None
... )

>>> # Create context
>>> context = ToolExecutionContext(
...     session_id="manual_test",
...     user_id="test_user",
...     iteration=1,
...     budget_remaining=Decimal("2.0"),
...     external_calls_remaining=10,
...     perplexity_enabled=True,
...     offline_mode=False,
...     cloud_routing_enabled=True
... )

>>> # Execute web search
>>> result = asyncio.run(executor.execute(
...     tool_name=ToolType.WEB_SEARCH,
...     arguments={"query": "llama.cpp optimization"},
...     context=context
... ))

>>> # Verify
>>> print(f"Success: {result.success}")
>>> print(f"Cost: ${result.cost_usd}")
>>> print(f"Results: {len(result.data.get('results', []))}")

# Expected:
# Success: True
# Cost: $0.00
# Results: 1-10
```

### Manual Test 2: Permission System Integration

**Purpose:** Verify complete permission flow with I/O Control and Budget

```bash
# Start Python shell
python3

>>> from brain.research.permissions import UnifiedPermissionGate
>>> from brain.research.models.budget import BudgetManager, BudgetConfig
>>> from brain.research.tools.mcp_integration import ResearchToolExecutor, ToolExecutionContext, ToolType
>>> from mcp.servers.research_server import ResearchMCPServer
>>> from decimal import Decimal
>>> import asyncio

>>> # Initialize budget manager
>>> budget_config = BudgetConfig(
...     max_total_cost_usd=Decimal("2.0"),
...     max_external_calls=10
... )
>>> budget_manager = BudgetManager(config=budget_config)

>>> # Initialize permission gate (without I/O Control for simplicity)
>>> permission_gate = UnifiedPermissionGate(
...     io_control_state_manager=None,
...     budget_manager=budget_manager,
...     omega_password="omega",
...     auto_approve_trivial=True,
...     auto_approve_low_cost=False
... )

>>> # Initialize executor
>>> research_server = ResearchMCPServer()
>>> executor = ResearchToolExecutor(
...     research_server=research_server,
...     memory_server=None,
...     permission_gate=permission_gate,
...     budget_manager=budget_manager
... )

>>> # Create context
>>> context = ToolExecutionContext(
...     session_id="manual_test",
...     user_id="test_user",
...     iteration=1,
...     budget_remaining=Decimal("2.0"),
...     external_calls_remaining=10,
...     perplexity_enabled=True,
...     offline_mode=False,
...     cloud_routing_enabled=True
... )

>>> # Test 1: Free tool (should work)
>>> result = asyncio.run(executor.execute(
...     tool_name=ToolType.WEB_SEARCH,
...     arguments={"query": "test"},
...     context=context
... ))
>>> print(f"Web search success: {result.success}, cost: ${result.cost_usd}")

>>> # Test 2: Check budget
>>> status = asyncio.run(budget_manager.get_status())
>>> print(f"Budget used: ${status.total_cost_usd}, remaining: ${status.budget_remaining}")

# Expected:
# Web search success: True, cost: $0.00
# Budget used: $0.00, remaining: $2.00
```

### Manual Test 3: Research Deep with Perplexity (If API Key Available)

**Purpose:** Verify paid tool execution with permission gating

```bash
# Only if PERPLEXITY_API_KEY is set
>>> import os
>>> if not os.getenv("PERPLEXITY_API_KEY"):
...     print("⚠️  PERPLEXITY_API_KEY not set, skipping this test")
... else:
...     from brain.routing.cloud_clients import MCPClient
...
...     # Create Perplexity client
...     perplexity_client = MCPClient(
...         base_url="https://api.perplexity.ai",
...         api_key=os.getenv("PERPLEXITY_API_KEY"),
...         model="sonar"
...     )
...
...     # Create research server with Perplexity
...     research_server = ResearchMCPServer(perplexity_client=perplexity_client)
...
...     # Execute research_deep (will be auto-approved if < $0.01)
...     result = asyncio.run(executor.execute(
...         tool_name=ToolType.RESEARCH_DEEP,
...         arguments={"query": "vector databases comparison"},
...         context=context
...     ))
...
...     print(f"Research deep success: {result.success}")
...     print(f"Cost: ${result.cost_usd}")
...     if result.success:
...         print(f"Research output length: {len(result.data.get('research', ''))}")
...     else:
...         print(f"Error: {result.error}")

# Expected (if API key valid):
# Research deep success: True
# Cost: $0.001 - $0.005
# Research output length: 500-2000 chars

# Expected (if no API key):
# ⚠️  PERPLEXITY_API_KEY not set, skipping this test
```

---

## Troubleshooting

### Test Failures

#### "Redis connection failed"
```bash
# Check Redis is running
docker ps | grep redis

# If not running, start it
docker-compose up -d redis

# Verify connection
redis-cli ping
# Expected: PONG
```

#### "PostgreSQL connection failed"
```bash
# Check PostgreSQL is running
docker ps | grep postgres

# If not running, start it
docker-compose up -d postgres

# Verify connection
psql $DATABASE_URL -c "SELECT 1"
# Expected: 1
```

#### "ModuleNotFoundError: No module named 'brain.research.permissions'"
```bash
# Install brain service in development mode
cd services/brain
pip install -e .

# Or install all services
cd /home/user/KITT
pip install -e services/brain
pip install -e services/common
pip install -e services/mcp
```

#### "Import Error: cannot import name 'UnifiedPermissionGate'"
```bash
# Check the file exists
ls -la services/brain/src/brain/research/permissions/unified_gate.py

# If missing, you're on wrong branch
git branch
# Should show: claude/debug-research-pipeline-01TG5VrtVjMtV2X9avnNk5VB

# Switch to correct branch
git checkout claude/debug-research-pipeline-01TG5VrtVjMtV2X9avnNk5VB
```

#### "Test hangs or times out"
```bash
# Kill hanging tests
pkill -f pytest

# Run single test to debug
pytest tests/unit/test_unified_permission_gate.py::TestUnifiedPermissionGate::test_check_io_control_enabled -v -s

# Check for async issues
# If test uses async, make sure pytest-asyncio is installed
pip install pytest-asyncio
```

### Permission System Issues

#### "Permission denied" when it should be approved
```bash
# Check I/O Control state
python3 -c "
from common.io_control.state_manager import FeatureStateManager
import redis

redis_client = redis.Redis(host='redis', port=6379, decode_responses=False)
state_manager = FeatureStateManager(redis_client=redis_client)
state = state_manager.get_current_state()

print('Perplexity enabled:', state.get('perplexity_api'))
print('OpenAI enabled:', state.get('openai_api'))
print('Offline mode:', state.get('offline_mode'))
print('Cloud routing:', state.get('cloud_routing'))
"

# If provider disabled, enable it in I/O Control dashboard
# or set environment variable
export PERPLEXITY_API_KEY=your_key_here
```

#### "Budget exceeded" but budget should be available
```bash
# Check budget status
python3 -c "
from brain.research.models.budget import BudgetManager, BudgetConfig
from decimal import Decimal
import asyncio

async def check_budget():
    config = BudgetConfig(max_total_cost_usd=Decimal('2.0'))
    manager = BudgetManager(config=config)
    status = await manager.get_status()
    print(f'Total cost: \${status.total_cost_usd}')
    print(f'Budget remaining: \${status.budget_remaining}')
    print(f'External calls: {status.external_calls_used}')

asyncio.run(check_budget())
"
```

---

## Test Data and Fixtures

### Mock Data Used in Tests

**MockIOControlStateManager:**
```python
# All enabled
{
    "perplexity_api": True,
    "openai_api": True,
    "anthropic_api": True,
    "offline_mode": False,
    "cloud_routing": True,
}

# All disabled
{
    "perplexity_api": False,
    "openai_api": False,
    "anthropic_api": False,
    "offline_mode": True,
    "cloud_routing": False,
}
```

**MockBudgetManager:**
```python
# Ample budget
BudgetConfig(
    max_total_cost_usd=Decimal("5.0"),
    max_external_calls=20
)

# Limited budget
BudgetConfig(
    max_total_cost_usd=Decimal("0.10"),
    max_external_calls=2
)
```

**Cost Tiers:**
```python
Trivial: < $0.01   # Example: $0.005
Low:     < $0.10   # Example: $0.05
High:    >= $0.10  # Example: $0.50
```

---

## CI/CD Integration

### GitHub Actions Workflow

Add to `.github/workflows/test-research-pipeline.yml`:

```yaml
name: Research Pipeline Tests

on:
  push:
    branches: [ main, develop, claude/* ]
  pull_request:
    branches: [ main, develop ]

jobs:
  test-permissions:
    runs-on: ubuntu-latest

    services:
      redis:
        image: redis:7-alpine
        ports:
          - 6379:6379
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

      postgres:
        image: postgres:15-alpine
        env:
          POSTGRES_PASSWORD: postgres
          POSTGRES_DB: kitt_test
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -e services/brain
          pip install -e services/common
          pip install -e services/mcp
          pip install pytest pytest-asyncio pytest-cov

      - name: Run permission system tests
        env:
          REDIS_HOST: localhost
          REDIS_PORT: 6379
          DATABASE_URL: postgresql://postgres:postgres@localhost:5432/kitt_test
        run: |
          pytest tests/unit/test_unified_permission_gate.py \
                 tests/unit/test_research_tool_executor.py \
                 tests/integration/test_research_permission_flow.py \
                 --cov=brain.research.permissions \
                 --cov=brain.research.tools \
                 --cov-report=xml \
                 --cov-report=term \
                 -v

      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          file: ./coverage.xml
```

---

## Performance Benchmarks

### Expected Test Execution Times

| Test Suite | Tests | Expected Time | Acceptable Max |
|------------|-------|---------------|----------------|
| test_unified_permission_gate.py | 20+ | < 5s | 10s |
| test_research_tool_executor.py | 15+ | < 3s | 8s |
| test_research_permission_flow.py | 10+ | < 8s | 15s |
| **Total** | **50+** | **< 20s** | **40s** |

### Running Benchmarks

```bash
# Run with timing
pytest tests/ --durations=10

# Run with profiling
pytest tests/ --profile

# Generate performance report
pytest tests/ --benchmark-only
```

---

## Coverage Goals

### Current Coverage (as of 2025-01-16)

| Module | Coverage | Goal |
|--------|----------|------|
| `permissions/unified_gate.py` | 95%+ | 95% |
| `tools/mcp_integration.py` | 85%+ | 90% |
| `models/budget.py` | 80%+ | 85% |
| `models/coordinator.py` | 75%+ | 80% |

### Generating Coverage Reports

```bash
# HTML report
pytest tests/ \
  --cov=brain.research.permissions \
  --cov=brain.research.tools \
  --cov=brain.research.models \
  --cov-report=html

# View report
open htmlcov/index.html

# Terminal report
pytest tests/ \
  --cov=brain.research.permissions \
  --cov=brain.research.tools \
  --cov-report=term-missing
```

---

## Next Steps

1. **Run all tests** to verify system is working
2. **Check test coverage** to identify gaps
3. **Add more integration tests** for graph nodes (Phase 5)
4. **Test with real Perplexity API** (if available)
5. **Benchmark performance** on production workload

---

## Testing Research Graph Wiring

### Overview

The research graph uses dependency injection to access infrastructure components. Test the wiring to ensure nodes use real execution instead of simulated data.

### Test File

```bash
pytest tests/integration/test_research_graph_wiring.py -v -m integration
```

### What's Tested

1. **Component Factory**: ResearchComponents dataclass creation
2. **Global Registration**: set_global_components() / get_global_components()
3. **Real Execution**: execute_iteration uses tool_executor
4. **Fallback Behavior**: Simulated execution when components unavailable
5. **Tool Selection**: High-priority tasks use research_deep

### Verification

Check brain service logs for component registration:

```
INFO: Research components registered: {'fully_wired': True, 'tool_executor': True, ...}
INFO: Executing 3 tasks with real tool executor
INFO: Task task_1 executed with web_search: cost=$0.00
```

If you see `"Tool executor not available, using simulated execution"`, components weren't properly registered.

**See**: `Research/ResearchGraphWiring.md` for full wiring documentation.

---

## Testing Semantic Cache (TTL & Eviction)

### Overview

The semantic cache stores LLM prompt/response pairs in Redis Streams for reuse. It now includes TTL-based expiration and max entry limits to prevent unbounded growth.

### Configuration

Environment variables (optional - defaults shown):

```bash
export SEMANTIC_CACHE_TTL_SECONDS=43200     # 12 hours default
export SEMANTIC_CACHE_MAX_ENTRIES=10000     # 10,000 entries default
```

### Testing Cache Behavior

#### 1. Test Basic Cache Operations

```python
from common.cache import SemanticCache, CacheRecord

# Initialize cache
cache = SemanticCache()

# Store entry
record = CacheRecord(
    key="test_key",
    prompt="What is AI?",
    response="Artificial Intelligence is...",
    confidence=0.95
)
entry_id = cache.store(record)

# Fetch entry (should hit)
result = cache.fetch("test_key")
assert result is not None
assert result.response == "Artificial Intelligence is..."

# Check stats
stats = cache.get_stats()
print(f"Entries: {stats.entry_count}")
print(f"Hit rate: {stats.hit_rate:.2%}")
print(f"Hits: {stats.hits}, Misses: {stats.misses}")
```

#### 2. Test TTL Expiration

```python
import time
from common.cache import SemanticCache

# Create cache with 5-second TTL
cache = SemanticCache(ttl_seconds=5)

# Store entry
cache.store(record)

# Fetch immediately (should hit)
assert cache.fetch("test_key") is not None

# Wait for TTL expiration
time.sleep(6)

# Fetch after TTL (should miss - stream expired)
assert cache.fetch("test_key") is None
```

#### 3. Test Max Entries Trimming

```python
from common.cache import SemanticCache, CacheRecord

# Create cache with small max
cache = SemanticCache(max_entries=10)

# Add 20 entries
for i in range(20):
    record = CacheRecord(
        key=f"key_{i}",
        prompt=f"Question {i}",
        response=f"Answer {i}",
        confidence=0.9
    )
    cache.store(record)

# Check stats - should be trimmed to ~10 (approximate=True allows slight overage)
stats = cache.get_stats()
assert stats.entry_count <= 12  # Allow some approximation
assert stats.max_entries == 10
```

#### 4. Test Hit/Miss Tracking

```python
cache = SemanticCache()

# Initial stats
stats = cache.get_stats()
initial_hits = stats.hits
initial_misses = stats.misses

# Cache miss
cache.fetch("nonexistent_key")
stats = cache.get_stats()
assert stats.misses == initial_misses + 1

# Cache hit
cache.store(CacheRecord(key="exists", prompt="Q", response="A", confidence=0.9))
cache.fetch("exists")
stats = cache.get_stats()
assert stats.hits == initial_hits + 1

# Check hit rate calculation
hit_rate = stats.hit_rate
expected = stats.hits / (stats.hits + stats.misses)
assert abs(hit_rate - expected) < 0.01
```

#### 5. Test Manual Operations

```python
cache = SemanticCache()

# Add entries
for i in range(100):
    cache.store(CacheRecord(key=f"k{i}", prompt="Q", response="A", confidence=0.9))

# Manual trim to 50
trimmed = cache.trim(max_entries=50)
print(f"Trimmed {trimmed} entries")

stats = cache.get_stats()
assert stats.entry_count <= 55  # Approximate

# Clear all
deleted = cache.clear()
assert deleted >= 1  # At least the stream was deleted

stats = cache.get_stats()
assert stats.entry_count == 0
assert stats.hits == 0
assert stats.misses == 0
```

### Monitoring Cache Health

```python
from common.cache import SemanticCache

cache = SemanticCache()
stats = cache.get_stats()

print(f"""
Semantic Cache Statistics:
- Entries: {stats.entry_count:,} / {stats.max_entries:,}
- Size: ~{stats.size_bytes / 1024 / 1024:.2f} MB
- Hit Rate: {stats.hit_rate:.2%}
- Hits: {stats.hits:,}
- Misses: {stats.misses:,}
- TTL: {stats.ttl_seconds / 3600:.1f} hours
""")

# Alert if cache is full
if stats.entry_count >= stats.max_entries * 0.9:
    print("⚠️  Cache is 90% full - consider increasing SEMANTIC_CACHE_MAX_ENTRIES")

# Alert if hit rate is low
if stats.hit_rate < 0.1 and (stats.hits + stats.misses) > 100:
    print("⚠️  Cache hit rate below 10% - cache may not be effective")
```

### Troubleshooting

#### Cache Not Evicting Old Entries

Check Redis Streams directly:

```bash
# Connect to Redis
redis-cli

# Check stream length
XLEN kitty:semantic-cache

# Check stream TTL
TTL kitty:semantic-cache
# Should return seconds remaining (up to 43200 for 12 hours)

# Check if TTL is set
XINFO STREAM kitty:semantic-cache
```

If TTL is -1 (no expiration), the cache isn't setting TTL properly. Check:
1. Redis version supports `EXPIRE` on streams (Redis 5.0+)
2. Cache initialization isn't being overridden
3. Environment variables are being loaded

#### Cache Growing Beyond Max Entries

The `approximate=True` flag allows Redis to trim slightly above the limit for performance. This is expected behavior. Actual size should stay within ~2% of max_entries.

If cache grows significantly beyond limit:
1. Check Redis version supports `MAXLEN` (Redis 5.0+)
2. Verify `max_entries` parameter is being passed to `xadd()`
3. Call `cache.trim()` manually to force exact trimming

#### Hit Rate is 0% But Cache Has Entries

This happens if:
1. Keys are changing between store/fetch (check key generation logic)
2. Stats were recently cleared (use `cache.get_stats()` to verify)
3. Only storing, never fetching (expected - hit rate will rise as cache is used)

The hit/miss tracking is persistent in Redis hash `kitty:semantic-cache:stats`.

---

## References

- **Permission System Architecture**: `Research/PermissionSystemArchitecture.md`
- **Research Graph Wiring**: `Research/ResearchGraphWiring.md`
- **Implementation Plan**: `Research/AutonomousResearchImplementationPlan.md`
- **README**: `README.md` (Autonomous Research Pipeline section)
- **Test Files**: `tests/unit/`, `tests/integration/`

---

## Quick Reference: Test Commands

```bash
# Run all permission tests
pytest tests/unit/test_unified_permission_gate.py \
       tests/unit/test_research_tool_executor.py \
       tests/integration/test_research_permission_flow.py -v

# Run with coverage
pytest tests/ --cov=brain.research --cov-report=html

# Run specific test
pytest tests/unit/test_unified_permission_gate.py::TestUnifiedPermissionGate::test_check_io_control_enabled -v

# Run in parallel (faster)
pytest tests/ -n auto

# Run with verbose output
pytest tests/ -vv -s
```
