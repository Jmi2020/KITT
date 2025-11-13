# KITTY Autonomous System - Test Suite Manifest

**Purpose**: Comprehensive test documentation for batch execution on workstation deployment.

**Last Updated**: 2025-11-13
**Total Tests**: 40 unit tests + 3 integration tests
**Test Framework**: pytest
**Coverage Target**: >80% for autonomous system

---

## Test Execution Commands

### Run All Autonomous Tests
```bash
# From repo root
pytest tests/unit/test_autonomous_*.py -v

# With coverage
pytest tests/unit/test_autonomous_*.py --cov=services.brain.src.brain.autonomous --cov-report=html

# Fast parallel execution
pytest tests/unit/test_autonomous_*.py -v -n auto
```

### Run Specific Test Suites
```bash
# Scheduler tests only
pytest tests/unit/test_autonomous_scheduler.py -v

# Jobs tests only
pytest tests/unit/test_autonomous_jobs.py -v

# Goal generator tests only
pytest tests/unit/test_goal_generator.py -v

# Integration tests (when implemented)
pytest tests/integration/test_autonomous_integration.py -v -m integration
```

### Run Tests with Markers
```bash
# Skip slow tests
pytest tests/unit/test_autonomous_*.py -v -m "not slow"

# Only integration tests
pytest tests/ -v -m integration

# Only unit tests
pytest tests/ -v -m "not integration"
```

---

## Test File Inventory

### 1. test_autonomous_scheduler.py
**Location**: `tests/unit/test_autonomous_scheduler.py`
**Lines**: 250
**Test Count**: 10 tests
**Coverage**: `services.brain.src.brain.autonomous.scheduler`

**Test Classes**:
- `TestAutonomousScheduler` (8 tests)
  - `test_scheduler_initialization` - Verify initial state
  - `test_scheduler_start` - Start scheduler successfully
  - `test_scheduler_start_idempotent` - Handle duplicate start() calls
  - `test_scheduler_stop` - Stop gracefully
  - `test_add_interval_job` - Add periodic jobs
  - `test_add_cron_job` - Add cron-style jobs
  - `test_add_job_before_start_raises_error` - Error handling
  - `test_remove_job` - Remove scheduled jobs

- `TestSchedulerEventHandling` (2 tests)
  - `test_job_execution_event_logged` - Success logging
  - `test_job_error_event_logged` - Error logging

- `TestSchedulerLifecycle` (1 test)
  - `test_scheduler_integrates_with_lifespan` - FastAPI integration

**Dependencies**:
- `unittest.mock`: Mock, MagicMock, patch
- `apscheduler`: BackgroundScheduler

**Fixtures**: None (uses mocks)

**Expected Runtime**: ~5 seconds

---

### 2. test_autonomous_jobs.py
**Location**: `tests/unit/test_autonomous_jobs.py`
**Lines**: 300
**Test Count**: 15 tests
**Coverage**: `services.brain.src.brain.autonomous.jobs`

**Test Classes**:
- `TestDailyHealthCheck` (2 tests)
  - `test_health_check_success` - Normal execution
  - `test_health_check_handles_errors` - Error handling

- `TestWeeklyResearchCycle` (3 tests)
  - `test_research_cycle_runs_when_ready` - Execute when resources available
  - `test_research_cycle_skips_when_blocked` - Skip when budget exhausted
  - `test_research_cycle_handles_errors` - Graceful error handling

- `TestKnowledgeBaseUpdate` (3 tests)
  - `test_kb_update_runs_when_ready` - Execute when resources available
  - `test_kb_update_skips_when_blocked` - Skip when blocked
  - `test_kb_update_handles_errors` - Error handling

- `TestPrinterFleetHealthCheck` (2 tests)
  - `test_printer_fleet_check_placeholder` - Placeholder execution
  - `test_printer_fleet_check_handles_errors` - Error handling

- `TestJobScheduleIntegration` (2 tests)
  - `test_all_jobs_have_correct_signatures` - Verify async callables with no args
  - `test_jobs_use_resource_manager_correctly` - Resource checks

- `TestJobExecutionTiming` (1 test, marked `@pytest.mark.integration`)
  - `test_job_schedules_match_requirements` - Verify 4am-6am PST schedule

**Fixtures**:
- `mock_resource_status_ready` - ResourceStatus indicating system ready
- `mock_resource_status_blocked` - ResourceStatus indicating blocked

**Dependencies**:
- `unittest.mock`: Mock, MagicMock, patch, AsyncMock
- `decimal.Decimal`: Budget calculations
- `common.db.models`: Goal, GoalStatus, ResourceStatus

**Expected Runtime**: ~8 seconds

---

### 3. test_goal_generator.py
**Location**: `tests/unit/test_goal_generator.py`
**Lines**: 350
**Test Count**: 15 tests
**Coverage**: `services.brain.src.brain.autonomous.goal_generator`

**Test Classes**:
- `TestOpportunityScore` (4 tests)
  - `test_score_initialization` - Component initialization
  - `test_total_score_calculation` - Weighted scoring (max 100)
  - `test_partial_score_calculation` - Partial weights
  - `test_score_to_dict` - Dictionary export

- `TestGoalGenerator` (11 tests)
  - `test_generator_initialization` - Config defaults
  - `test_detect_knowledge_gaps` - Missing material detection
  - `test_detect_print_failures_insufficient_data` - Below threshold
  - `test_detect_print_failures_creates_goals` - Above threshold
  - `test_detect_cost_opportunities_low_usage` - <30% frontier
  - `test_detect_cost_opportunities_high_usage` - >30% frontier
  - `test_generate_goals_integration` - Full pipeline
  - `test_calculate_impact_score_print_failure` - Failure scoring
  - `test_calculate_impact_score_knowledge_gap` - Knowledge scoring
  - `test_persist_goals_success` - Database persistence
  - `test_persist_goals_handles_errors` - DB error handling

- `TestGoalGeneratorIntegration` (1 test, marked `@pytest.mark.integration`)
  - `test_end_to_end_goal_generation` - Requires test database (skipped)

**Fixtures**:
- `mock_session` - Database session mock
- `mock_session_factory` - Session factory context manager

**Dependencies**:
- `unittest.mock`: Mock, MagicMock, patch
- `uuid`: Goal ID generation
- `common.db.models`: Goal, GoalType, GoalStatus, FabricationJob, JobStatus

**Expected Runtime**: ~10 seconds

---

## Integration Tests (Sprint 3.4 - IMPLEMENTED)

### test_autonomous_workflow.py
**Location**: `tests/integration/test_autonomous_workflow.py`
**Lines**: 700+
**Test Count**: 3 integration tests
**Coverage**: End-to-end autonomous workflows

**Test Classes**:

#### 1. test_autonomous_workflow_end_to_end
**Purpose**: Verify complete autonomous research workflow from goal generation to KB article creation

**Workflow Tested**:
```
Goal Generation → Goal Approval → Project Generation →
Task 1: research_gather (Perplexity) →
Task 2: research_synthesize (Collective) →
Task 3: kb_create (KnowledgeUpdater) →
Task 4: review_commit (Git) →
Project Complete → Goal Complete
```

**Test Steps**:
1. Seed database with 3 PETG warping fabrication failures
2. Run GoalGenerator - verify fabrication_failure_analysis goal created
3. Approve goal (simulated manual step)
4. Run ProjectGenerator - verify 4 tasks created with correct dependencies
5. Execute task 1 (research_gather) with mock Perplexity API
6. Execute task 2 (research_synthesize) with mock collective meta-agent
7. Execute task 3 (kb_create) - verify KB article file created with YAML frontmatter
8. Execute task 4 (review_commit) with mock git operations
9. Verify all tasks marked as completed
10. Verify project marked as completed
11. Verify goal marked as completed

**Mocks & Fixtures**:
- `mock_perplexity`: Provides realistic PETG warping research response
- `mock_collective`: Provides structured KB article outline
- `mock_kb_updater`: Writes to tmp_path for testing
- `seed_fabrication_failures`: Creates 3 failed jobs with PETG warping

**Assertions**:
- Goal generated with correct type and description
- Project created with 4 tasks
- Task dependency chain: gather → synthesize → kb_create → commit
- Each task executes in correct order (dependency blocking works)
- KB article created with proper YAML frontmatter
- Project and goal marked as completed

**Runtime**: ~5-10 seconds

#### 2. test_task_dependency_blocking
**Purpose**: Verify task dependency tracking prevents out-of-order execution

**Scenario**:
- Create project with 3 tasks in dependency chain
- Task 1 has no dependencies
- Task 2 depends on Task 1
- Task 3 depends on Task 2

**Test Steps**:
1. Call `_find_ready_tasks()` - should return only Task 1
2. Mark Task 1 as completed
3. Call `_find_ready_tasks()` - should return only Task 2
4. Mark Task 2 as completed
5. Call `_find_ready_tasks()` - should return only Task 3

**Assertions**:
- Only tasks with no blocking dependencies are returned
- Dependency chain enforced correctly
- Task execution order guaranteed

**Runtime**: <1 second

#### 3. test_failed_task_blocks_dependents
**Purpose**: Verify failed tasks block dependent tasks from executing

**Scenario**:
- Create project with 2 tasks (Task 2 depends on Task 1)
- Mark Task 1 as failed
- Attempt to execute Task 2

**Test Steps**:
1. Create task dependency chain
2. Mark Task 1 as failed with error result
3. Call `_find_ready_tasks()` - should return empty list
4. Call `_update_project_status()` - project should be in_progress (not completed)
5. Verify goal still in approved status (not completed)

**Assertions**:
- Failed tasks block dependent tasks
- No tasks ready when dependency failed
- Project marked as in_progress (has failures)
- Project not marked as completed
- Goal not marked as completed

**Runtime**: <1 second

---

### Running Integration Tests

**Prerequisites**:
- PostgreSQL test database running
- llama.cpp servers running (Q4/F16) OR use mocks
- PERPLEXITY_API_KEY in .env OR use mocks

**Commands**:
```bash
# Run all integration tests
pytest tests/integration/test_autonomous_workflow.py -v -s

# Run with coverage
pytest tests/integration/test_autonomous_workflow.py --cov=services.brain.src.brain.autonomous --cov-report=html -v

# Run only integration tests (skip unit tests)
pytest tests/ -v -m integration

# Run with verbose output
pytest tests/integration/test_autonomous_workflow.py -v -s -vv
```

**Expected Output**:
```
tests/integration/test_autonomous_workflow.py::test_autonomous_workflow_end_to_end PASSED
✅ End-to-end autonomous workflow test passed!
✅ Goal: Research PETG warping prevention techniques...
✅ Project: Research PETG warping mitigation
✅ Tasks completed: 4
✅ KB article created: 2025-W46-petg-warping-prevention.md

tests/integration/test_autonomous_workflow.py::test_task_dependency_blocking PASSED
✅ Task dependency blocking test passed!

tests/integration/test_autonomous_workflow.py::test_failed_task_blocks_dependents PASSED
✅ Failed task blocking test passed!
```

**Execution Time**: ~10-15 seconds total

---

## Test Data Fixtures

### Sample Goal (for integration tests)
```python
{
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "goal_type": "improvement",
    "description": "Reduce first_layer failures in 3D printing",
    "rationale": "Observed 8 failures due to 'first_layer' in the past 30 days...",
    "estimated_budget": 2.50,
    "estimated_duration_hours": 4,
    "status": "identified",
    "goal_metadata": {
        "source": "print_failure_analysis",
        "failure_reason": "first_layer",
        "failure_count": 8,
        "lookback_days": 30
    }
}
```

### Sample Fabrication Failures (for seeding)
```python
fabrication_failures = [
    {
        "id": str(uuid.uuid4()),
        "status": "failed",
        "job_metadata": {"failure_reason": "first_layer"},
        "created_at": datetime.utcnow() - timedelta(days=i)
    }
    for i in range(8)
]
```

### Sample Resource Status (for mocks)
```python
ready_status = ResourceStatus(
    budget_available=Decimal("4.50"),
    budget_used_today=Decimal("0.50"),
    is_idle=True,
    cpu_usage_percent=15.0,
    memory_usage_percent=45.0,
    gpu_available=True,
    can_run_autonomous=True,
    reason="Ready: $4.50 available, idle, CPU 15.0%, RAM 45.0%",
    workload=AutonomousWorkload.scheduled,
)
```

---

## Test Execution Matrix

### Pre-Deployment Testing (Local)

| Suite | Command | Expected Runtime | Required Services |
|-------|---------|------------------|-------------------|
| Unit - Scheduler | `pytest tests/unit/test_autonomous_scheduler.py -v` | 5s | None |
| Unit - Jobs | `pytest tests/unit/test_autonomous_jobs.py -v` | 8s | None |
| Unit - Goal Generator | `pytest tests/unit/test_goal_generator.py -v` | 10s | None |
| All Unit Tests | `pytest tests/unit/test_autonomous_*.py -v` | 23s | None |

### Post-Deployment Testing (Workstation)

| Suite | Command | Expected Runtime | Required Services |
|-------|---------|------------------|-------------------|
| All Unit Tests | `pytest tests/unit/test_autonomous_*.py -v` | 23s | None |
| Integration Tests | `pytest tests/integration/ -v -m integration` | 60s | PostgreSQL, Brain |
| Full Test Suite | `pytest tests/ -v` | 90s | All services |
| With Coverage | `pytest tests/ --cov=services.brain --cov-report=html` | 120s | All services |

---

## Continuous Integration Pipeline (Future)

### GitHub Actions Workflow (Planned)
```yaml
name: Autonomous System Tests

on: [push, pull_request]

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python 3.11
        uses: actions/setup-python@v4
        with:
          python-version: 3.11
      - name: Install dependencies
        run: |
          pip install -r requirements-test.txt
          pip install -e services/brain
          pip install -e services/common
      - name: Run unit tests
        run: pytest tests/unit/test_autonomous_*.py -v --junitxml=junit.xml
      - name: Upload results
        uses: actions/upload-artifact@v3
        with:
          name: test-results
          path: junit.xml

  integration-tests:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_PASSWORD: test
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    steps:
      - uses: actions/checkout@v3
      - name: Run integration tests
        run: pytest tests/integration/ -v -m integration
```

---

## Test Debugging Guide

### Common Test Failures

**1. ImportError: No module named 'services'**
```bash
# Solution: Install packages in editable mode
pip install -e services/brain
pip install -e services/common
```

**2. Database connection errors (integration tests)**
```bash
# Solution: Start test database
docker run -d -p 5433:5432 -e POSTGRES_PASSWORD=test postgres:15

# Set test database URL
export DATABASE_URL=postgresql://postgres:test@localhost:5433/test_kitty
```

**3. Async test warnings**
```bash
# Solution: Install pytest-asyncio
pip install pytest-asyncio

# Add to pytest.ini or pyproject.toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

**4. Mock patching issues**
```bash
# Common issue: Incorrect patch path
# ❌ @patch('goal_generator.KnowledgeUpdater')
# ✅ @patch('services.brain.src.brain.autonomous.goal_generator.KnowledgeUpdater')
```

### Running Tests in Debug Mode
```bash
# Verbose output with print statements
pytest tests/unit/test_autonomous_*.py -v -s

# Stop on first failure
pytest tests/unit/test_autonomous_*.py -v -x

# Drop into debugger on failure
pytest tests/unit/test_autonomous_*.py -v --pdb

# Run specific test
pytest tests/unit/test_goal_generator.py::TestGoalGenerator::test_generate_goals_integration -v
```

---

## Test Coverage Goals

### Current Coverage (Estimated)
- `autonomous/scheduler.py`: ~90% (10/10 tests)
- `autonomous/jobs.py`: ~85% (15/15 tests)
- `autonomous/goal_generator.py`: ~80% (15/15 tests)
- `routes/autonomy.py`: 0% (no API tests yet)

### Target Coverage
- All modules: >80%
- Critical paths (goal generation, approval): >95%
- Error handling: >90%

### Coverage Commands
```bash
# Generate HTML coverage report
pytest tests/unit/test_autonomous_*.py --cov=services.brain.src.brain.autonomous --cov-report=html

# Open report
open htmlcov/index.html

# Show missing lines
pytest tests/unit/test_autonomous_*.py --cov=services.brain.src.brain.autonomous --cov-report=term-missing
```

---

## Test Maintenance Checklist

### When Adding New Autonomous Features
- [ ] Write unit tests first (TDD)
- [ ] Add integration tests for end-to-end flows
- [ ] Update this test manifest
- [ ] Update coverage goals
- [ ] Add new fixtures if needed
- [ ] Document expected runtime

### Before Deploying to Workstation
- [ ] Run all unit tests locally: `pytest tests/unit/test_autonomous_*.py -v`
- [ ] Verify no test failures
- [ ] Check coverage: `pytest --cov-report=term-missing`
- [ ] Update test documentation if new tests added
- [ ] Commit test results/reports

### After Deploying to Workstation
- [ ] Run full test suite: `pytest tests/ -v`
- [ ] Run integration tests: `pytest tests/integration/ -v -m integration`
- [ ] Verify all services running for integration tests
- [ ] Document any workstation-specific test issues
- [ ] Set up cron for nightly test runs (optional)

---

## Quick Reference

### Run All Tests (Batch Execution)
```bash
# From repo root on workstation
cd /path/to/KITT

# Install test dependencies
pip install -r requirements-test.txt
pip install -e services/brain
pip install -e services/common
pip install -e services/cli

# Run all autonomous unit tests
pytest tests/unit/test_autonomous_*.py -v --tb=short

# Run with coverage
pytest tests/unit/test_autonomous_*.py --cov=services.brain.src.brain.autonomous --cov-report=html --cov-report=term

# Run integration tests (requires services running)
docker compose up -d
pytest tests/integration/ -v -m integration

# Generate report
pytest tests/ -v --junitxml=test-results.xml --html=test-report.html
```

### Expected Output (Success)
```
tests/unit/test_autonomous_scheduler.py::TestAutonomousScheduler::test_scheduler_initialization PASSED
tests/unit/test_autonomous_scheduler.py::TestAutonomousScheduler::test_scheduler_start PASSED
...
tests/unit/test_goal_generator.py::TestGoalGenerator::test_persist_goals_success PASSED

==================== 40 passed in 23.45s ====================

Coverage:
services/brain/src/brain/autonomous/scheduler.py       90%
services/brain/src/brain/autonomous/jobs.py            85%
services/brain/src/brain/autonomous/goal_generator.py  80%
```

---

## Contact & Support

**Test Issues**: Check `tests/README.md` for troubleshooting
**Integration Test Setup**: See `tests/integration/README.md` (to be created)
**Coverage Reports**: Available in `htmlcov/` after running coverage command

**Last Updated**: 2025-11-12
**Maintained By**: Autonomous System Development Team
