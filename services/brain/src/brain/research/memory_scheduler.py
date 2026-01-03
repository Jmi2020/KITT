"""
Memory Mode Scheduler for Research Pipeline

Manages memory allocation and model lifecycle during different research phases.
Handles transitions between IDLE, RESEARCH, COLLECTIVE, and FINETUNE modes.

Mac Studio M3 Ultra Memory Budget:
- Total: 256GB unified memory
- Reserved: ~20GB for OS/Docker
- Available: ~236GB for models

Mode Memory Requirements:
- IDLE: ~8GB (Summary 8B only)
- RESEARCH: ~80GB (GPTOSS 120B + tools)
- COLLECTIVE: ~100GB (Q4 + GPTOSS 120B)
- FINETUNE: ~200GB (mlx-lm training, all LLMs unloaded)
"""

import asyncio
import subprocess
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any
import json

logger = logging.getLogger(__name__)


class ResearchMemoryMode(str, Enum):
    """Memory mode states for research pipeline."""
    IDLE = "idle"           # Minimal memory usage
    RESEARCH = "research"   # Paper harvesting and extraction
    COLLECTIVE = "collective"  # Multi-agent evaluation
    FINETUNE = "finetune"   # QLoRA training


@dataclass
class MemoryModeState:
    """Current state of memory mode."""
    mode: ResearchMemoryMode
    checkpoint_id: Optional[str] = None
    entered_at: Optional[datetime] = None
    models_loaded: List[str] = field(default_factory=list)
    memory_used_gb: float = 0.0
    memory_available_gb: float = 0.0
    transition_notes: str = ""


@dataclass
class ModeRequirements:
    """Memory and model requirements for a mode."""
    min_memory_gb: float
    required_models: List[str]
    models_to_unload: List[str]
    description: str


# Mode configurations
MODE_REQUIREMENTS: Dict[ResearchMemoryMode, ModeRequirements] = {
    ResearchMemoryMode.IDLE: ModeRequirements(
        min_memory_gb=8.0,
        required_models=["kitty-summary"],
        models_to_unload=["gptoss-120b", "kitty-q4", "kitty-coder", "kitty-vision"],
        description="Idle mode with minimal memory usage",
    ),
    ResearchMemoryMode.RESEARCH: ModeRequirements(
        min_memory_gb=90.0,
        required_models=["gptoss-120b", "kitty-summary"],
        models_to_unload=["kitty-coder"],
        description="Research mode for paper harvesting with GPTOSS 120B",
    ),
    ResearchMemoryMode.COLLECTIVE: ModeRequirements(
        min_memory_gb=110.0,
        required_models=["gptoss-120b", "kitty-q4", "kitty-summary"],
        models_to_unload=["kitty-coder"],
        description="Collective evaluation with Q4 + GPTOSS 120B",
    ),
    ResearchMemoryMode.FINETUNE: ModeRequirements(
        min_memory_gb=200.0,
        required_models=[],  # No LLMs needed during training
        models_to_unload=["gptoss-120b", "kitty-q4", "kitty-coder", "kitty-vision", "kitty-summary"],
        description="Fine-tuning mode - all LLMs unloaded for mlx-lm",
    ),
}


class MemoryModeScheduler:
    """
    Manages memory mode transitions for research pipeline.

    Handles:
    - Memory availability checks via macOS vm_stat
    - Model loading/unloading coordination
    - Checkpoint persistence for recovery
    - Mode transition validation
    """

    def __init__(
        self,
        project_root: str = "/Users/Shared/Coding/KITT",
        checkpoint_dir: Optional[str] = None,
    ):
        self.project_root = project_root
        self.checkpoint_dir = checkpoint_dir or os.path.join(
            project_root, ".research_data", "checkpoints"
        )
        self._current_state = MemoryModeState(mode=ResearchMemoryMode.IDLE)
        self._mode_lock = asyncio.Lock()

        # Ensure checkpoint directory exists
        os.makedirs(self.checkpoint_dir, exist_ok=True)

    @property
    def current_mode(self) -> ResearchMemoryMode:
        return self._current_state.mode

    @property
    def current_state(self) -> MemoryModeState:
        return self._current_state

    async def get_memory_stats(self) -> Dict[str, float]:
        """Get current memory statistics using macOS vm_stat."""
        try:
            result = subprocess.run(
                ["vm_stat"],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode != 0:
                logger.warning("vm_stat failed, using fallback")
                return self._get_fallback_memory_stats()

            # Parse vm_stat output
            lines = result.stdout.strip().split("\n")
            stats = {}

            for line in lines[1:]:  # Skip header
                if ":" in line:
                    key, value = line.split(":", 1)
                    # Remove trailing period and convert to int
                    value = value.strip().rstrip(".")
                    try:
                        stats[key.strip()] = int(value)
                    except ValueError:
                        continue

            # Calculate memory in GB
            # vm_stat reports in pages (typically 16384 bytes on M3)
            page_size = 16384  # Apple Silicon page size

            free_pages = stats.get("Pages free", 0)
            inactive_pages = stats.get("Pages inactive", 0)
            speculative_pages = stats.get("Pages speculative", 0)
            purgeable_pages = stats.get("Pages purgeable", 0)

            # Available memory = free + inactive + speculative + purgeable
            available_pages = free_pages + inactive_pages + speculative_pages + purgeable_pages
            available_gb = (available_pages * page_size) / (1024 ** 3)

            # Total physical memory
            total_gb = 256.0  # M3 Ultra
            used_gb = total_gb - available_gb

            return {
                "total_gb": total_gb,
                "available_gb": round(available_gb, 2),
                "used_gb": round(used_gb, 2),
                "free_pages": free_pages,
            }

        except Exception as e:
            logger.error(f"Failed to get memory stats: {e}")
            return self._get_fallback_memory_stats()

    def _get_fallback_memory_stats(self) -> Dict[str, float]:
        """Fallback memory stats when vm_stat fails."""
        return {
            "total_gb": 256.0,
            "available_gb": 200.0,  # Conservative estimate
            "used_gb": 56.0,
            "free_pages": 0,
        }

    async def can_enter_mode(self, target_mode: ResearchMemoryMode) -> tuple[bool, str]:
        """
        Check if we can safely enter the target mode.

        Returns:
            Tuple of (can_enter, reason)
        """
        requirements = MODE_REQUIREMENTS[target_mode]
        memory_stats = await self.get_memory_stats()

        available_gb = memory_stats["available_gb"]

        # Check if we have enough memory
        if available_gb < requirements.min_memory_gb:
            return (
                False,
                f"Insufficient memory: need {requirements.min_memory_gb}GB, "
                f"have {available_gb}GB available"
            )

        return (True, f"Memory OK: {available_gb}GB available")

    async def enter_mode(
        self,
        target_mode: ResearchMemoryMode,
        checkpoint_id: Optional[str] = None,
        force: bool = False,
    ) -> MemoryModeState:
        """
        Transition to a new memory mode.

        Args:
            target_mode: The mode to enter
            checkpoint_id: Optional checkpoint to associate with this mode
            force: Force transition even if memory check fails

        Returns:
            New MemoryModeState after transition
        """
        async with self._mode_lock:
            current_mode = self._current_state.mode

            if current_mode == target_mode:
                logger.info(f"Already in {target_mode.value} mode")
                return self._current_state

            logger.info(f"Transitioning from {current_mode.value} to {target_mode.value}")

            # Check if transition is safe
            can_enter, reason = await self.can_enter_mode(target_mode)
            if not can_enter and not force:
                raise MemoryModeError(
                    f"Cannot enter {target_mode.value} mode: {reason}"
                )

            requirements = MODE_REQUIREMENTS[target_mode]

            # Step 1: Unload models that shouldn't be running in target mode
            for model in requirements.models_to_unload:
                await self._unload_model(model)

            # Wait for memory to be released
            await asyncio.sleep(5)

            # Step 2: Load required models for target mode
            loaded_models = []
            for model in requirements.required_models:
                success = await self._load_model(model)
                if success:
                    loaded_models.append(model)

            # Get updated memory stats
            memory_stats = await self.get_memory_stats()

            # Update state
            self._current_state = MemoryModeState(
                mode=target_mode,
                checkpoint_id=checkpoint_id,
                entered_at=datetime.utcnow(),
                models_loaded=loaded_models,
                memory_used_gb=memory_stats["used_gb"],
                memory_available_gb=memory_stats["available_gb"],
                transition_notes=reason,
            )

            # Save checkpoint
            await self._save_checkpoint()

            logger.info(
                f"Entered {target_mode.value} mode. "
                f"Models: {loaded_models}, Memory: {memory_stats['available_gb']}GB available"
            )

            return self._current_state

    async def enter_research_mode(
        self,
        checkpoint_id: Optional[str] = None,
    ) -> MemoryModeState:
        """Enter research mode for paper harvesting."""
        return await self.enter_mode(
            ResearchMemoryMode.RESEARCH,
            checkpoint_id=checkpoint_id,
        )

    async def enter_collective_mode(
        self,
        checkpoint_id: Optional[str] = None,
    ) -> MemoryModeState:
        """Enter collective mode for multi-agent evaluation."""
        return await self.enter_mode(
            ResearchMemoryMode.COLLECTIVE,
            checkpoint_id=checkpoint_id,
        )

    async def enter_finetune_mode(
        self,
        checkpoint_id: Optional[str] = None,
    ) -> MemoryModeState:
        """Enter fine-tune mode for QLoRA training."""
        return await self.enter_mode(
            ResearchMemoryMode.FINETUNE,
            checkpoint_id=checkpoint_id,
        )

    async def enter_idle_mode(self) -> MemoryModeState:
        """Return to idle mode with minimal memory usage."""
        return await self.enter_mode(ResearchMemoryMode.IDLE)

    async def _load_model(self, model_id: str) -> bool:
        """
        Load a model by ID.

        Handles both Ollama models (gptoss-120b) and llama.cpp servers.
        """
        try:
            if model_id == "gptoss-120b":
                return await self._load_ollama_model("gptoss-120b")
            elif model_id.startswith("kitty-"):
                return await self._start_llama_server(model_id)
            else:
                logger.warning(f"Unknown model: {model_id}")
                return False
        except Exception as e:
            logger.error(f"Failed to load model {model_id}: {e}")
            return False

    async def _unload_model(self, model_id: str) -> bool:
        """
        Unload a model by ID.
        """
        try:
            if model_id == "gptoss-120b":
                return await self._unload_ollama_model("gptoss-120b")
            elif model_id.startswith("kitty-"):
                return await self._stop_llama_server(model_id)
            else:
                logger.warning(f"Unknown model: {model_id}")
                return False
        except Exception as e:
            logger.error(f"Failed to unload model {model_id}: {e}")
            return False

    async def _load_ollama_model(self, model_name: str) -> bool:
        """Load a model via Ollama."""
        try:
            # Use ollama pull/load to ensure model is ready
            result = subprocess.run(
                ["ollama", "run", model_name, "--keepalive", "0"],
                capture_output=True,
                text=True,
                timeout=300,  # 5 minutes for large model
                input="exit\n",  # Send exit to close the session
            )
            return result.returncode == 0
        except subprocess.TimeoutExpired:
            logger.warning(f"Ollama load timed out for {model_name}")
            return False
        except FileNotFoundError:
            logger.warning("Ollama not found")
            return False

    async def _unload_ollama_model(self, model_name: str) -> bool:
        """Unload a model from Ollama."""
        try:
            # Ollama doesn't have explicit unload, but we can stop it
            result = subprocess.run(
                ["ollama", "stop", model_name],
                capture_output=True,
                text=True,
                timeout=30,
            )
            return True  # Even if stop fails, we tried
        except Exception:
            return True  # Model may already be unloaded

    async def _start_llama_server(self, server_name: str) -> bool:
        """Start a specific llama.cpp server."""
        # Map server names to start script behavior
        # The start.sh script handles all servers
        script_path = os.path.join(
            self.project_root, "ops", "scripts", "llama", "start.sh"
        )

        try:
            result = subprocess.run(
                [script_path],
                capture_output=True,
                text=True,
                timeout=120,
                cwd=self.project_root,
            )
            return result.returncode == 0
        except Exception as e:
            logger.error(f"Failed to start llama server: {e}")
            return False

    async def _stop_llama_server(self, server_name: str) -> bool:
        """Stop all llama.cpp servers."""
        script_path = os.path.join(
            self.project_root, "ops", "scripts", "llama", "stop.sh"
        )

        try:
            result = subprocess.run(
                [script_path],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=self.project_root,
            )
            return result.returncode == 0
        except Exception as e:
            logger.error(f"Failed to stop llama server: {e}")
            return False

    async def _save_checkpoint(self) -> None:
        """Save current state to checkpoint file."""
        checkpoint_path = os.path.join(
            self.checkpoint_dir,
            "memory_mode_state.json"
        )

        state_dict = {
            "mode": self._current_state.mode.value,
            "checkpoint_id": self._current_state.checkpoint_id,
            "entered_at": self._current_state.entered_at.isoformat()
                if self._current_state.entered_at else None,
            "models_loaded": self._current_state.models_loaded,
            "memory_used_gb": self._current_state.memory_used_gb,
            "memory_available_gb": self._current_state.memory_available_gb,
        }

        with open(checkpoint_path, "w") as f:
            json.dump(state_dict, f, indent=2)

        logger.debug(f"Saved memory mode checkpoint: {checkpoint_path}")

    async def restore_from_checkpoint(self) -> Optional[MemoryModeState]:
        """Restore state from checkpoint file."""
        checkpoint_path = os.path.join(
            self.checkpoint_dir,
            "memory_mode_state.json"
        )

        if not os.path.exists(checkpoint_path):
            return None

        try:
            with open(checkpoint_path, "r") as f:
                state_dict = json.load(f)

            mode = ResearchMemoryMode(state_dict["mode"])
            entered_at = None
            if state_dict.get("entered_at"):
                entered_at = datetime.fromisoformat(state_dict["entered_at"])

            self._current_state = MemoryModeState(
                mode=mode,
                checkpoint_id=state_dict.get("checkpoint_id"),
                entered_at=entered_at,
                models_loaded=state_dict.get("models_loaded", []),
                memory_used_gb=state_dict.get("memory_used_gb", 0.0),
                memory_available_gb=state_dict.get("memory_available_gb", 0.0),
            )

            logger.info(f"Restored memory mode state: {mode.value}")
            return self._current_state

        except Exception as e:
            logger.error(f"Failed to restore checkpoint: {e}")
            return None


class MemoryModeError(Exception):
    """Exception raised when memory mode transition fails."""
    pass


# Global scheduler instance
_scheduler: Optional[MemoryModeScheduler] = None


def get_memory_scheduler() -> MemoryModeScheduler:
    """Get or create the global memory scheduler."""
    global _scheduler
    if _scheduler is None:
        _scheduler = MemoryModeScheduler()
    return _scheduler


async def initialize_memory_scheduler(
    project_root: str = "/Users/Shared/Coding/KITT",
) -> MemoryModeScheduler:
    """Initialize the global memory scheduler and restore state."""
    global _scheduler
    _scheduler = MemoryModeScheduler(project_root=project_root)
    await _scheduler.restore_from_checkpoint()
    return _scheduler
