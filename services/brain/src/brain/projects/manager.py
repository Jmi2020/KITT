"""
Project lifecycle management for KITTY autonomous operations.

Handles CRUD operations, state transitions, budget allocation, and approval
workflows for Goals, Projects, and Tasks.
"""

import logging
import uuid
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy.orm import Session

from common.db import SessionLocal
from common.db.models import (
    Goal,
    GoalStatus,
    GoalType,
    Project,
    ProjectStatus,
    Task,
    TaskPriority,
    TaskStatus,
)

logger = logging.getLogger(__name__)


class ProjectManager:
    """
    Manages the lifecycle of autonomous projects and tasks.

    Provides methods for creating, approving, executing, and completing
    projects and tasks with proper state transitions and budget tracking.
    """

    def __init__(self, session_factory=SessionLocal):
        """
        Initialize ProjectManager.

        Args:
            session_factory: SQLAlchemy session factory (default: SessionLocal)
        """
        self.session_factory = session_factory

    def create_goal(
        self,
        goal_type: GoalType,
        description: str,
        rationale: str,
        estimated_budget: float,
        estimated_duration_hours: Optional[int] = None,
        metadata: Optional[dict] = None,
    ) -> Goal:
        """
        Create a new goal.

        Args:
            goal_type: Type of goal (research, fabrication, improvement, optimization)
            description: Description of the goal
            rationale: Why KITTY identified this goal
            estimated_budget: Estimated cost in USD
            estimated_duration_hours: Estimated time to complete (hours)
            metadata: Additional metadata (dict)

        Returns:
            Created Goal object
        """
        with self.session_factory() as session:
            goal = Goal(
                id=str(uuid.uuid4()),
                goal_type=goal_type,
                description=description,
                rationale=rationale,
                estimated_budget=Decimal(str(estimated_budget)),
                estimated_duration_hours=estimated_duration_hours,
                status=GoalStatus.identified,
                identified_at=datetime.utcnow(),
                goal_metadata=metadata or {},
            )
            session.add(goal)
            session.commit()
            session.refresh(goal)
            logger.info(f"Created goal '{goal.id}' ({goal_type.value}): {description}")
            return goal

    def approve_goal(
        self, goal_id: str, approved_by: str, session: Optional[Session] = None
    ) -> Goal:
        """
        Approve a goal.

        Args:
            goal_id: Goal ID
            approved_by: User ID of approver
            session: Optional existing session

        Returns:
            Updated Goal object

        Raises:
            ValueError: If goal not found or invalid state transition
        """

        def _approve(sess: Session) -> Goal:
            goal = sess.query(Goal).filter(Goal.id == goal_id).first()
            if not goal:
                raise ValueError(f"Goal {goal_id} not found")

            if goal.status != GoalStatus.identified:
                raise ValueError(
                    f"Goal {goal_id} cannot be approved from status {goal.status.value}"
                )

            goal.status = GoalStatus.approved
            goal.approved_at = datetime.utcnow()
            goal.approved_by = approved_by
            sess.commit()
            sess.refresh(goal)
            logger.info(f"Approved goal '{goal.id}' by user {approved_by}")
            return goal

        if session:
            return _approve(session)

        with self.session_factory() as sess:
            return _approve(sess)

    def reject_goal(self, goal_id: str, session: Optional[Session] = None) -> Goal:
        """
        Reject a goal.

        Args:
            goal_id: Goal ID
            session: Optional existing session

        Returns:
            Updated Goal object

        Raises:
            ValueError: If goal not found or invalid state transition
        """

        def _reject(sess: Session) -> Goal:
            goal = sess.query(Goal).filter(Goal.id == goal_id).first()
            if not goal:
                raise ValueError(f"Goal {goal_id} not found")

            if goal.status != GoalStatus.identified:
                raise ValueError(
                    f"Goal {goal_id} cannot be rejected from status {goal.status.value}"
                )

            goal.status = GoalStatus.rejected
            sess.commit()
            sess.refresh(goal)
            logger.info(f"Rejected goal '{goal.id}'")
            return goal

        if session:
            return _reject(session)

        with self.session_factory() as sess:
            return _reject(sess)

    def create_project(
        self,
        title: str,
        description: str,
        budget_allocated: float,
        goal_id: Optional[str] = None,
        created_by: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> Project:
        """
        Create a new project.

        Args:
            title: Project title
            description: Project description
            budget_allocated: Allocated budget in USD
            goal_id: Optional parent goal ID
            created_by: User ID of creator (use "system-autonomous" for autonomous)
            metadata: Additional metadata (dict)

        Returns:
            Created Project object
        """
        with self.session_factory() as session:
            project = Project(
                id=str(uuid.uuid4()),
                goal_id=goal_id,
                title=title,
                description=description,
                status=ProjectStatus.proposed,
                budget_allocated=Decimal(str(budget_allocated)),
                budget_spent=Decimal("0.0"),
                created_by=created_by or "system-autonomous",
                created_at=datetime.utcnow(),
                project_metadata=metadata or {},
            )
            session.add(project)
            session.commit()
            session.refresh(project)
            logger.info(f"Created project '{project.id}': {title}")
            return project

    def approve_project(
        self, project_id: str, session: Optional[Session] = None
    ) -> Project:
        """
        Approve a proposed project.

        Args:
            project_id: Project ID
            session: Optional existing session

        Returns:
            Updated Project object

        Raises:
            ValueError: If project not found or invalid state transition
        """

        def _approve(sess: Session) -> Project:
            project = sess.query(Project).filter(Project.id == project_id).first()
            if not project:
                raise ValueError(f"Project {project_id} not found")

            if project.status != ProjectStatus.proposed:
                raise ValueError(
                    f"Project {project_id} cannot be approved from status {project.status.value}"
                )

            project.status = ProjectStatus.approved
            sess.commit()
            sess.refresh(project)
            logger.info(f"Approved project '{project.id}'")
            return project

        if session:
            return _approve(session)

        with self.session_factory() as sess:
            return _approve(sess)

    def start_project(
        self, project_id: str, session: Optional[Session] = None
    ) -> Project:
        """
        Start an approved project.

        Args:
            project_id: Project ID
            session: Optional existing session

        Returns:
            Updated Project object

        Raises:
            ValueError: If project not found or invalid state transition
        """

        def _start(sess: Session) -> Project:
            project = sess.query(Project).filter(Project.id == project_id).first()
            if not project:
                raise ValueError(f"Project {project_id} not found")

            if project.status != ProjectStatus.approved:
                raise ValueError(
                    f"Project {project_id} cannot be started from status {project.status.value}"
                )

            project.status = ProjectStatus.in_progress
            project.started_at = datetime.utcnow()
            sess.commit()
            sess.refresh(project)
            logger.info(f"Started project '{project.id}'")
            return project

        if session:
            return _start(session)

        with self.session_factory() as sess:
            return _start(sess)

    def complete_project(
        self, project_id: str, session: Optional[Session] = None
    ) -> Project:
        """
        Complete a project.

        Args:
            project_id: Project ID
            session: Optional existing session

        Returns:
            Updated Project object

        Raises:
            ValueError: If project not found or invalid state transition
        """

        def _complete(sess: Session) -> Project:
            project = sess.query(Project).filter(Project.id == project_id).first()
            if not project:
                raise ValueError(f"Project {project_id} not found")

            if project.status != ProjectStatus.in_progress:
                raise ValueError(
                    f"Project {project_id} cannot be completed from status {project.status.value}"
                )

            project.status = ProjectStatus.completed
            project.completed_at = datetime.utcnow()
            sess.commit()
            sess.refresh(project)
            logger.info(f"Completed project '{project.id}'")

            # Mark associated goal as completed if exists
            if project.goal_id:
                goal = sess.query(Goal).filter(Goal.id == project.goal_id).first()
                if goal and goal.status == GoalStatus.approved:
                    goal.status = GoalStatus.completed
                    sess.commit()
                    logger.info(f"Completed associated goal '{goal.id}'")

            return project

        if session:
            return _complete(session)

        with self.session_factory() as sess:
            return _complete(sess)

    def cancel_project(
        self, project_id: str, session: Optional[Session] = None
    ) -> Project:
        """
        Cancel a project.

        Args:
            project_id: Project ID
            session: Optional existing session

        Returns:
            Updated Project object

        Raises:
            ValueError: If project not found
        """

        def _cancel(sess: Session) -> Project:
            project = sess.query(Project).filter(Project.id == project_id).first()
            if not project:
                raise ValueError(f"Project {project_id} not found")

            project.status = ProjectStatus.cancelled
            sess.commit()
            sess.refresh(project)
            logger.info(f"Cancelled project '{project.id}'")
            return project

        if session:
            return _cancel(session)

        with self.session_factory() as sess:
            return _cancel(sess)

    def record_cost(
        self, project_id: str, cost_usd: float, session: Optional[Session] = None
    ) -> Project:
        """
        Record cost against project budget.

        Args:
            project_id: Project ID
            cost_usd: Cost in USD
            session: Optional existing session

        Returns:
            Updated Project object

        Raises:
            ValueError: If project not found or budget exceeded
        """

        def _record(sess: Session) -> Project:
            project = sess.query(Project).filter(Project.id == project_id).first()
            if not project:
                raise ValueError(f"Project {project_id} not found")

            cost_decimal = Decimal(str(cost_usd))
            new_spent = project.budget_spent + cost_decimal

            if new_spent > project.budget_allocated:
                raise ValueError(
                    f"Cost ${cost_usd} would exceed project budget "
                    f"(allocated: ${project.budget_allocated}, "
                    f"spent: ${project.budget_spent})"
                )

            project.budget_spent = new_spent
            sess.commit()
            sess.refresh(project)
            logger.info(
                f"Recorded ${cost_usd} cost for project '{project.id}' "
                f"(total spent: ${project.budget_spent})"
            )
            return project

        if session:
            return _record(session)

        with self.session_factory() as sess:
            return _record(sess)

    def create_task(
        self,
        project_id: str,
        title: str,
        description: str,
        priority: TaskPriority = TaskPriority.medium,
        depends_on: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> Task:
        """
        Create a new task within a project.

        Args:
            project_id: Parent project ID
            title: Task title
            description: Task description
            priority: Task priority (low, medium, high, critical)
            depends_on: Optional task ID this task depends on
            metadata: Additional metadata (dict)

        Returns:
            Created Task object
        """
        with self.session_factory() as session:
            task = Task(
                id=str(uuid.uuid4()),
                project_id=project_id,
                title=title,
                description=description,
                status=TaskStatus.pending,
                priority=priority,
                depends_on=depends_on,
                task_metadata=metadata or {},
            )
            session.add(task)
            session.commit()
            session.refresh(task)
            logger.info(
                f"Created task '{task.id}' in project '{project_id}': {title} (priority: {priority.value})"
            )
            return task

    def start_task(self, task_id: str, session: Optional[Session] = None) -> Task:
        """
        Start a pending task.

        Args:
            task_id: Task ID
            session: Optional existing session

        Returns:
            Updated Task object

        Raises:
            ValueError: If task not found or invalid state transition
        """

        def _start(sess: Session) -> Task:
            task = sess.query(Task).filter(Task.id == task_id).first()
            if not task:
                raise ValueError(f"Task {task_id} not found")

            if task.status not in [TaskStatus.pending, TaskStatus.blocked]:
                raise ValueError(
                    f"Task {task_id} cannot be started from status {task.status.value}"
                )

            task.status = TaskStatus.in_progress
            task.started_at = datetime.utcnow()
            sess.commit()
            sess.refresh(task)
            logger.info(f"Started task '{task.id}'")
            return task

        if session:
            return _start(session)

        with self.session_factory() as sess:
            return _start(sess)

    def complete_task(
        self, task_id: str, result: Optional[dict] = None, session: Optional[Session] = None
    ) -> Task:
        """
        Complete a task.

        Args:
            task_id: Task ID
            result: Optional result data (dict)
            session: Optional existing session

        Returns:
            Updated Task object

        Raises:
            ValueError: If task not found or invalid state transition
        """

        def _complete(sess: Session) -> Task:
            task = sess.query(Task).filter(Task.id == task_id).first()
            if not task:
                raise ValueError(f"Task {task_id} not found")

            if task.status != TaskStatus.in_progress:
                raise ValueError(
                    f"Task {task_id} cannot be completed from status {task.status.value}"
                )

            task.status = TaskStatus.completed
            task.completed_at = datetime.utcnow()
            if result:
                task.result = result
            sess.commit()
            sess.refresh(task)
            logger.info(f"Completed task '{task.id}'")
            return task

        if session:
            return _complete(session)

        with self.session_factory() as sess:
            return _complete(sess)

    def fail_task(
        self, task_id: str, error: str, session: Optional[Session] = None
    ) -> Task:
        """
        Mark a task as failed.

        Args:
            task_id: Task ID
            error: Error message or reason
            session: Optional existing session

        Returns:
            Updated Task object

        Raises:
            ValueError: If task not found
        """

        def _fail(sess: Session) -> Task:
            task = sess.query(Task).filter(Task.id == task_id).first()
            if not task:
                raise ValueError(f"Task {task_id} not found")

            task.status = TaskStatus.failed
            task.result = {"error": error}
            sess.commit()
            sess.refresh(task)
            logger.warning(f"Marked task '{task.id}' as failed: {error}")
            return task

        if session:
            return _fail(session)

        with self.session_factory() as sess:
            return _fail(sess)

    def get_project(self, project_id: str) -> Optional[Project]:
        """
        Get a project by ID.

        Args:
            project_id: Project ID

        Returns:
            Project object or None if not found
        """
        with self.session_factory() as session:
            return session.query(Project).filter(Project.id == project_id).first()

    def get_projects_by_status(self, status: ProjectStatus) -> List[Project]:
        """
        Get all projects with a specific status.

        Args:
            status: Project status

        Returns:
            List of Project objects
        """
        with self.session_factory() as session:
            projects = session.query(Project).filter(Project.status == status).all()
            # Detach from session to avoid lazy loading issues
            session.expunge_all()
            return projects

    def get_project_tasks(self, project_id: str) -> List[Task]:
        """
        Get all tasks for a project.

        Args:
            project_id: Project ID

        Returns:
            List of Task objects
        """
        with self.session_factory() as session:
            tasks = session.query(Task).filter(Task.project_id == project_id).all()
            # Detach from session
            session.expunge_all()
            return tasks

    def get_goals_by_status(self, status: GoalStatus) -> List[Goal]:
        """
        Get all goals with a specific status.

        Args:
            status: Goal status

        Returns:
            List of Goal objects
        """
        with self.session_factory() as session:
            goals = session.query(Goal).filter(Goal.status == status).all()
            # Detach from session
            session.expunge_all()
            return goals


# Singleton instance
_manager_instance: Optional[ProjectManager] = None


def get_project_manager() -> ProjectManager:
    """
    Get the singleton ProjectManager instance.

    Returns:
        ProjectManager instance
    """
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = ProjectManager()
    return _manager_instance
