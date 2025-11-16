"""Task executor for autonomous project execution.

Executes tasks based on task_type, updating status and managing dependencies.

Features:
- Distributed locking to prevent race conditions in concurrent job execution
- Task type routing (research_gather, research_synthesize, kb_create, etc.)
- Dependency management
- Project/goal status tracking
"""

import asyncio
import logging
import subprocess
import uuid
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import List, Optional, Dict, Any

import structlog
import redis.asyncio as aioredis
from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from common.config import settings
from common.db.models import (
    Task,
    TaskStatus,
    Project,
    ProjectStatus,
    Goal,
    GoalStatus,
)
from common.db import SessionLocal

from brain.routing.cloud_clients import MCPClient
from brain.agents.collective.graph_async import build_collective_graph_async
from brain.knowledge.updater import KnowledgeUpdater
from brain.autonomous.distributed_lock import LockManager, get_lock_manager

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
        mcp_client: Optional[MCPClient] = None,
        kb_updater: Optional[KnowledgeUpdater] = None,
        lock_manager: Optional[LockManager] = None,
    ):
        """Initialize task executor.

        Args:
            session_factory: SQLAlchemy session factory
            mcp_client: Perplexity MCP client (optional, will create if needed)
            kb_updater: Knowledge base updater (optional, will create if needed)
            lock_manager: Distributed lock manager (optional, uses global if not provided)
        """
        self._session_factory = session_factory
        # Use provided lock manager, or fallback to global instance
        self._lock_manager = lock_manager or get_lock_manager()

        # Initialize Perplexity MCP client
        if mcp_client:
            self._mcp = mcp_client
        elif settings.perplexity_api_key:
            self._mcp = MCPClient(
                base_url=settings.perplexity_base_url,
                api_key=settings.perplexity_api_key,
                model=getattr(settings, "perplexity_model_search", "sonar"),
            )
        else:
            self._mcp = None
            logger.warning("Perplexity API key not configured, research_gather will fail")

        # Initialize Knowledge Updater
        self._kb_updater = kb_updater or KnowledgeUpdater()

        # Initialize collective graph (lazy, built on first use)
        self._collective_graph = None

    def _calculate_perplexity_cost(self, tokens: int, model: str) -> float:
        """Calculate Perplexity API cost based on model and token count.

        Args:
            tokens: Total token count (input + output)
            model: Perplexity model name

        Returns:
            Cost in USD

        Note:
            Pricing is per 1M tokens as of 2025-01.
            For models with different input/output pricing, we use the average.
            Actual costs may vary slightly; check https://docs.perplexity.ai/guides/pricing
        """
        # Pricing per 1M tokens (as of 2025-01)
        # For models with split pricing, use average of input/output
        pricing = {
            "sonar": 0.20,                    # $0.20 combined input/output
            "sonar-pro": 9.0,                 # Average of $3 input + $15 output
            "sonar-reasoning": 3.0,           # Average of $1 input + $5 output
            "sonar-reasoning-pro": 5.0,       # Average of $2 input + $8 output
            "sonar-deep-research": 9.0,       # Estimated, similar to sonar-pro
        }

        rate = pricing.get(model, 0.20)  # Default to sonar pricing
        return (tokens / 1_000_000) * rate

    async def execute_ready_tasks(self, limit: int = 5) -> List[Task]:
        """Execute tasks that are ready to run with distributed locking.

        A task is ready if:
        - status = pending
        - depends_on is None OR depends_on task has status = completed
        - NOT currently locked (being executed by another job)

        Uses distributed locking to prevent race conditions when multiple
        APScheduler jobs run concurrently.

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
                    # Try to acquire distributed lock for this task
                    if self._lock_manager:
                        try:
                            async with self._lock_manager.lock_task(task.id):
                                # Lock acquired - execute task
                                success = await self._execute_task_async(task, session)

                                if success:
                                    executed_tasks.append(task)
                                    logger.info(
                                        f"✅ Task executed: {task.title} (ID: {task.id[:16]}...)"
                                    )
                                else:
                                    logger.warning(
                                        f"⚠️ Task execution incomplete: {task.title}"
                                    )
                        except RuntimeError as lock_err:
                            # Failed to acquire lock - task is being executed by another job
                            logger.info(
                                f"⏭️ Skipping task (locked by another job): {task.title}"
                            )
                            continue
                    else:
                        # No lock manager - execute without locking (backwards compatible)
                        logger.warning(
                            "LockManager not configured - executing without distributed locks"
                        )
                        success = await self._execute_task_async(task, session)

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
                skipped=len(ready_tasks) - len(executed_tasks)
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

    async def _execute_task_async(self, task: Task, session: Session) -> bool:
        """Async wrapper for task execution.

        Runs the synchronous _execute_task in a thread pool to avoid blocking
        the event loop during long-running task execution.

        Args:
            task: Task object to execute
            session: Database session

        Returns:
            True if task completed successfully, False otherwise
        """
        # Run synchronous task execution in thread pool
        return await asyncio.to_thread(self._execute_task, task, session)

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

        # Check if Perplexity is configured
        if not self._mcp:
            raise RuntimeError(
                "Perplexity API not configured. Set PERPLEXITY_API_KEY in .env"
            )

        # Extract search queries from metadata
        queries = task.task_metadata.get("search_queries", [])
        max_cost = task.task_metadata.get("max_cost_usd", 1.0)

        if not queries:
            logger.warning("No search queries provided, using task description")
            queries = [task.description]

        # Extract optional Perplexity search parameters and model selection
        # These control result quality and sources
        search_params = {}
        if "search_domain_filter" in task.task_metadata:
            search_params["search_domain_filter"] = task.task_metadata["search_domain_filter"]
        if "search_recency_filter" in task.task_metadata:
            search_params["search_recency_filter"] = task.task_metadata["search_recency_filter"]
        if "return_related_questions" in task.task_metadata:
            search_params["return_related_questions"] = task.task_metadata["return_related_questions"]

        # Allow per-task model override (e.g., sonar-pro for high-impact research)
        perplexity_model = task.task_metadata.get("perplexity_model", self._mcp._model)
        search_params["model"] = perplexity_model

        logger.info(f"Executing {len(queries)} Perplexity searches with model={perplexity_model}, search_params: {search_params}")

        # Execute searches using Perplexity API (async)
        # Run in event loop since _execute_task is synchronous
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Create new loop if one is already running
            results = asyncio.run(self._gather_research_async(queries, search_params))
        else:
            results = loop.run_until_complete(self._gather_research_async(queries, search_params))

        # Calculate actual cost based on token usage
        total_tokens = sum(r.get("usage", {}).get("total_tokens", 0) for r in results)
        cost_usd = self._calculate_perplexity_cost(total_tokens, model=perplexity_model)

        result = {
            "task_type": "research_gather",
            "queries_executed": len(queries),
            "queries": queries,
            "cost_usd": cost_usd,
            "total_tokens": total_tokens,
            "results": results,
            "status": "completed",
        }

        struct_logger.info(
            "research_gather_completed",
            task_id=task.id,
            queries_count=len(queries),
            total_tokens=total_tokens,
            cost_usd=cost_usd,
        )

        return result

    async def _gather_research_async(
        self, queries: List[str], search_params: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Execute multiple research queries in parallel.

        Args:
            queries: List of search queries
            search_params: Optional Perplexity search parameters:
                          - search_domain_filter: List of domains to include/exclude
                          - search_recency_filter: "day", "week", "month", "year"
                          - return_related_questions: Include related questions

        Returns:
            List of result dictionaries
        """
        results = []
        search_params = search_params or {}

        for query in queries:
            try:
                # Build query payload with search parameters
                payload = {"query": query, **search_params}

                # Query Perplexity API
                response = await self._mcp.query(payload)

                # Extract output
                output = response.get("output", "")

                # Parse sources and usage from raw response
                # Try multiple locations as Perplexity API format may vary
                raw = response.get("raw", {})

                # Extract citations from multiple possible locations
                sources = (
                    raw.get("citations", []) or  # Top-level citations
                    (raw.get("choices", [{}])[0].get("metadata", {}).get("citations", []) if raw.get("choices") else [])  # Choice metadata
                )

                # Extract usage data for cost tracking
                usage = raw.get("usage", {})

                results.append(
                    {
                        "query": query,
                        "summary": output,
                        "sources": sources,
                        "usage": usage,
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                )

                logger.info(f"✅ Research query completed: {query[:60]}...")

            except Exception as exc:
                logger.error(f"Failed to execute query '{query}': {exc}", exc_info=True)
                results.append(
                    {
                        "query": query,
                        "summary": "",
                        "error": str(exc),
                        "sources": [],
                        "usage": {},
                    }
                )

        return results

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

        if not research_results:
            return {
                "error": "No research results to synthesize",
                "status": "failed",
            }

        logger.info(f"Synthesizing {len(research_results)} research results using collective meta-agent")

        # Build collective graph if not already built
        if not self._collective_graph:
            self._collective_graph = build_collective_graph_async()

        # Prepare synthesis task prompt
        research_summary = "\n\n".join([
            f"Query: {r.get('query', 'Unknown')}\n"
            f"Summary: {r.get('summary', 'No summary')}\n"
            f"Sources: {', '.join(r.get('sources', []))}"
            for r in research_results
        ])

        synthesis_prompt = f"""Synthesize the following research findings into a structured knowledge base article outline.

Research Topic: {task.title}
Goal: {project.goal.description if project.goal else 'Unknown'}

Research Findings:
{research_summary}

Please provide:
1. A concise title for the knowledge base article
2. An executive summary (2-3 sentences)
3. A structured outline with key sections and bullet points
4. Key insights and recommendations
5. Suggested tags for categorization

Format your response as a structured outline suitable for a knowledge base article."""

        # Run collective meta-agent (council pattern with k=3 specialists)
        # Run in event loop since this is synchronous context
        loop = asyncio.get_event_loop()
        if loop.is_running():
            synthesis_result = asyncio.run(self._run_collective_synthesis(synthesis_prompt))
        else:
            synthesis_result = loop.run_until_complete(
                self._run_collective_synthesis(synthesis_prompt)
            )

        # Extract verdict from collective result
        synthesis = synthesis_result.get("verdict", "")

        result = {
            "task_type": "research_synthesize",
            "input_count": len(research_results),
            "synthesis": synthesis,
            "collective_logs": synthesis_result.get("logs", ""),
            "status": "completed",
        }

        struct_logger.info(
            "research_synthesize_completed",
            task_id=task.id,
            input_count=len(research_results),
        )

        return result

    async def _run_collective_synthesis(self, prompt: str) -> Dict[str, Any]:
        """Run collective meta-agent for synthesis.

        Args:
            prompt: Synthesis task prompt

        Returns:
            Collective result with verdict
        """
        # Invoke collective graph
        result = await self._collective_graph.ainvoke({
            "task": prompt,
            "pattern": "council",  # Use council pattern for synthesis
            "k": 3,  # 3 specialist proposers
        })

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
        gather_task = None

        for t in project.tasks:
            if t.task_metadata.get("task_type") == "research_synthesize":
                synthesize_task = t
            elif t.task_metadata.get("task_type") == "research_gather":
                gather_task = t

        if not synthesize_task or not synthesize_task.result:
            logger.warning("No synthesis results found")
            return {
                "error": "No synthesis to create article from",
                "status": "failed",
            }

        # Extract synthesis content
        synthesis = synthesize_task.result.get("synthesis", "")

        if not synthesis:
            return {
                "error": "Empty synthesis content",
                "status": "failed",
            }

        # Extract sources from gather task
        sources = []
        if gather_task and gather_task.result:
            for r in gather_task.result.get("results", []):
                sources.extend(r.get("sources", []))

        # Get goal info for metadata
        goal = project.goal if project.goal else None
        goal_id = goal.id if goal else None

        # Extract topic from task or goal
        topic = task.task_metadata.get("topic", task.title)

        # Get cost from gather task
        cost_usd = None
        if gather_task and gather_task.result:
            cost_usd = gather_task.result.get("cost_usd", 0.0)

        logger.info(f"Creating knowledge base article: {topic}")

        # Create research article using KnowledgeUpdater
        # auto_commit=False because review_commit task will handle git operations
        try:
            file_path = self._kb_updater.create_research_article(
                topic=topic,
                content=synthesis,
                goal_id=goal_id,
                project_id=project.id,
                cost_usd=cost_usd,
                sources=sources,
                auto_commit=False,  # Will be committed by review_commit task
            )

            result = {
                "task_type": "kb_create",
                "topic": topic,
                "file_path": str(file_path),
                "goal_id": goal_id,
                "project_id": project.id,
                "sources_count": len(sources),
                "status": "completed",
            }

            struct_logger.info(
                "kb_create_completed",
                task_id=task.id,
                file_path=str(file_path),
                sources_count=len(sources),
            )

            logger.info(f"✅ Knowledge base article created: {file_path}")

            return result

        except Exception as exc:
            logger.error(f"Failed to create KB article: {exc}", exc_info=True)
            return {
                "error": str(exc),
                "status": "failed",
            }

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

        file_path_str = kb_task.result.get("file_path")
        file_path = Path(file_path_str)

        if not file_path.exists():
            logger.error(f"KB article file not found: {file_path}")
            return {
                "error": f"File not found: {file_path}",
                "status": "failed",
            }

        # Extract topic for commit message
        topic = kb_task.result.get("topic", "research")

        # Validate file (basic check for YAML frontmatter)
        try:
            with open(file_path, "r") as f:
                content = f.read()
                if not content.startswith("---"):
                    logger.warning("File missing YAML frontmatter, but proceeding with commit")
        except Exception as exc:
            logger.error(f"Failed to read file for validation: {exc}")
            return {
                "error": f"File validation failed: {exc}",
                "status": "failed",
            }

        # Execute git operations
        logger.info(f"Committing file: {file_path}")

        try:
            # Get repo root (knowledge base parent directory)
            repo_root = file_path.parent.parent.parent

            # Get relative path from repo root
            rel_path = file_path.relative_to(repo_root)

            # Git add
            add_result = subprocess.run(
                ["git", "add", str(rel_path)],
                cwd=repo_root,
                check=True,
                capture_output=True,
                text=True,
            )

            # Git commit with autonomous tag
            commit_message = f"KB: autonomous update - {topic}"
            commit_result = subprocess.run(
                ["git", "commit", "-m", commit_message],
                cwd=repo_root,
                check=True,
                capture_output=True,
                text=True,
            )

            # Get commit SHA
            sha_result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo_root,
                check=True,
                capture_output=True,
                text=True,
            )
            commit_sha = sha_result.stdout.strip()

            result = {
                "task_type": "review_commit",
                "file_path": str(file_path),
                "commit_sha": commit_sha,
                "commit_message": commit_message,
                "status": "completed",
            }

            struct_logger.info(
                "review_commit_completed",
                task_id=task.id,
                file_path=str(rel_path),
                commit_sha=commit_sha,
            )

            logger.info(f"✅ Git commit successful: {commit_sha[:8]} - {commit_message}")

            return result

        except subprocess.CalledProcessError as exc:
            error_msg = exc.stderr if exc.stderr else str(exc)
            logger.error(f"Git commit failed: {error_msg}", exc_info=True)
            return {
                "error": f"Git commit failed: {error_msg}",
                "status": "failed",
            }

    def _execute_improvement_research(self, task: Task, session: Session) -> Dict[str, Any]:
        """Execute improvement research task.

        This combines research_gather + research_synthesize into a single task
        for improvement goals (smaller scope than full research goals).
        """
        logger.info(f"🔧 Executing improvement research: {task.title}")

        # Check if Perplexity is configured
        if not self._mcp:
            raise RuntimeError(
                "Perplexity API not configured. Set PERPLEXITY_API_KEY in .env"
            )

        # Extract search query from task metadata or use description
        query = task.task_metadata.get("search_query", task.description)

        logger.info(f"Executing improvement research query: {query}")

        # Execute single Perplexity search
        loop = asyncio.get_event_loop()
        if loop.is_running():
            search_results = asyncio.run(self._gather_research_async([query]))
        else:
            search_results = loop.run_until_complete(self._gather_research_async([query]))

        # Extract result
        if search_results and len(search_results) > 0:
            research_output = search_results[0].get("summary", "")
            sources = search_results[0].get("sources", [])
        else:
            research_output = ""
            sources = []

        result = {
            "task_type": "improvement_research",
            "query": query,
            "research_output": research_output,
            "sources": sources,
            "cost_usd": 0.001,  # Rough estimate
            "status": "completed",
        }

        struct_logger.info(
            "improvement_research_completed",
            task_id=task.id,
            query=query,
            sources_count=len(sources),
        )

        return result

    def _execute_kb_update_technique(self, task: Task, session: Session) -> Dict[str, Any]:
        """Execute KB technique update task.

        Updates an existing technique guide based on improvement research results.
        """
        logger.info(f"📚 Executing KB technique update: {task.title}")

        # Get previous task results (improvement_research)
        project = session.get(Project, task.project_id)
        research_task = None
        for t in project.tasks:
            if t.task_metadata.get("task_type") == "improvement_research":
                research_task = t
                break

        if not research_task or not research_task.result:
            logger.warning("No research results found for technique update")
            return {
                "error": "No research results to update technique with",
                "status": "failed",
            }

        # Extract research output
        research_output = research_task.result.get("research_output", "")
        sources = research_task.result.get("sources", [])

        if not research_output:
            return {
                "error": "Empty research output",
                "status": "failed",
            }

        # Extract technique slug from metadata
        technique_slug = task.task_metadata.get("technique_slug")

        if not technique_slug:
            # Try to infer from task title or description
            logger.warning("No technique_slug provided, using placeholder")
            technique_slug = "autonomous-improvement"

        logger.info(f"Updating technique: {technique_slug}")

        # Format update content with research findings
        update_content = f"""
## Autonomous Update - {datetime.utcnow().strftime('%Y-%m-%d')}

{research_output}

### Sources
{chr(10).join([f"- {source}" for source in sources])}
"""

        # Update technique guide
        try:
            # Check if technique exists, otherwise create it
            technique_path = self._kb_updater.techniques_path / f"{technique_slug}.md"

            if technique_path.exists():
                # Update existing technique
                file_path = self._kb_updater.update_material(
                    slug=technique_slug,
                    updates={"content": update_content},
                    auto_commit=True,
                )
                action = "updated"
            else:
                # Create new technique guide
                file_path = self._kb_updater.create_technique(
                    slug=technique_slug,
                    name=task.title,
                    content=update_content,
                    metadata={
                        "autonomous": True,
                        "project_id": project.id,
                        "goal_id": project.goal_id,
                    },
                    auto_commit=True,
                )
                action = "created"

            result = {
                "task_type": "kb_update_technique",
                "technique_slug": technique_slug,
                "file_path": str(file_path),
                "action": action,
                "sources_count": len(sources),
                "status": "completed",
            }

            struct_logger.info(
                "kb_update_technique_completed",
                task_id=task.id,
                technique_slug=technique_slug,
                action=action,
            )

            logger.info(f"✅ Technique {action}: {file_path}")

            return result

        except Exception as exc:
            logger.error(f"Failed to update technique: {exc}", exc_info=True)
            return {
                "error": str(exc),
                "status": "failed",
            }

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
