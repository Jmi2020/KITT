"""
Autonomous project and task management for KITTY.

This module provides project lifecycle management, task scheduling,
and execution orchestration for autonomous workflows.
"""

from brain.projects.manager import ProjectManager
from brain.projects.task_scheduler import TaskScheduler

__all__ = ["ProjectManager", "TaskScheduler"]
