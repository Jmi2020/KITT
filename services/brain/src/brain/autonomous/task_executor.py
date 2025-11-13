"""Task executor for autonomous project execution.

Executes tasks based on task_type, updating status and managing dependencies.
"""

import logging
import uuid
from datetime import datetime
from decimal import Decimal
from typing import List, Optional, Dict, Any

import structlog
from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from common.db.models import (
    Task,
    TaskStatus,
    Project,
    ProjectStatus,
    Goal,
    GoalStatus,
)
from common.db import SessionLocal

logger = logging.getLogger(__name__)
struct_logger = structlog.get_logger()


class TaskExecutor:
    """Executes autonomous tasks based on task_type.

    Responsibilities:
    - Monitor for executable tasks (pending, no blocking dependencies)
    - Execute tasks based on task_type routing
    - Update task status through lifecycle
    - Mark dependent tasks as ready
    - Update project/goal completion status
    """

    def __init__(
        self,
        session_factory=SessionLocal,
    ):
        """Initialize task executor.

        Args:
            session_factory: SQLAlchemy session factory
        """
        self._session_factory = session_factory

    def execute_ready_tasks(self, limit: int = 5) -> List[Task]:
        """Execute tasks that are ready to run.

        A task is ready if:
        - status = pending
        - depends_on is None OR depends_on task has status = completed

        Args:
            limit: Maximum number of tasks to execute in one cycle

        Returns:
            List of executed Task objects
        """
        struct_logger.info("task_execution_started", limit=limit)

        with self._session_factory() as session:
            # Find ready tasks
            ready_tasks = self._find_ready_tasks(session, limit)

            if not ready_tasks:
                logger.info("No tasks ready for execution")
                struct_logger.info("task_execution_no_tasks")
                return []

            logger.info(f"Found {len(ready_tasks)} tasks ready for execution")

            executed_tasks = []
            for task in ready_tasks:
                try:
                    # Execute the task
                    success = self._execute_task(task, session)

                    if success:
                        executed_tasks.append(task)
                        logger.info(
                            f"✅ Task executed: {task.title} (ID: {task.id[:16]}...)"
                        )
                    else:
                        logger.warning(
                            f"⚠️ Task execution incomplete: {task.title}"
                        )

                except Exception as exc:
                    logger.error(
                        f"Failed to execute task {task.id}: {exc}",
                        exc_info=True
                    )
                    # Mark task as failed
                    task.status = TaskStatus.failed
                    task.result = {
                        "error": str(exc),
                        "failed_at": datetime.utcnow().isoformat(),
                    }
                    session.commit()
                    continue

            # Check for completed projects
            self._update_project_status(session)

            struct_logger.info(
                "task_execution_completed",
                tasks_executed=len(executed_tasks),
                task_ids=[t.id for t in executed_tasks],
            )

            return executed_tasks

    def _find_ready_tasks(self, session: Session, limit: int) -> List[Task]:
        """Find tasks ready for execution.

        Args:
            session: Database session
            limit: Maximum tasks to return

        Returns:
            List of ready Task objects
        """
        # Query for pending tasks
        stmt = (
            select(Task)
            .where(Task.status == TaskStatus.pending)
            .order_by(Task.priority.desc())  # High priority first
            .limit(limit * 3)  # Get extra to filter dependencies
        )

        pending_tasks = session.execute(stmt).scalars().all()

        # Filter by dependency status
        ready_tasks = []
        for task in pending_tasks:
            if task.depends_on is None:
                # No dependencies, ready to run
                ready_tasks.append(task)
            else:
                # Check if dependency is completed
                dependency = session.get(Task, task.depends_on)
                if dependency and dependency.status == TaskStatus.completed:
                    ready_tasks.append(task)

            if len(ready_tasks) >= limit:
                break

        return ready_tasks

    def _execute_task(self, task: Task, session: Session) -> bool:
        """Execute a single task based on task_type.

        Args:
            task: Task object to execute
            session: Database session

        Returns:
            True if task completed successfully, False otherwise
        """
        # Update status to in_progress
        task.status = TaskStatus.in_progress
        task.started_at = datetime.utcnow()
        session.commit()

        struct_logger.info(
            "task_execution_started",
            task_id=task.id,
            task_title=task.title,
            task_type=task.task_metadata.get("task_type"),
        )

        # Route to appropriate executor based on task_type
        task_type = task.task_metadata.get("task_type", "unknown")

        try:
            if task_type == "research_gather":
                result = self._execute_research_gather(task, session)
            elif task_type == "research_synthesize":
                result = self._execute_research_synthesize(task, session)
            elif task_type == "kb_create":
                result = self._execute_kb_create(task, session)
            elif task_type == "review_commit":
                result = self._execute_review_commit(task, session)
            elif task_type == "improvement_research":
                result = self._execute_improvement_research(task, session)
            elif task_type == "kb_update_technique":
                result = self._execute_kb_update_technique(task, session)
            elif task_type == "optimization_analyze":
                result = self._execute_optimization_analyze(task, session)
            elif task_type == "optimization_document":
                result = self._execute_optimization_document(task, session)
            else:
                logger.warning(f"Unknown task_type: {task_type}")
                result = {"error": f"Unknown task_type: {task_type}"}

            # Update task with result
            task.result = result
            task.completed_at = datetime.utcnow()
            task.status = TaskStatus.completed
            session.commit()

            struct_logger.info(
                "task_execution_completed",
                task_id=task.id,
                task_type=task_type,
                result_summary=str(result)[:200],
            )

            return True

        except Exception as exc:
            logger.error(f"Task execution failed: {exc}", exc_info=True)
            task.status = TaskStatus.failed
            task.result = {
                "error": str(exc),
                "failed_at": datetime.utcnow().isoformat(),
            }
            session.commit()
            return False

    def _execute_research_gather(self, task: Task, session: Session) -> Dict[str, Any]:
        """Execute research gather task (Perplexity search).

        Args:
            task: Task object
            session: Database session

        Returns:
            Result dictionary with search results
        """
        logger.info(f"🔍 Executing research gather: {task.title}")

        # Extract search queries from metadata
        queries = task.task_metadata.get("search_queries", [])
        max_cost = task.task_metadata.get("max_cost_usd", 1.0)

        if not queries:
            logger.warning("No search queries provided, using task description")
            queries = [task.description]

        # TODO: Sprint 3.3 - Integrate Perplexity API
        # For now, return placeholder
        logger.info(f"Would execute {len(queries)} Perplexity searches")
        logger.info(f"Queries: {queries[:3]}")

        result = {
            "task_type": "research_gather",
            "queries_executed": len(queries),
            "queries": queries,
            "cost_usd": 0.0,  # Placeholder
            "results": [
                {
                    "query": q,
                    "summary": f"[PLACEHOLDER] Research results for: {q}",
                    "sources": [],
                }
                for q in queries[:3]  # Limit to 3 for placeholder
            ],
            "status": "placeholder_complete",
            "note": "Perplexity integration pending Sprint 3.3",
        }

        return result

    def _execute_research_synthesize(self, task: Task, session: Session) -> Dict[str, Any]:
        """Execute research synthesis task (collective meta-agent).

        Args:
            task: Task object
            session: Database session

        Returns:
            Result dictionary with synthesized content
        """
        logger.info(f"🧠 Executing research synthesis: {task.title}")

        # Get previous task results (research_gather)
        project = session.get(Project, task.project_id)
        gather_task = None
        for t in project.tasks:
            if t.task_metadata.get("task_type") == "research_gather":
                gather_task = t
                break

        if not gather_task or not gather_task.result:
            logger.warning("No gather task results found")
            return {
                "error": "No research results to synthesize",
                "status": "failed",
            }

        # Extract research results
        research_results = gather_task.result.get("results", [])

        # TODO: Sprint 3.3 - Use collective meta-agent for synthesis
        logger.info(f"Would synthesize {len(research_results)} research results")

        result = {
            "task_type": "research_synthesize",
            "input_count": len(research_results),
            "synthesis": "[PLACEHOLDER] Synthesized outline from research results",
            "key_points": [
                "Point 1: Material properties",
                "Point 2: Print settings",
                "Point 3: Suppliers",
            ],
            "status": "placeholder_complete",
            "note": "Collective meta-agent integration pending Sprint 3.3",
        }

        return result

    def _execute_kb_create(self, task: Task, session: Session) -> Dict[str, Any]:
        """Execute KB article creation task.

        Args:
            task: Task object
            session: Database session

        Returns:
            Result dictionary with file path
        """
        logger.info(f"📝 Executing KB article creation: {task.title}")

        # Get synthesis results
        project = session.get(Project, task.project_id)
        synthesize_task = None
        for t in project.tasks:
            if t.task_metadata.get("task_type") == "research_synthesize":
                synthesize_task = t
                break

        if not synthesize_task or not synthesize_task.result:
            logger.warning("No synthesis results found")
            return {
                "error": "No synthesis to create article from",
                "status": "failed",
            }

        # Determine KB category
        kb_category = task.task_metadata.get("kb_category", "research")

        # TODO: Sprint 3.3 - Use KnowledgeUpdater to create article
        logger.info(f"Would create KB article in {kb_category}/")

        result = {
            "task_type": "kb_create",
            "kb_category": kb_category,
            "file_path": f"knowledge/{kb_category}/placeholder-article.md",
            "status": "placeholder_complete",
            "note": "KnowledgeUpdater integration pending Sprint 3.3",
        }

        return result

    def _execute_review_commit(self, task: Task, session: Session) -> Dict[str, Any]:
        """Execute review and git commit task.

        Args:
            task: Task object
            session: Database session

        Returns:
            Result dictionary with commit info
        """
        logger.info(f"✅ Executing review and commit: {task.title}")

        # Get KB creation results
        project = session.get(Project, task.project_id)
        kb_task = None
        for t in project.tasks:
            if t.task_metadata.get("task_type") == "kb_create":
                kb_task = t
                break

        if not kb_task or not kb_task.result:
            logger.warning("No KB article to commit")
            return {
                "error": "No KB article found",
                "status": "failed",
            }

        file_path = kb_task.result.get("file_path")

        # TODO: Sprint 3.3 - Git operations
        logger.info(f"Would commit file: {file_path}")

        result = {
            "task_type": "review_commit",
            "file_path": file_path,
            "commit_sha": "placeholder_commit_sha",
            "status": "placeholder_complete",
            "note": "Git commit integration pending Sprint 3.3",
        }

        return result

    def _execute_improvement_research(self, task: Task, session: Session) -> Dict[str, Any]:
        """Execute improvement research task."""
        logger.info(f"🔧 Executing improvement research: {task.title}")

        result = {
            "task_type": "improvement_research",
            "status": "placeholder_complete",
            "note": "Improvement research pending Sprint 3.3",
        }

        return result

    def _execute_kb_update_technique(self, task: Task, session: Session) -> Dict[str, Any]:
        """Execute KB technique update task."""
        logger.info(f"📚 Executing KB technique update: {task.title}")

        result = {
            "task_type": "kb_update_technique",
            "status": "placeholder_complete",
            "note": "Technique update pending Sprint 3.3",
        }

        return result

    def _execute_optimization_analyze(self, task: Task, session: Session) -> Dict[str, Any]:
        """Execute optimization analysis task."""
        logger.info(f"📊 Executing optimization analysis: {task.title}")

        result = {
            "task_type": "optimization_analyze",
            "status": "placeholder_complete",
            "note": "Optimization analysis pending Sprint 3.3",
        }

        return result

    def _execute_optimization_document(self, task: Task, session: Session) -> Dict[str, Any]:
        """Execute optimization documentation task."""
        logger.info(f"📄 Executing optimization documentation: {task.title}")

        result = {
            "task_type": "optimization_document",
            "status": "placeholder_complete",
            "note": "Optimization documentation pending Sprint 3.3",
        }

        return result

    def _update_project_status(self, session: Session) -> None:
        """Check and update project completion status.

        Args:
            session: Database session
        """
        # Find projects with all tasks completed
        stmt = select(Project).where(Project.status == ProjectStatus.proposed)
        projects = session.execute(stmt).scalars().all()

        for project in projects:
            total_tasks = len(project.tasks)
            if total_tasks == 0:
                continue

            completed_tasks = sum(
                1 for t in project.tasks if t.status == TaskStatus.completed
            )
            failed_tasks = sum(
                1 for t in project.tasks if t.status == TaskStatus.failed
            )

            if completed_tasks == total_tasks:
                # All tasks completed
                project.status = ProjectStatus.completed
                project.completed_at = datetime.utcnow()

                # Update goal status
                if project.goal_id:
                    goal = session.get(Goal, project.goal_id)
                    if goal:
                        goal.status = GoalStatus.completed

                logger.info(
                    f"🎉 Project completed: {project.title} "
                    f"({completed_tasks}/{total_tasks} tasks)"
                )

                struct_logger.info(
                    "project_completed",
                    project_id=project.id,
                    project_title=project.title,
                    tasks_completed=completed_tasks,
                    goal_id=project.goal_id,
                )

            elif failed_tasks > 0:
                # Some tasks failed
                project.status = ProjectStatus.in_progress
                logger.warning(
                    f"Project has failed tasks: {project.title} "
                    f"({failed_tasks} failed, {completed_tasks} completed)"
                )

        session.commit()


__all__ = ["TaskExecutor"]
