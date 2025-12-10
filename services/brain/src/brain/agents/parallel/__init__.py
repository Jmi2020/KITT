"""
Parallel Agent Orchestration System for KITTY.

This package provides high-performance multi-agent orchestration with:
- Parallel task decomposition and execution
- Slot-aware resource management across model endpoints
- Soft tool guidance via agent-specific allowlists
- Automatic fallback to secondary tiers when primary is exhausted
- Idle shutdown and auto-restart for memory management

Components:
- types: Core data types (ModelTier, TaskStatus, KittyTask)
- registry: Agent and endpoint definitions
- slot_manager: Async slot acquisition/release with idle tracking
- llm_adapter: Slot-aware LLM client wrapper
- parallel_manager: Main orchestration logic
- idle_reaper: Background task for shutting down idle servers
- process_manager: Python subprocess control for llama.cpp servers
- integration: BrainOrchestrator integration

Usage:
    from brain.agents.parallel import ParallelTaskManager, KITTY_AGENTS

    manager = ParallelTaskManager(agents=KITTY_AGENTS)
    result = await manager.execute_goal("Research and design a parametric gear")
"""

from .types import ModelTier, TaskStatus, KittyTask, AgentExecutionMetrics
from .registry import KittyAgent, ModelEndpoint, KITTY_AGENTS, ENDPOINTS
from .slot_manager import SlotManager, get_slot_manager
from .parallel_manager import ParallelTaskManager
from .idle_reaper import IdleReaper
from .process_manager import ProcessManager, get_process_manager

__all__ = [
    # Types
    "ModelTier",
    "TaskStatus",
    "KittyTask",
    "AgentExecutionMetrics",
    # Registry
    "KittyAgent",
    "ModelEndpoint",
    "KITTY_AGENTS",
    "ENDPOINTS",
    # Core
    "SlotManager",
    "get_slot_manager",
    "ParallelTaskManager",
    # Memory management
    "IdleReaper",
    "ProcessManager",
    "get_process_manager",
]
