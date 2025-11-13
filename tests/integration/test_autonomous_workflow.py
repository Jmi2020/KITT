"""Integration tests for autonomous research workflow.

Tests the complete autonomous cycle:
1. Goal generation from fabrication failures
2. Goal approval (manual step)
3. Project generation from approved goals
4. Task execution with dependency tracking
5. Research workflow (gather → synthesize → create → commit)
6. Project and goal completion

These tests require:
- PostgreSQL database
- PERPLEXITY_API_KEY (or mock)
- llama.cpp servers running (Q4/F16) for collective
"""

import pytest
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock

from sqlalchemy.orm import Session

from common.db.models import (
    Goal,
    GoalType,
    GoalStatus,
    Project,
    ProjectStatus,
    Task,
    TaskStatus,
    FabricationJob,
)
from common.db import SessionLocal

from brain.autonomous.goal_generator import GoalGenerator, OpportunityScore
from brain.autonomous.project_generator import ProjectGenerator
from brain.autonomous.task_executor import TaskExecutor


@pytest.fixture
def db_session():
    """Provide a database session for tests."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def seed_fabrication_failures(db_session: Session):
    """Seed database with fabrication failures for goal generation."""
    failures = []

    # Create 3 fabrication failures with PETG warping
    for i in range(3):
        job = FabricationJob(
            id=str(uuid.uuid4()),
            cad_artifact_id=f"artifact_{i}",
            device_id="printer_01",
            status="failed",
            failure_reason="PETG warping during print, bed adhesion issues",
            created_at=datetime.utcnow() - timedelta(days=i),
            started_at=datetime.utcnow() - timedelta(days=i),
            completed_at=datetime.utcnow() - timedelta(days=i),
        )
        db_session.add(job)
        failures.append(job)

    db_session.commit()
    return failures


@pytest.fixture
def mock_perplexity():
    """Mock Perplexity API responses."""
    mock_response = {
        "output": """PETG (Polyethylene Terephthalate Glycol) warping is commonly caused by:

1. Insufficient bed adhesion - use glue stick or PEI sheet
2. Incorrect bed temperature - should be 70-80°C for PETG
3. Poor first layer calibration
4. Cooling fan too high - PETG needs minimal cooling
5. Enclosure temperature fluctuations

Recommended solutions:
- Clean bed with IPA before printing
- Use brim or raft for better adhesion
- Reduce cooling to 20-30% after first layer
- Consider enclosure for ambient temperature control
- Adjust Z-offset for proper squish on first layer

Sources: Prusa Knowledge Base, Simplify3D troubleshooting guide""",
        "raw": {
            "citations": [
                "https://help.prusa3d.com/article/petg_2059",
                "https://www.simplify3d.com/support/materials-guide/petg/",
            ]
        }
    }

    async def mock_query(payload):
        return mock_response

    mock_client = Mock()
    mock_client.query = AsyncMock(side_effect=mock_query)
    return mock_client


@pytest.fixture
def mock_collective():
    """Mock collective meta-agent responses."""
    mock_verdict = """# PETG Warping Prevention Guide

## Executive Summary
PETG warping is primarily caused by poor bed adhesion and thermal management. This guide provides proven techniques to eliminate warping issues.

## Key Sections

### 1. Bed Preparation
- Clean with isopropyl alcohol before each print
- Apply thin layer of glue stick or use PEI sheet
- Verify bed level and Z-offset calibration

### 2. Temperature Management
- Bed temperature: 70-80°C (optimal: 75°C)
- Nozzle temperature: 230-250°C
- Ambient temperature: enclosed preferred

### 3. Print Settings
- First layer: 100% cooling off
- Subsequent layers: 20-30% cooling
- Use brim (5-10mm) or raft for large parts
- Print speed: <50mm/s for first layer

### 4. Material Handling
- Store PETG in dry box (moisture causes issues)
- Use fresh filament (<6 months old)
- Dry filament at 65°C for 4-6 hours if moisture suspected

## Key Insights
1. PETG requires minimal cooling compared to PLA
2. Bed adhesion is critical - invest in quality build surface
3. Enclosures significantly reduce warping for large prints

## Recommended Tags
- materials
- petg
- troubleshooting
- bed-adhesion
- warping
"""

    async def mock_ainvoke(state):
        return {
            "verdict": mock_verdict,
            "logs": "[plan]\nPlan complete\n[propose_council]\nProposals generated\n[judge]\nVerdict ready"
        }

    mock_graph = Mock()
    mock_graph.ainvoke = AsyncMock(side_effect=mock_ainvoke)
    return mock_graph


@pytest.mark.integration
@pytest.mark.asyncio
async def test_autonomous_workflow_end_to_end(
    db_session: Session,
    seed_fabrication_failures,
    mock_perplexity,
    mock_collective,
    tmp_path: Path,
):
    """Test complete autonomous workflow from goal generation to KB article creation.

    Workflow:
    1. Goal generator detects fabrication failures
    2. Generate goal with opportunity score
    3. Approve goal (manual step, simulated here)
    4. Project generator creates project + 4 tasks
    5. Task executor runs tasks in dependency order
    6. Verify KB article created and committed
    7. Verify project and goal marked as completed
    """
    # Setup
    created_by = "test-autonomous"

    # Step 1: Goal Generation
    goal_generator = GoalGenerator(session_factory=lambda: db_session, created_by=created_by)

    goals = goal_generator.generate_goals()

    assert len(goals) > 0, "Should generate at least one goal from fabrication failures"

    # Find fabrication failure goal
    failure_goal = None
    for goal in goals:
        if goal.goal_type == GoalType.fabrication_failure_analysis:
            failure_goal = goal
            break

    assert failure_goal is not None, "Should generate fabrication failure analysis goal"
    assert failure_goal.status == GoalStatus.pending, "New goal should be pending approval"
    assert "PETG" in failure_goal.description or "warping" in failure_goal.description

    # Step 2: Approve Goal (manual step, simulated)
    failure_goal.status = GoalStatus.approved
    db_session.commit()

    # Step 3: Project Generation
    project_generator = ProjectGenerator(session_factory=lambda: db_session, created_by=created_by)

    projects = project_generator.generate_projects()

    assert len(projects) > 0, "Should generate project from approved goal"

    project = projects[0]
    assert project.goal_id == failure_goal.id
    assert project.status == ProjectStatus.proposed
    assert len(project.tasks) == 4, "Research goals should generate 4 tasks"

    # Verify task types and dependencies
    task_types = [t.task_metadata.get("task_type") for t in project.tasks]
    assert "research_gather" in task_types
    assert "research_synthesize" in task_types
    assert "kb_create" in task_types
    assert "review_commit" in task_types

    # Verify dependency chain
    gather_task = next(t for t in project.tasks if t.task_metadata.get("task_type") == "research_gather")
    synthesize_task = next(t for t in project.tasks if t.task_metadata.get("task_type") == "research_synthesize")
    kb_task = next(t for t in project.tasks if t.task_metadata.get("task_type") == "kb_create")
    commit_task = next(t for t in project.tasks if t.task_metadata.get("task_type") == "review_commit")

    assert gather_task.depends_on is None, "gather should have no dependencies"
    assert synthesize_task.depends_on == gather_task.id, "synthesize should depend on gather"
    assert kb_task.depends_on == synthesize_task.id, "kb_create should depend on synthesize"
    assert commit_task.depends_on == kb_task.id, "commit should depend on kb_create"

    # Step 4: Task Execution with Mocks
    # Create mock KnowledgeUpdater that writes to tmp_path
    mock_kb_updater = Mock()
    mock_kb_path = tmp_path / "knowledge" / "research"
    mock_kb_path.mkdir(parents=True)

    def mock_create_research_article(topic, content, **kwargs):
        # Generate filename like real KnowledgeUpdater
        now = datetime.utcnow()
        week_num = now.isocalendar()[1]
        slug = topic.lower().replace(" ", "-")
        filename = f"{now.year}-W{week_num:02d}-{slug}.md"
        file_path = mock_kb_path / filename

        # Write YAML frontmatter + content
        with open(file_path, "w") as f:
            f.write("---\n")
            f.write(f"generated_date: {now.isoformat()}Z\n")
            f.write(f"topic: {topic}\n")
            f.write(f"goal_id: {kwargs.get('goal_id')}\n")
            f.write(f"project_id: {kwargs.get('project_id')}\n")
            f.write("---\n\n")
            f.write(content)

        return file_path

    mock_kb_updater.create_research_article = Mock(side_effect=mock_create_research_article)
    mock_kb_updater.techniques_path = tmp_path / "knowledge" / "techniques"
    mock_kb_updater.techniques_path.mkdir(parents=True)

    # Patch build_collective_graph_async to return mock graph
    with patch("brain.autonomous.task_executor.build_collective_graph_async", return_value=mock_collective):
        task_executor = TaskExecutor(
            session_factory=lambda: db_session,
            mcp_client=mock_perplexity,
            kb_updater=mock_kb_updater,
        )

        # Execute tasks (should run in dependency order)
        # Iteration 1: gather (no dependencies)
        executed = task_executor.execute_ready_tasks(limit=5)
        assert len(executed) == 1, "Should execute gather task first"
        assert executed[0].task_metadata.get("task_type") == "research_gather"
        assert executed[0].status == TaskStatus.completed
        assert "results" in executed[0].result

        db_session.refresh(gather_task)
        assert gather_task.status == TaskStatus.completed

        # Iteration 2: synthesize (depends on gather)
        executed = task_executor.execute_ready_tasks(limit=5)
        assert len(executed) == 1, "Should execute synthesize task"
        assert executed[0].task_metadata.get("task_type") == "research_synthesize"
        assert executed[0].status == TaskStatus.completed
        assert "synthesis" in executed[0].result

        db_session.refresh(synthesize_task)
        assert synthesize_task.status == TaskStatus.completed

        # Iteration 3: kb_create (depends on synthesize)
        executed = task_executor.execute_ready_tasks(limit=5)
        assert len(executed) == 1, "Should execute kb_create task"
        assert executed[0].task_metadata.get("task_type") == "kb_create"
        assert executed[0].status == TaskStatus.completed
        assert "file_path" in executed[0].result

        db_session.refresh(kb_task)
        assert kb_task.status == TaskStatus.completed

        # Verify KB article was created
        kb_file_path = Path(kb_task.result["file_path"])
        assert kb_file_path.exists(), "KB article should be created"

        with open(kb_file_path, "r") as f:
            content = f.read()
            assert content.startswith("---"), "Should have YAML frontmatter"
            assert "PETG" in content or "warping" in content

        # Iteration 4: review_commit (depends on kb_create)
        # Mock git operations since we're in tmp_path
        with patch("subprocess.run") as mock_subprocess:
            # Mock successful git operations
            mock_subprocess.return_value = Mock(
                returncode=0,
                stdout=b"abc123def456\n",  # commit SHA
                stderr=b"",
            )

            executed = task_executor.execute_ready_tasks(limit=5)
            assert len(executed) == 1, "Should execute review_commit task"
            assert executed[0].task_metadata.get("task_type") == "review_commit"
            assert executed[0].status == TaskStatus.completed
            assert "commit_sha" in executed[0].result

            db_session.refresh(commit_task)
            assert commit_task.status == TaskStatus.completed

    # Step 5: Verify Project and Goal Completion
    db_session.refresh(project)
    db_session.refresh(failure_goal)

    # All tasks should be completed
    all_completed = all(t.status == TaskStatus.completed for t in project.tasks)
    assert all_completed, "All tasks should be completed"

    # Project should be marked as completed
    assert project.status == ProjectStatus.completed, "Project should be completed"
    assert project.completed_at is not None

    # Goal should be marked as completed
    assert failure_goal.status == GoalStatus.completed, "Goal should be completed"

    print("✅ End-to-end autonomous workflow test passed!")
    print(f"✅ Goal: {failure_goal.description[:60]}...")
    print(f"✅ Project: {project.title}")
    print(f"✅ Tasks completed: {len(project.tasks)}")
    print(f"✅ KB article created: {kb_file_path.name}")


@pytest.mark.integration
def test_task_dependency_blocking(db_session: Session):
    """Test that tasks with unmet dependencies are not executed."""
    # Create a project with 3 tasks in dependency chain
    project_id = str(uuid.uuid4())
    goal_id = str(uuid.uuid4())

    # Create goal
    goal = Goal(
        id=goal_id,
        goal_type=GoalType.research,
        description="Test dependency blocking",
        status=GoalStatus.approved,
        opportunity_score=OpportunityScore(
            impact_score=50,
            effort_estimate_hours=2.0,
            confidence=0.8,
            priority=60.0,
        ).to_dict(),
        created_by="test",
    )
    db_session.add(goal)

    # Create project
    project = Project(
        id=project_id,
        goal_id=goal_id,
        title="Test Project",
        description="Test dependency tracking",
        status=ProjectStatus.proposed,
        budget_allocated=Decimal("10.00"),
        budget_spent=Decimal("0.00"),
        created_by="test",
    )
    db_session.add(project)

    # Create tasks with dependencies
    task1 = Task(
        id=str(uuid.uuid4()),
        project_id=project_id,
        title="Task 1",
        description="First task",
        status=TaskStatus.pending,
        task_metadata={"task_type": "research_gather"},
        depends_on=None,  # No dependencies
        priority=1,
    )

    task2 = Task(
        id=str(uuid.uuid4()),
        project_id=project_id,
        title="Task 2",
        description="Second task",
        status=TaskStatus.pending,
        task_metadata={"task_type": "research_synthesize"},
        depends_on=task1.id,  # Depends on task1
        priority=2,
    )

    task3 = Task(
        id=str(uuid.uuid4()),
        project_id=project_id,
        title="Task 3",
        description="Third task",
        status=TaskStatus.pending,
        task_metadata={"task_type": "kb_create"},
        depends_on=task2.id,  # Depends on task2
        priority=3,
    )

    db_session.add_all([task1, task2, task3])
    db_session.commit()

    # Create mock executor
    mock_mcp = Mock()
    mock_mcp.query = AsyncMock(return_value={"output": "test", "raw": {}})

    task_executor = TaskExecutor(
        session_factory=lambda: db_session,
        mcp_client=mock_mcp,
    )

    # Find ready tasks - should only return task1
    ready_tasks = task_executor._find_ready_tasks(db_session, limit=10)

    assert len(ready_tasks) == 1, "Only task1 should be ready (no dependencies)"
    assert ready_tasks[0].id == task1.id

    # Mark task1 as completed
    task1.status = TaskStatus.completed
    task1.completed_at = datetime.utcnow()
    task1.result = {"test": "result"}
    db_session.commit()

    # Find ready tasks again - should only return task2 now
    ready_tasks = task_executor._find_ready_tasks(db_session, limit=10)

    assert len(ready_tasks) == 1, "Only task2 should be ready now"
    assert ready_tasks[0].id == task2.id

    # Mark task2 as completed
    task2.status = TaskStatus.completed
    task2.completed_at = datetime.utcnow()
    task2.result = {"test": "result"}
    db_session.commit()

    # Find ready tasks again - should only return task3 now
    ready_tasks = task_executor._find_ready_tasks(db_session, limit=10)

    assert len(ready_tasks) == 1, "Only task3 should be ready now"
    assert ready_tasks[0].id == task3.id

    print("✅ Task dependency blocking test passed!")


@pytest.mark.integration
def test_failed_task_blocks_dependents(db_session: Session):
    """Test that failed tasks block dependent tasks from executing."""
    # Create project with 2 tasks in dependency chain
    project_id = str(uuid.uuid4())
    goal_id = str(uuid.uuid4())

    goal = Goal(
        id=goal_id,
        goal_type=GoalType.research,
        description="Test failure blocking",
        status=GoalStatus.approved,
        opportunity_score=OpportunityScore(
            impact_score=50,
            effort_estimate_hours=2.0,
            confidence=0.8,
            priority=60.0,
        ).to_dict(),
        created_by="test",
    )
    db_session.add(goal)

    project = Project(
        id=project_id,
        goal_id=goal_id,
        title="Test Project",
        description="Test failure handling",
        status=ProjectStatus.proposed,
        budget_allocated=Decimal("10.00"),
        budget_spent=Decimal("0.00"),
        created_by="test",
    )
    db_session.add(project)

    task1 = Task(
        id=str(uuid.uuid4()),
        project_id=project_id,
        title="Task 1 (will fail)",
        description="First task",
        status=TaskStatus.pending,
        task_metadata={"task_type": "research_gather"},
        depends_on=None,
        priority=1,
    )

    task2 = Task(
        id=str(uuid.uuid4()),
        project_id=project_id,
        title="Task 2 (blocked)",
        description="Second task",
        status=TaskStatus.pending,
        task_metadata={"task_type": "research_synthesize"},
        depends_on=task1.id,
        priority=2,
    )

    db_session.add_all([task1, task2])
    db_session.commit()

    # Mark task1 as failed
    task1.status = TaskStatus.failed
    task1.started_at = datetime.utcnow()
    task1.result = {"error": "API call failed"}
    db_session.commit()

    # Create executor
    mock_mcp = Mock()
    task_executor = TaskExecutor(
        session_factory=lambda: db_session,
        mcp_client=mock_mcp,
    )

    # Find ready tasks - should return nothing (task1 failed, task2 blocked)
    ready_tasks = task_executor._find_ready_tasks(db_session, limit=10)

    assert len(ready_tasks) == 0, "No tasks should be ready (task1 failed, task2 blocked)"

    # Verify project status is updated to in_progress (has failures)
    task_executor._update_project_status(db_session)

    db_session.refresh(project)
    assert project.status == ProjectStatus.in_progress, "Project should be in_progress with failed tasks"
    assert project.completed_at is None, "Project should not be completed"

    db_session.refresh(goal)
    assert goal.status == GoalStatus.approved, "Goal should still be approved (not completed)"

    print("✅ Failed task blocking test passed!")


if __name__ == "__main__":
    # Run with: pytest tests/integration/test_autonomous_workflow.py -v -s
    pytest.main([__file__, "-v", "-s"])
