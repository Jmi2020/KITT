"""
Task scheduling and dependency resolution for autonomous projects.

Handles task queue management, dependency resolution via topological sort,
and priority-based execution ordering.
"""

import logging
from collections import defaultdict, deque
from typing import Dict, List, Optional, Set

from common.db.models import Task, TaskPriority, TaskStatus

logger = logging.getLogger(__name__)


class TaskScheduler:
    """
    Manages task execution order based on dependencies and priorities.

    Uses topological sorting for dependency resolution and priority queues
    for execution ordering.
    """

    def __init__(self):
        """Initialize TaskScheduler."""
        pass

    def get_executable_tasks(self, tasks: List[Task]) -> List[Task]:
        """
        Get tasks that can be executed now (dependencies met, not blocked).

        Args:
            tasks: List of all tasks in a project

        Returns:
            List of tasks ready for execution, sorted by priority

        Algorithm:
            1. Build dependency graph
            2. Filter tasks with status=pending
            3. Check if dependencies are completed
            4. Sort by priority (critical > high > medium > low)
        """
        if not tasks:
            return []

        # Build task lookup
        task_map: Dict[str, Task] = {task.id: task for task in tasks}

        # Find pending tasks with no unmet dependencies
        executable = []

        for task in tasks:
            if task.status != TaskStatus.pending:
                continue

            # Check if dependency is met
            if task.depends_on:
                dependency = task_map.get(task.depends_on)
                if not dependency:
                    logger.warning(
                        f"Task {task.id} has invalid dependency {task.depends_on}"
                    )
                    continue
                if dependency.status != TaskStatus.completed:
                    # Dependency not completed yet
                    continue

            # Task is executable
            executable.append(task)

        # Sort by priority (critical=0, high=1, medium=2, low=3)
        priority_order = {
            TaskPriority.critical: 0,
            TaskPriority.high: 1,
            TaskPriority.medium: 2,
            TaskPriority.low: 3,
        }

        executable.sort(key=lambda t: priority_order[t.priority])

        if executable:
            logger.info(
                f"Found {len(executable)} executable tasks "
                f"(highest priority: {executable[0].priority.value})"
            )

        return executable

    def get_execution_order(self, tasks: List[Task]) -> List[Task]:
        """
        Get optimal execution order for all tasks using topological sort.

        Args:
            tasks: List of all tasks

        Returns:
            Tasks in execution order (dependencies first)

        Raises:
            ValueError: If circular dependency detected

        Uses Kahn's algorithm for topological sorting.
        """
        if not tasks:
            return []

        # Build adjacency list and in-degree count
        task_map: Dict[str, Task] = {task.id: task for task in tasks}
        in_degree: Dict[str, int] = defaultdict(int)
        adj_list: Dict[str, List[str]] = defaultdict(list)

        # Initialize in-degree for all tasks
        for task in tasks:
            in_degree[task.id] = 0

        # Build graph: if task B depends_on task A, add edge A → B
        for task in tasks:
            if task.depends_on:
                if task.depends_on not in task_map:
                    logger.warning(
                        f"Task {task.id} has invalid dependency {task.depends_on}, ignoring"
                    )
                    continue
                adj_list[task.depends_on].append(task.id)
                in_degree[task.id] += 1

        # Find tasks with no dependencies (in-degree = 0)
        queue = deque([task_id for task_id in task_map.keys() if in_degree[task_id] == 0])

        # Topological sort using Kahn's algorithm
        sorted_task_ids: List[str] = []

        while queue:
            # Pop task with no dependencies
            task_id = queue.popleft()
            sorted_task_ids.append(task_id)

            # Reduce in-degree for dependent tasks
            for dependent_id in adj_list[task_id]:
                in_degree[dependent_id] -= 1
                if in_degree[dependent_id] == 0:
                    queue.append(dependent_id)

        # Check for circular dependencies
        if len(sorted_task_ids) != len(tasks):
            remaining = set(task_map.keys()) - set(sorted_task_ids)
            raise ValueError(
                f"Circular dependency detected in tasks: {remaining}. "
                "Cannot determine execution order."
            )

        # Convert back to Task objects
        sorted_tasks = [task_map[task_id] for task_id in sorted_task_ids]

        logger.info(f"Determined execution order for {len(sorted_tasks)} tasks")
        return sorted_tasks

    def validate_dependencies(self, tasks: List[Task]) -> Dict[str, List[str]]:
        """
        Validate task dependencies and detect issues.

        Args:
            tasks: List of tasks to validate

        Returns:
            Dictionary of issues: {task_id: [issue1, issue2, ...]}

        Checks for:
        - Invalid dependency references (task doesn't exist)
        - Circular dependencies
        - Self-dependencies
        """
        issues: Dict[str, List[str]] = defaultdict(list)
        task_ids: Set[str] = {task.id for task in tasks}

        for task in tasks:
            # Check self-dependency
            if task.depends_on == task.id:
                issues[task.id].append("Task cannot depend on itself")

            # Check invalid reference
            if task.depends_on and task.depends_on not in task_ids:
                issues[task.id].append(
                    f"Dependency '{task.depends_on}' does not exist"
                )

        # Check circular dependencies by attempting topological sort
        try:
            self.get_execution_order(tasks)
        except ValueError as e:
            # Extract task IDs from error message
            error_msg = str(e)
            if "Circular dependency" in error_msg:
                # Parse remaining task IDs from error
                for task in tasks:
                    if task.id in error_msg:
                        issues[task.id].append("Part of circular dependency")

        return dict(issues)

    def get_next_task(
        self, tasks: List[Task], current_task_id: Optional[str] = None
    ) -> Optional[Task]:
        """
        Get the next task to execute.

        Args:
            tasks: All tasks in the project
            current_task_id: Optional ID of currently executing task

        Returns:
            Next task to execute, or None if no tasks available

        Priority:
            1. Critical priority tasks
            2. High priority tasks
            3. Medium priority tasks
            4. Low priority tasks

        If multiple tasks have same priority, return first in dependency order.
        """
        executable = self.get_executable_tasks(tasks)

        if not executable:
            return None

        # If we have a current task, skip it
        if current_task_id:
            executable = [t for t in executable if t.id != current_task_id]

        if not executable:
            return None

        # Return highest priority task
        next_task = executable[0]
        logger.info(
            f"Selected next task: '{next_task.title}' (priority: {next_task.priority.value})"
        )
        return next_task

    def get_task_statistics(self, tasks: List[Task]) -> dict:
        """
        Get statistics about task states.

        Args:
            tasks: List of tasks

        Returns:
            Dictionary with counts by status and priority.

        Notes:
            - `by_priority` reflects work that is not currently blocked by unmet
              dependencies so operators can focus on actionable tasks.
        """
        stats = {
            "total": len(tasks),
            "by_status": defaultdict(int),
            "by_priority": defaultdict(int),
            "executable": len(self.get_executable_tasks(tasks)),
            "blocked_by_dependencies": 0,
        }

        task_map = {task.id: task for task in tasks}

        for task in tasks:
            stats["by_status"][task.status.value] += 1

            blocked = False
            if task.status == TaskStatus.pending and task.depends_on:
                dependency = task_map.get(task.depends_on)
                if dependency and dependency.status != TaskStatus.completed:
                    stats["blocked_by_dependencies"] += 1
                    blocked = True

            if not blocked:
                stats["by_priority"][task.priority.value] += 1

        # Convert defaultdicts to regular dicts for JSON serialization
        stats["by_status"] = dict(stats["by_status"])
        stats["by_priority"] = dict(stats["by_priority"])

        return stats


# Singleton instance
_scheduler_instance: Optional[TaskScheduler] = None


def get_task_scheduler() -> TaskScheduler:
    """
    Get the singleton TaskScheduler instance.

    Returns:
        TaskScheduler instance
    """
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = TaskScheduler()
    return _scheduler_instance
