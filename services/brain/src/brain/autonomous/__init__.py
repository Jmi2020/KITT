"""Autonomous operations module for KITTY.

Provides resource management, goal identification, and project execution
for bounded autonomous work.
"""

from .resource_manager import AutonomousWorkload, ResourceManager, ResourceStatus

__all__ = ["ResourceManager", "ResourceStatus", "AutonomousWorkload"]
