"""Project generator for converting approved goals into actionable projects.

Monitors approved goals and creates Projects with task breakdowns for autonomous execution.
"""

import logging
import uuid
from datetime import datetime
from decimal import Decimal
from typing import List, Optional, Dict, Any

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from common.db.models import (
    Goal,
    GoalStatus,
    GoalType,
    Project,
    ProjectStatus,
    Task,
    TaskStatus,
    TaskPriority,
)
from common.db import SessionLocal

logger = logging.getLogger(__name__)
struct_logger = structlog.get_logger()


class ProjectGenerator:
    """Generates projects and tasks from approved goals.

    Responsibilities:
    - Monitor for newly approved goals
    - Create Project records with appropriate scope
    - Break down projects into actionable Tasks
    - Set task dependencies and priorities
    - Allocate budget to projects
    """

    def __init__(
        self,
        session_factory=SessionLocal,
        *,
        created_by: str = "system-autonomous",
    ):
        """Initialize project generator.

        Args:
            session_factory: SQLAlchemy session factory
            created_by: User ID for autonomous project creation
        """
        self._session_factory = session_factory
        self.created_by = created_by

    def generate_projects_from_approved_goals(
        self, limit: int = 10
    ) -> List[Project]:
        """Generate projects from approved goals that don't have projects yet.

        Args:
            limit: Maximum number of projects to generate in one cycle

        Returns:
            List of newly created Project objects
        """
        struct_logger.info("project_generation_started", limit=limit)

        with self._session_factory() as session:
            # Find approved goals without projects
            stmt = (
                select(Goal)
                .where(Goal.status == GoalStatus.approved)
                .outerjoin(Project, Goal.id == Project.goal_id)
                .where(Project.id == None)  # noqa: E711
                .order_by(Goal.approved_at.desc())
                .limit(limit)
            )

            approved_goals = session.execute(stmt).scalars().all()

            if not approved_goals:
                logger.info("No approved goals pending project generation")
                struct_logger.info("project_generation_no_goals")
                return []

            logger.info(f"Found {len(approved_goals)} approved goals to convert to projects")

            projects = []
            for goal in approved_goals:
                try:
                    project = self._create_project_from_goal(goal, session)
                    projects.append(project)

                    logger.info(
                        f"✅ Created project: {project.title} (ID: {project.id[:16]}...)"
                    )

                    struct_logger.info(
                        "project_created",
                        project_id=project.id,
                        goal_id=goal.id,
                        project_title=project.title,
                        task_count=len(project.tasks),
                    )
                except Exception as exc:
                    logger.error(
                        f"Failed to create project for goal {goal.id}: {exc}",
                        exc_info=True
                    )
                    struct_logger.error(
                        "project_creation_failed",
                        goal_id=goal.id,
                        error=str(exc)
                    )
                    continue

            session.commit()

            struct_logger.info(
                "project_generation_completed",
                projects_created=len(projects),
                project_ids=[p.id for p in projects],
            )

            return projects

    def _create_project_from_goal(self, goal: Goal, session: Session) -> Project:
        """Create a project and tasks from a goal.

        Args:
            goal: Approved Goal object
            session: Database session

        Returns:
            Created Project object with tasks
        """
        # Generate project title and description based on goal type
        title, description = self._generate_project_scope(goal)

        # Create project
        project = Project(
            id=str(uuid.uuid4()),
            goal_id=goal.id,
            title=title,
            description=description,
            status=ProjectStatus.proposed,
            budget_allocated=goal.estimated_budget,
            budget_spent=Decimal("0.00"),
            created_by=self.created_by,
            created_at=datetime.utcnow(),
            project_metadata={
                "goal_type": goal.goal_type.value,
                "estimated_duration_hours": goal.estimated_duration_hours,
                "auto_generated": True,
            },
        )

        session.add(project)
        session.flush()  # Get project ID

        # Generate tasks for the project
        tasks = self._generate_tasks_for_project(project, goal, session)

        # Update project metadata with task count
        project.project_metadata["task_count"] = len(tasks)

        return project

    def _generate_project_scope(self, goal: Goal) -> tuple[str, str]:
        """Generate project title and description from goal.

        Args:
            goal: Goal object

        Returns:
            Tuple of (title, description)
        """
        goal_type = goal.goal_type

        # Title is a concise version of the goal description
        title = goal.description[:150]  # Truncate if too long

        # Description includes goal rationale and implementation approach
        if goal_type == GoalType.research:
            description = f"""**Research Project: {goal.description}**

**Rationale**: {goal.rationale}

**Research Approach**:
1. Gather information from web sources and documentation
2. Synthesize findings into comprehensive guide
3. Create knowledge base article with YAML frontmatter
4. Review and refine content for accuracy

**Deliverables**:
- Knowledge base article in `knowledge/` directory
- Git commit with autonomous tag
- Structured data for future reference

**Budget**: ${float(goal.estimated_budget):.2f}
**Estimated Duration**: {goal.estimated_duration_hours}h
"""

        elif goal_type == GoalType.improvement:
            description = f"""**Improvement Project: {goal.description}**

**Rationale**: {goal.rationale}

**Improvement Approach**:
1. Research best practices and troubleshooting techniques
2. Document recommended solutions
3. Update technique guides in knowledge base
4. Track effectiveness in future fabrication jobs

**Deliverables**:
- Updated technique guide in `knowledge/techniques/`
- Git commit with improvement tag
- Metrics for tracking success rate

**Budget**: ${float(goal.estimated_budget):.2f}
**Estimated Duration**: {goal.estimated_duration_hours}h
"""

        elif goal_type == GoalType.optimization:
            description = f"""**Optimization Project: {goal.description}**

**Rationale**: {goal.rationale}

**Optimization Approach**:
1. Analyze current performance metrics
2. Identify optimization opportunities
3. Document recommended changes
4. Validate improvements through testing

**Deliverables**:
- Optimization report with recommendations
- Updated configuration or prompts
- Performance comparison metrics

**Budget**: ${float(goal.estimated_budget):.2f}
**Estimated Duration**: {goal.estimated_duration_hours}h
"""

        elif goal_type == GoalType.fabrication:
            description = f"""**Fabrication Project: {goal.description}**

**Rationale**: {goal.rationale}

**Fabrication Approach**:
1. Generate CAD design (parametric or mesh)
2. Analyze printability and optimize
3. Select appropriate printer and settings
4. Monitor print execution
5. Document results and lessons learned

**Deliverables**:
- CAD artifact (STEP/STL)
- Print job record with photos
- Fabrication report with metrics

**Budget**: ${float(goal.estimated_budget):.2f}
**Estimated Duration**: {goal.estimated_duration_hours}h
"""

        else:
            description = f"{goal.rationale}\n\nBudget: ${float(goal.estimated_budget):.2f}"

        return title, description

    def _generate_tasks_for_project(
        self, project: Project, goal: Goal, session: Session
    ) -> List[Task]:
        """Generate task breakdown for a project.

        Args:
            project: Project object
            goal: Goal object
            session: Database session

        Returns:
            List of created Task objects
        """
        tasks = []
        goal_type = goal.goal_type

        if goal_type == GoalType.research:
            tasks = self._generate_research_tasks(project, goal, session)
        elif goal_type == GoalType.improvement:
            tasks = self._generate_improvement_tasks(project, goal, session)
        elif goal_type == GoalType.optimization:
            tasks = self._generate_optimization_tasks(project, goal, session)
        elif goal_type == GoalType.fabrication:
            tasks = self._generate_fabrication_tasks(project, goal, session)

        return tasks

    def _generate_research_tasks(
        self, project: Project, goal: Goal, session: Session
    ) -> List[Task]:
        """Generate tasks for research projects.

        Research workflow: Gather → Synthesize → Document → Review
        """
        tasks = []

        # Task 1: Gather information
        task1 = Task(
            id=str(uuid.uuid4()),
            project_id=project.id,
            title="Gather information from web sources",
            description=f"Research {goal.description} using Perplexity API. Gather documentation, best practices, specifications, and expert recommendations.",
            status=TaskStatus.pending,
            priority=TaskPriority.high,
            task_metadata={
                "task_type": "research_gather",
                "search_queries": self._generate_search_queries(goal),
                "max_cost_usd": float(goal.estimated_budget) * 0.4,  # 40% of budget
            },
        )
        tasks.append(task1)
        session.add(task1)

        # Task 2: Synthesize findings (depends on task 1)
        session.flush()  # Get task1 ID
        task2 = Task(
            id=str(uuid.uuid4()),
            project_id=project.id,
            title="Synthesize research findings",
            description="Analyze gathered information and create structured outline for knowledge base article.",
            status=TaskStatus.pending,
            priority=TaskPriority.high,
            depends_on=task1.id,
            task_metadata={
                "task_type": "research_synthesize",
            },
        )
        tasks.append(task2)
        session.add(task2)

        # Task 3: Create KB article (depends on task 2)
        session.flush()
        task3 = Task(
            id=str(uuid.uuid4()),
            project_id=project.id,
            title="Create knowledge base article",
            description="Write comprehensive knowledge base article with YAML frontmatter and markdown content.",
            status=TaskStatus.pending,
            priority=TaskPriority.medium,
            depends_on=task2.id,
            task_metadata={
                "task_type": "kb_create",
                "kb_category": self._determine_kb_category(goal),
            },
        )
        tasks.append(task3)
        session.add(task3)

        # Task 4: Review and commit (depends on task 3)
        session.flush()
        task4 = Task(
            id=str(uuid.uuid4()),
            project_id=project.id,
            title="Review and commit to repository",
            description="Validate article formatting, commit to git with autonomous tag, update project completion status.",
            status=TaskStatus.pending,
            priority=TaskPriority.low,
            depends_on=task3.id,
            task_metadata={
                "task_type": "review_commit",
                "auto_commit": True,
            },
        )
        tasks.append(task4)
        session.add(task4)

        return tasks

    def _generate_improvement_tasks(
        self, project: Project, goal: Goal, session: Session
    ) -> List[Task]:
        """Generate tasks for improvement projects.

        Improvement workflow: Research → Document → Update Guide → Validate
        """
        tasks = []

        # Similar structure to research tasks but focused on troubleshooting
        task1 = Task(
            id=str(uuid.uuid4()),
            project_id=project.id,
            title="Research troubleshooting techniques",
            description=f"Investigate solutions for {goal.description}",
            status=TaskStatus.pending,
            priority=TaskPriority.high,
            task_metadata={
                "task_type": "improvement_research",
                "failure_reason": goal.goal_metadata.get("failure_reason"),
            },
        )
        tasks.append(task1)
        session.add(task1)

        session.flush()
        task2 = Task(
            id=str(uuid.uuid4()),
            project_id=project.id,
            title="Update technique guide",
            description="Create or update technique guide in knowledge base",
            status=TaskStatus.pending,
            priority=TaskPriority.medium,
            depends_on=task1.id,
            task_metadata={
                "task_type": "kb_update_technique",
            },
        )
        tasks.append(task2)
        session.add(task2)

        return tasks

    def _generate_optimization_tasks(
        self, project: Project, goal: Goal, session: Session
    ) -> List[Task]:
        """Generate tasks for optimization projects."""
        tasks = []

        task1 = Task(
            id=str(uuid.uuid4()),
            project_id=project.id,
            title="Analyze current metrics",
            description=f"Analyze current performance for {goal.description}",
            status=TaskStatus.pending,
            priority=TaskPriority.high,
            task_metadata={
                "task_type": "optimization_analyze",
            },
        )
        tasks.append(task1)
        session.add(task1)

        session.flush()
        task2 = Task(
            id=str(uuid.uuid4()),
            project_id=project.id,
            title="Document optimization recommendations",
            description="Create optimization report with actionable recommendations",
            status=TaskStatus.pending,
            priority=TaskPriority.medium,
            depends_on=task1.id,
            task_metadata={
                "task_type": "optimization_document",
            },
        )
        tasks.append(task2)
        session.add(task2)

        return tasks

    def _generate_fabrication_tasks(
        self, project: Project, goal: Goal, session: Session
    ) -> List[Task]:
        """Generate tasks for fabrication projects."""
        tasks = []

        # Fabrication requires more tasks and safety checks
        task1 = Task(
            id=str(uuid.uuid4()),
            project_id=project.id,
            title="Generate CAD design",
            description=f"Generate CAD for {goal.description}",
            status=TaskStatus.pending,
            priority=TaskPriority.high,
            task_metadata={
                "task_type": "fabrication_cad",
            },
        )
        tasks.append(task1)
        session.add(task1)

        # Note: Fabrication goals require explicit approval for each task
        # due to safety-critical nature

        return tasks

    def _generate_search_queries(self, goal: Goal) -> List[str]:
        """Generate search queries for research tasks.

        Args:
            goal: Goal object

        Returns:
            List of search query strings
        """
        queries = []

        # Extract key terms from goal description
        description = goal.description.lower()

        if "material" in description:
            # Material research
            material_name = goal.goal_metadata.get("material", "")
            if material_name:
                queries.extend([
                    f"{material_name} 3D printing properties specifications",
                    f"{material_name} print temperature bed temperature settings",
                    f"{material_name} filament suppliers pricing 2025",
                    f"{material_name} sustainability recycling environmental impact",
                ])

        elif "failure" in description or "improve" in description:
            # Troubleshooting research
            failure_reason = goal.goal_metadata.get("failure_reason", "")
            if failure_reason:
                queries.extend([
                    f"3D printing {failure_reason} troubleshooting solutions",
                    f"{failure_reason} print failure causes prevention",
                    f"how to fix {failure_reason} in FDM printing",
                ])

        elif "optim" in description:
            # Optimization research
            queries.extend([
                "LLM routing optimization cost reduction strategies",
                "local inference vs cloud API cost comparison",
                "prompt engineering for better local model performance",
            ])

        # Default fallback
        if not queries:
            queries.append(goal.description)

        return queries

    def _determine_kb_category(self, goal: Goal) -> str:
        """Determine knowledge base category from goal.

        Args:
            goal: Goal object

        Returns:
            Category string (materials, techniques, equipment, research)
        """
        description = goal.description.lower()

        if "material" in description:
            return "materials"
        elif "technique" in description or "failure" in description:
            return "techniques"
        elif "equipment" in description or "printer" in description:
            return "equipment"
        else:
            return "research"


__all__ = ["ProjectGenerator"]
