"""
Model Lifecycle Manager for Research Pipeline

Provides fine-grained control over loading and unloading individual models
for research, evaluation, and fine-tuning workflows.

Supports:
- Ollama models (GPTOSS 120B, etc.)
- llama.cpp servers (Q4, Summary, Vision, Coder)
- Memory monitoring and budgeting
"""

import asyncio
import subprocess
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any
import httpx

logger = logging.getLogger(__name__)


class ModelProvider(str, Enum):
    """Model provider types."""
    OLLAMA = "ollama"
    LLAMA_CPP = "llama_cpp"
    MLX = "mlx"


class ModelStatus(str, Enum):
    """Current status of a model."""
    UNLOADED = "unloaded"
    LOADING = "loading"
    LOADED = "loaded"
    ERROR = "error"
    UNKNOWN = "unknown"


@dataclass
class ModelInfo:
    """Information about a registered model."""
    model_id: str
    provider: ModelProvider
    display_name: str
    memory_gb: float  # Estimated memory usage
    port: Optional[int] = None  # For llama.cpp servers
    alias: Optional[str] = None  # Model alias
    context_size: int = 4096
    capabilities: List[str] = None  # e.g., ["reasoning", "coding", "vision"]

    def __post_init__(self):
        if self.capabilities is None:
            self.capabilities = []


@dataclass
class ModelState:
    """Current state of a model."""
    model_id: str
    status: ModelStatus
    loaded_at: Optional[datetime] = None
    memory_used_gb: float = 0.0
    error_message: Optional[str] = None
    health_check_url: Optional[str] = None


# Known models registry
KNOWN_MODELS: Dict[str, ModelInfo] = {
    # Ollama models
    "gptoss-120b": ModelInfo(
        model_id="gptoss-120b",
        provider=ModelProvider.OLLAMA,
        display_name="GPTOSS 120B",
        memory_gb=75.0,
        context_size=32768,
        capabilities=["reasoning", "thinking"],
    ),

    # llama.cpp models
    "kitty-q4": ModelInfo(
        model_id="kitty-q4",
        provider=ModelProvider.LLAMA_CPP,
        display_name="Athene V2 Q4 (Tool Orchestrator)",
        memory_gb=20.0,
        port=8083,
        alias="kitty-q4",
        context_size=131072,
        capabilities=["reasoning", "tools"],
    ),
    "kitty-summary": ModelInfo(
        model_id="kitty-summary",
        provider=ModelProvider.LLAMA_CPP,
        display_name="Hermes 3 8B (Summarizer)",
        memory_gb=5.0,
        port=8084,
        alias="kitty-summary",
        context_size=4096,
        capabilities=["summarization"],
    ),
    "kitty-vision": ModelInfo(
        model_id="kitty-vision",
        provider=ModelProvider.LLAMA_CPP,
        display_name="Llama 3.2 11B Vision",
        memory_gb=8.0,
        port=8085,
        alias="kitty-vision",
        context_size=4096,
        capabilities=["vision", "multimodal"],
    ),
    "kitty-coder": ModelInfo(
        model_id="kitty-coder",
        provider=ModelProvider.LLAMA_CPP,
        display_name="Qwen 2.5 Coder 32B",
        memory_gb=35.0,
        port=8087,
        alias="kitty-coder",
        context_size=16384,
        capabilities=["coding"],
    ),
}


class ModelLifecycleManager:
    """
    Manages loading and unloading of models across providers.

    Provides unified interface for:
    - Listing loaded models
    - Loading models on demand
    - Unloading models to free memory
    - Health checking
    """

    def __init__(
        self,
        project_root: str = "/Users/Shared/Coding/KITT",
        ollama_url: str = "http://localhost:11434",
    ):
        self.project_root = project_root
        self.ollama_url = ollama_url
        self._model_states: Dict[str, ModelState] = {}
        self._lock = asyncio.Lock()

    async def list_loaded_models(self) -> List[ModelState]:
        """
        List all currently loaded models across providers.

        Returns:
            List of ModelState for loaded models
        """
        loaded = []

        # Check Ollama models
        ollama_models = await self._list_ollama_models()
        for model_name in ollama_models:
            info = KNOWN_MODELS.get(model_name)
            state = ModelState(
                model_id=model_name,
                status=ModelStatus.LOADED,
                memory_used_gb=info.memory_gb if info else 0.0,
                health_check_url=f"{self.ollama_url}/api/show",
            )
            loaded.append(state)
            self._model_states[model_name] = state

        # Check llama.cpp servers
        for model_id, info in KNOWN_MODELS.items():
            if info.provider == ModelProvider.LLAMA_CPP and info.port:
                is_running = await self._check_llama_server(info.port)
                if is_running:
                    state = ModelState(
                        model_id=model_id,
                        status=ModelStatus.LOADED,
                        memory_used_gb=info.memory_gb,
                        health_check_url=f"http://localhost:{info.port}/health",
                    )
                    loaded.append(state)
                    self._model_states[model_id] = state

        return loaded

    async def get_model_status(self, model_id: str) -> ModelState:
        """
        Get current status of a specific model.

        Args:
            model_id: Model identifier

        Returns:
            ModelState with current status
        """
        info = KNOWN_MODELS.get(model_id)
        if not info:
            return ModelState(
                model_id=model_id,
                status=ModelStatus.UNKNOWN,
                error_message=f"Unknown model: {model_id}",
            )

        if info.provider == ModelProvider.OLLAMA:
            ollama_models = await self._list_ollama_models()
            if model_id in ollama_models:
                return ModelState(
                    model_id=model_id,
                    status=ModelStatus.LOADED,
                    memory_used_gb=info.memory_gb,
                )
            else:
                return ModelState(
                    model_id=model_id,
                    status=ModelStatus.UNLOADED,
                )

        elif info.provider == ModelProvider.LLAMA_CPP and info.port:
            is_running = await self._check_llama_server(info.port)
            if is_running:
                return ModelState(
                    model_id=model_id,
                    status=ModelStatus.LOADED,
                    memory_used_gb=info.memory_gb,
                )
            else:
                return ModelState(
                    model_id=model_id,
                    status=ModelStatus.UNLOADED,
                )

        return ModelState(
            model_id=model_id,
            status=ModelStatus.UNKNOWN,
        )

    async def load_model(
        self,
        model_id: str,
        provider: Optional[ModelProvider] = None,
        timeout: float = 300.0,
    ) -> ModelState:
        """
        Load a model by ID.

        Args:
            model_id: Model identifier
            provider: Optional provider hint
            timeout: Maximum time to wait for model to load

        Returns:
            ModelState after loading attempt
        """
        async with self._lock:
            info = KNOWN_MODELS.get(model_id)

            if info:
                provider = info.provider
            elif not provider:
                return ModelState(
                    model_id=model_id,
                    status=ModelStatus.ERROR,
                    error_message=f"Unknown model and no provider specified: {model_id}",
                )

            # Update state to loading
            self._model_states[model_id] = ModelState(
                model_id=model_id,
                status=ModelStatus.LOADING,
            )

            try:
                if provider == ModelProvider.OLLAMA:
                    success = await self._load_ollama_model(model_id, timeout)
                elif provider == ModelProvider.LLAMA_CPP:
                    success = await self._start_llama_servers()
                else:
                    success = False

                if success:
                    state = ModelState(
                        model_id=model_id,
                        status=ModelStatus.LOADED,
                        loaded_at=datetime.utcnow(),
                        memory_used_gb=info.memory_gb if info else 0.0,
                    )
                else:
                    state = ModelState(
                        model_id=model_id,
                        status=ModelStatus.ERROR,
                        error_message="Failed to load model",
                    )

                self._model_states[model_id] = state
                return state

            except Exception as e:
                state = ModelState(
                    model_id=model_id,
                    status=ModelStatus.ERROR,
                    error_message=str(e),
                )
                self._model_states[model_id] = state
                return state

    async def unload_model(self, model_id: str) -> ModelState:
        """
        Unload a model to free memory.

        Args:
            model_id: Model identifier

        Returns:
            ModelState after unloading
        """
        async with self._lock:
            info = KNOWN_MODELS.get(model_id)

            if not info:
                return ModelState(
                    model_id=model_id,
                    status=ModelStatus.UNKNOWN,
                    error_message=f"Unknown model: {model_id}",
                )

            try:
                if info.provider == ModelProvider.OLLAMA:
                    success = await self._unload_ollama_model(model_id)
                elif info.provider == ModelProvider.LLAMA_CPP:
                    # Stop all llama.cpp servers (they start/stop together)
                    success = await self._stop_llama_servers()
                else:
                    success = False

                if success:
                    state = ModelState(
                        model_id=model_id,
                        status=ModelStatus.UNLOADED,
                    )
                else:
                    state = ModelState(
                        model_id=model_id,
                        status=ModelStatus.ERROR,
                        error_message="Failed to unload model",
                    )

                self._model_states[model_id] = state
                return state

            except Exception as e:
                state = ModelState(
                    model_id=model_id,
                    status=ModelStatus.ERROR,
                    error_message=str(e),
                )
                self._model_states[model_id] = state
                return state

    async def unload_all_models(self) -> List[ModelState]:
        """
        Unload all models to free maximum memory.

        Returns:
            List of ModelState after unloading
        """
        results = []

        # Get currently loaded models
        loaded = await self.list_loaded_models()

        # Unload each
        for model_state in loaded:
            result = await self.unload_model(model_state.model_id)
            results.append(result)

        # Also stop llama.cpp servers explicitly
        await self._stop_llama_servers()

        # Wait for memory to be released
        await asyncio.sleep(5)

        return results

    async def health_check(self, model_id: str) -> bool:
        """
        Check if a model is healthy and responding.

        Args:
            model_id: Model identifier

        Returns:
            True if healthy, False otherwise
        """
        info = KNOWN_MODELS.get(model_id)
        if not info:
            return False

        if info.provider == ModelProvider.LLAMA_CPP and info.port:
            return await self._check_llama_server(info.port)
        elif info.provider == ModelProvider.OLLAMA:
            ollama_models = await self._list_ollama_models()
            return model_id in ollama_models

        return False

    async def get_total_memory_usage(self) -> float:
        """
        Calculate total memory usage of loaded models.

        Returns:
            Total memory in GB
        """
        loaded = await self.list_loaded_models()
        total = sum(s.memory_used_gb for s in loaded)
        return round(total, 2)

    # ==========================================
    # Provider-specific implementations
    # ==========================================

    async def _list_ollama_models(self) -> List[str]:
        """List models currently loaded in Ollama."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.ollama_url}/api/tags")
                if response.status_code == 200:
                    data = response.json()
                    return [m["name"] for m in data.get("models", [])]
        except Exception as e:
            logger.debug(f"Failed to list Ollama models: {e}")
        return []

    async def _load_ollama_model(self, model_name: str, timeout: float) -> bool:
        """Load a model in Ollama."""
        try:
            # Use ollama CLI to load model
            result = subprocess.run(
                ["ollama", "pull", model_name],
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            if result.returncode != 0:
                logger.error(f"Ollama pull failed: {result.stderr}")
                return False

            # Run briefly to ensure it's loaded
            result = subprocess.run(
                ["ollama", "run", model_name, "--keepalive", "0"],
                capture_output=True,
                text=True,
                timeout=60,
                input="exit\n",
            )

            return True

        except subprocess.TimeoutExpired:
            logger.error(f"Ollama load timed out for {model_name}")
            return False
        except FileNotFoundError:
            logger.error("Ollama not found in PATH")
            return False
        except Exception as e:
            logger.error(f"Failed to load Ollama model: {e}")
            return False

    async def _unload_ollama_model(self, model_name: str) -> bool:
        """Unload a model from Ollama."""
        try:
            result = subprocess.run(
                ["ollama", "stop", model_name],
                capture_output=True,
                text=True,
                timeout=30,
            )
            return True
        except Exception as e:
            logger.debug(f"Ollama stop may have failed: {e}")
            return True  # Model may not have been running

    async def _check_llama_server(self, port: int) -> bool:
        """Check if a llama.cpp server is running on the given port."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"http://localhost:{port}/health")
                return response.status_code == 200
        except Exception:
            return False

    async def _start_llama_servers(self) -> bool:
        """Start all llama.cpp servers via start.sh."""
        script_path = os.path.join(
            self.project_root, "ops", "scripts", "llama", "start.sh"
        )

        try:
            result = subprocess.run(
                [script_path],
                capture_output=True,
                text=True,
                timeout=180,  # 3 minutes for model loading
                cwd=self.project_root,
            )
            return result.returncode == 0
        except Exception as e:
            logger.error(f"Failed to start llama servers: {e}")
            return False

    async def _stop_llama_servers(self) -> bool:
        """Stop all llama.cpp servers via stop.sh."""
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
            logger.error(f"Failed to stop llama servers: {e}")
            return False


# Global instance
_manager: Optional[ModelLifecycleManager] = None


def get_model_lifecycle_manager() -> ModelLifecycleManager:
    """Get or create the global model lifecycle manager."""
    global _manager
    if _manager is None:
        _manager = ModelLifecycleManager()
    return _manager


async def initialize_model_lifecycle_manager(
    project_root: str = "/Users/Shared/Coding/KITT",
) -> ModelLifecycleManager:
    """Initialize the global model lifecycle manager."""
    global _manager
    _manager = ModelLifecycleManager(project_root=project_root)
    return _manager
