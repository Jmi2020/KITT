"""
Fine-Tuning Pipeline for Dataset Generation

Implements QLoRA fine-tuning using mlx-lm on Apple Silicon.
Creates domain expert models from accumulated training data.

Pipeline Steps:
1. Export dataset to Alpaca JSON format
2. Validate minimum sample count (5000+ recommended)
3. Run mlx-lm QLoRA training
4. Fuse adapter with base model
5. Export to GGUF (optional)
6. Register in expert registry
"""

import asyncio
import json
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any
import uuid

from .extraction_schemas import DatasetEntry, export_entries_to_alpaca

logger = logging.getLogger(__name__)


class FinetuneStatus(str, Enum):
    """Status of a fine-tuning job."""
    PENDING = "pending"
    VALIDATING = "validating"
    TRAINING = "training"
    FUSING = "fusing"
    EXPORTING = "exporting"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class FinetuneConfig:
    """Configuration for fine-tuning job."""
    topic_id: str
    topic_name: str
    base_model: str = "mlx-community/Llama-3.2-8B-Instruct-4bit"
    lora_rank: int = 16
    lora_alpha: int = 32
    batch_size: int = 4
    epochs: int = 3
    learning_rate: float = 1e-4
    warmup_steps: int = 100
    max_seq_length: int = 2048
    gradient_accumulation_steps: int = 4
    export_gguf: bool = True
    min_samples: int = 5000


@dataclass
class FinetuneMetrics:
    """Training metrics from fine-tuning."""
    final_loss: float = 0.0
    best_loss: float = 0.0
    epochs_completed: int = 0
    total_steps: int = 0
    training_time_seconds: float = 0.0
    samples_used: int = 0
    tokens_per_second: float = 0.0


@dataclass
class FinetuneResult:
    """Result of a fine-tuning job."""
    job_id: str
    status: FinetuneStatus
    topic_id: str
    topic_name: str
    base_model: str
    adapter_path: Optional[str] = None
    fused_model_path: Optional[str] = None
    gguf_path: Optional[str] = None
    metrics: Optional[FinetuneMetrics] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class FinetunePipeline:
    """
    Fine-tuning pipeline using mlx-lm for QLoRA training.

    Features:
    - Automatic dataset validation
    - QLoRA training with configurable hyperparameters
    - Adapter fusion with base model
    - GGUF export for llama.cpp deployment
    - Progress tracking and checkpointing
    """

    def __init__(
        self,
        models_dir: str = "/Users/Shared/Coding/KITT/.expert_models",
        data_dir: str = "/Users/Shared/Coding/KITT/.research_data",
        mlx_cache_dir: str = "/Users/Shared/Coding/KITT/.mlx_cache",
    ):
        self.models_dir = Path(models_dir)
        self.data_dir = Path(data_dir)
        self.mlx_cache_dir = Path(mlx_cache_dir)

        # Ensure directories exist
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.mlx_cache_dir.mkdir(parents=True, exist_ok=True)

        # Track active jobs
        self._active_jobs: Dict[str, FinetuneResult] = {}

    async def run_finetune(
        self,
        config: FinetuneConfig,
        entries: List[DatasetEntry],
    ) -> FinetuneResult:
        """
        Run the complete fine-tuning pipeline.

        Args:
            config: Fine-tuning configuration
            entries: Dataset entries for training

        Returns:
            FinetuneResult with status and paths
        """
        job_id = uuid.uuid4().hex[:12]
        logger.info(f"Starting fine-tune job {job_id} for topic: {config.topic_name}")

        result = FinetuneResult(
            job_id=job_id,
            status=FinetuneStatus.PENDING,
            topic_id=config.topic_id,
            topic_name=config.topic_name,
            base_model=config.base_model,
            started_at=datetime.utcnow(),
        )
        self._active_jobs[job_id] = result

        try:
            # Step 1: Validate dataset
            result.status = FinetuneStatus.VALIDATING
            if len(entries) < config.min_samples:
                raise ValueError(
                    f"Insufficient samples: {len(entries)} < {config.min_samples} required"
                )
            logger.info(f"Dataset validated: {len(entries)} samples")

            # Step 2: Export dataset
            dataset_path = self._export_dataset(job_id, entries)
            logger.info(f"Dataset exported to: {dataset_path}")

            # Step 3: Run training
            result.status = FinetuneStatus.TRAINING
            adapter_path, metrics = await self._run_training(
                job_id, config, dataset_path
            )
            result.adapter_path = str(adapter_path)
            result.metrics = metrics
            logger.info(f"Training completed. Loss: {metrics.final_loss:.4f}")

            # Step 4: Fuse adapter
            result.status = FinetuneStatus.FUSING
            fused_path = await self._fuse_adapter(job_id, config, adapter_path)
            result.fused_model_path = str(fused_path)
            logger.info(f"Adapter fused to: {fused_path}")

            # Step 5: Export to GGUF (optional)
            if config.export_gguf:
                result.status = FinetuneStatus.EXPORTING
                gguf_path = await self._export_gguf(job_id, config, fused_path)
                result.gguf_path = str(gguf_path) if gguf_path else None
                logger.info(f"GGUF exported to: {gguf_path}")

            result.status = FinetuneStatus.COMPLETED
            result.completed_at = datetime.utcnow()

            logger.info(f"Fine-tune job {job_id} completed successfully")
            return result

        except Exception as e:
            logger.error(f"Fine-tune job {job_id} failed: {e}")
            result.status = FinetuneStatus.FAILED
            result.error_message = str(e)
            result.completed_at = datetime.utcnow()
            return result

    def _export_dataset(
        self,
        job_id: str,
        entries: List[DatasetEntry],
    ) -> Path:
        """Export dataset to Alpaca JSON format."""
        dataset_dir = self.data_dir / "datasets" / job_id
        dataset_dir.mkdir(parents=True, exist_ok=True)

        # Split into train/val
        val_size = max(100, int(len(entries) * 0.1))
        train_entries = entries[:-val_size]
        val_entries = entries[-val_size:]

        train_path = dataset_dir / "train.json"
        val_path = dataset_dir / "valid.json"

        export_entries_to_alpaca(train_entries, str(train_path))
        export_entries_to_alpaca(val_entries, str(val_path))

        return dataset_dir

    async def _run_training(
        self,
        job_id: str,
        config: FinetuneConfig,
        dataset_path: Path,
    ) -> tuple[Path, FinetuneMetrics]:
        """Run mlx-lm training."""
        adapter_path = self.models_dir / "adapters" / job_id
        adapter_path.mkdir(parents=True, exist_ok=True)

        # Build mlx_lm.lora command
        cmd = [
            "python", "-m", "mlx_lm.lora",
            "--model", config.base_model,
            "--train",
            "--data", str(dataset_path),
            "--adapter-path", str(adapter_path),
            "--batch-size", str(config.batch_size),
            "--lora-rank", str(config.lora_rank),
            "--lora-alpha", str(config.lora_alpha),
            "--learning-rate", str(config.learning_rate),
            "--iters", str(config.epochs * 1000),  # Approximate iterations
            "--steps-per-report", "50",
            "--steps-per-eval", "200",
            "--val-batches", "20",
            "--grad-checkpoint",
        ]

        start_time = datetime.utcnow()

        try:
            # Run training process
            logger.info(f"Running mlx_lm.lora: {' '.join(cmd)}")

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ, "MLX_CACHE_DIR": str(self.mlx_cache_dir)},
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                raise RuntimeError(f"Training failed: {stderr.decode()}")

            # Parse metrics from output
            metrics = self._parse_training_output(stdout.decode())
            metrics.training_time_seconds = (
                datetime.utcnow() - start_time
            ).total_seconds()

            return adapter_path, metrics

        except FileNotFoundError:
            raise RuntimeError("mlx_lm not found. Install with: pip install mlx-lm")

    def _parse_training_output(self, output: str) -> FinetuneMetrics:
        """Parse training metrics from mlx_lm output."""
        metrics = FinetuneMetrics()

        # Try to extract loss values from output
        import re

        # Look for final loss pattern
        loss_matches = re.findall(r"Loss[:\s]+([0-9.]+)", output)
        if loss_matches:
            metrics.final_loss = float(loss_matches[-1])
            metrics.best_loss = min(float(l) for l in loss_matches)

        # Look for step count
        step_matches = re.findall(r"[Ss]tep[:\s]+(\d+)", output)
        if step_matches:
            metrics.total_steps = int(step_matches[-1])

        return metrics

    async def _fuse_adapter(
        self,
        job_id: str,
        config: FinetuneConfig,
        adapter_path: Path,
    ) -> Path:
        """Fuse LoRA adapter with base model."""
        fused_path = self.models_dir / "fused" / job_id
        fused_path.mkdir(parents=True, exist_ok=True)

        cmd = [
            "python", "-m", "mlx_lm.fuse",
            "--model", config.base_model,
            "--adapter-path", str(adapter_path),
            "--save-path", str(fused_path),
        ]

        try:
            logger.info(f"Fusing adapter: {' '.join(cmd)}")

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ, "MLX_CACHE_DIR": str(self.mlx_cache_dir)},
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                raise RuntimeError(f"Fusion failed: {stderr.decode()}")

            return fused_path

        except FileNotFoundError:
            raise RuntimeError("mlx_lm not found")

    async def _export_gguf(
        self,
        job_id: str,
        config: FinetuneConfig,
        fused_path: Path,
    ) -> Optional[Path]:
        """Export fused model to GGUF format."""
        gguf_path = self.models_dir / "gguf" / f"{job_id}.gguf"
        gguf_path.parent.mkdir(parents=True, exist_ok=True)

        # Find llama.cpp convert script
        convert_script = shutil.which("llama-convert-hf-to-gguf")

        if not convert_script:
            # Try common locations
            possible_paths = [
                "/opt/homebrew/bin/llama-convert-hf-to-gguf",
                Path.home() / "llama.cpp" / "convert-hf-to-gguf.py",
            ]
            for path in possible_paths:
                if Path(path).exists():
                    convert_script = str(path)
                    break

        if not convert_script:
            logger.warning("GGUF conversion script not found, skipping export")
            return None

        try:
            cmd = [convert_script, str(fused_path), "--outfile", str(gguf_path)]

            logger.info(f"Converting to GGUF: {' '.join(cmd)}")

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                logger.warning(f"GGUF export failed: {stderr.decode()}")
                return None

            return gguf_path

        except Exception as e:
            logger.warning(f"GGUF export failed: {e}")
            return None

    def get_job_status(self, job_id: str) -> Optional[FinetuneResult]:
        """Get status of a fine-tuning job."""
        return self._active_jobs.get(job_id)

    def list_jobs(self) -> List[FinetuneResult]:
        """List all tracked fine-tuning jobs."""
        return list(self._active_jobs.values())


@dataclass
class ExpertModel:
    """A fine-tuned expert model."""
    model_id: str
    topic_id: str
    topic_name: str
    base_model: str
    adapter_path: Optional[str] = None
    gguf_path: Optional[str] = None
    training_samples: int = 0
    final_loss: float = 0.0
    is_active: bool = True
    created_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class ExpertModelRegistry:
    """
    Registry for managing fine-tuned expert models.

    Tracks models, their paths, and metadata for serving.
    """

    def __init__(
        self,
        registry_path: str = "/Users/Shared/Coding/KITT/.expert_models/registry.json",
    ):
        self.registry_path = Path(registry_path)
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        self._experts: Dict[str, ExpertModel] = {}
        self._load_registry()

    def _load_registry(self) -> None:
        """Load registry from disk."""
        if self.registry_path.exists():
            try:
                with open(self.registry_path, "r") as f:
                    data = json.load(f)

                for expert_data in data.get("experts", []):
                    created_at = None
                    if expert_data.get("created_at"):
                        created_at = datetime.fromisoformat(expert_data["created_at"])

                    expert = ExpertModel(
                        model_id=expert_data["model_id"],
                        topic_id=expert_data["topic_id"],
                        topic_name=expert_data["topic_name"],
                        base_model=expert_data["base_model"],
                        adapter_path=expert_data.get("adapter_path"),
                        gguf_path=expert_data.get("gguf_path"),
                        training_samples=expert_data.get("training_samples", 0),
                        final_loss=expert_data.get("final_loss", 0.0),
                        is_active=expert_data.get("is_active", True),
                        created_at=created_at,
                        metadata=expert_data.get("metadata", {}),
                    )
                    self._experts[expert.model_id] = expert

                logger.info(f"Loaded {len(self._experts)} experts from registry")

            except Exception as e:
                logger.error(f"Failed to load registry: {e}")

    def _save_registry(self) -> None:
        """Save registry to disk."""
        data = {
            "experts": [
                {
                    "model_id": e.model_id,
                    "topic_id": e.topic_id,
                    "topic_name": e.topic_name,
                    "base_model": e.base_model,
                    "adapter_path": e.adapter_path,
                    "gguf_path": e.gguf_path,
                    "training_samples": e.training_samples,
                    "final_loss": e.final_loss,
                    "is_active": e.is_active,
                    "created_at": e.created_at.isoformat() if e.created_at else None,
                    "metadata": e.metadata,
                }
                for e in self._experts.values()
            ],
            "updated_at": datetime.utcnow().isoformat(),
        }

        with open(self.registry_path, "w") as f:
            json.dump(data, f, indent=2)

    async def register_expert(
        self,
        topic_id: str,
        topic_name: str,
        base_model: str,
        adapter_path: Optional[str] = None,
        gguf_path: Optional[str] = None,
        training_samples: int = 0,
        final_loss: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ExpertModel:
        """
        Register a new expert model.

        Args:
            topic_id: Research topic ID
            topic_name: Human-readable topic name
            base_model: Base model used for training
            adapter_path: Path to LoRA adapter
            gguf_path: Path to GGUF file
            training_samples: Number of training samples
            final_loss: Final training loss
            metadata: Additional metadata

        Returns:
            Registered ExpertModel
        """
        model_id = f"expert-{topic_id[:8]}-{uuid.uuid4().hex[:6]}"

        expert = ExpertModel(
            model_id=model_id,
            topic_id=topic_id,
            topic_name=topic_name,
            base_model=base_model,
            adapter_path=adapter_path,
            gguf_path=gguf_path,
            training_samples=training_samples,
            final_loss=final_loss,
            is_active=True,
            created_at=datetime.utcnow(),
            metadata=metadata or {},
        )

        self._experts[model_id] = expert
        self._save_registry()

        logger.info(f"Registered expert model: {model_id} for topic: {topic_name}")
        return expert

    async def list_experts(
        self,
        active_only: bool = True,
        topic_id: Optional[str] = None,
    ) -> List[ExpertModel]:
        """
        List registered expert models.

        Args:
            active_only: Only return active models
            topic_id: Filter by topic ID

        Returns:
            List of ExpertModel
        """
        experts = list(self._experts.values())

        if active_only:
            experts = [e for e in experts if e.is_active]

        if topic_id:
            experts = [e for e in experts if e.topic_id == topic_id]

        return experts

    async def get_expert(self, model_id: str) -> Optional[ExpertModel]:
        """Get a specific expert model."""
        return self._experts.get(model_id)

    async def deactivate_expert(self, model_id: str) -> bool:
        """Deactivate an expert model."""
        expert = self._experts.get(model_id)
        if expert:
            expert.is_active = False
            self._save_registry()
            return True
        return False

    async def delete_expert(self, model_id: str) -> bool:
        """Delete an expert model and its files."""
        expert = self._experts.get(model_id)
        if not expert:
            return False

        # Delete files
        if expert.adapter_path and Path(expert.adapter_path).exists():
            shutil.rmtree(expert.adapter_path, ignore_errors=True)

        if expert.gguf_path and Path(expert.gguf_path).exists():
            Path(expert.gguf_path).unlink(missing_ok=True)

        del self._experts[model_id]
        self._save_registry()

        logger.info(f"Deleted expert model: {model_id}")
        return True


# Global instances
_pipeline: Optional[FinetunePipeline] = None
_registry: Optional[ExpertModelRegistry] = None


def get_finetune_pipeline() -> FinetunePipeline:
    """Get or create the global fine-tune pipeline."""
    global _pipeline
    if _pipeline is None:
        _pipeline = FinetunePipeline()
    return _pipeline


def get_expert_registry() -> ExpertModelRegistry:
    """Get or create the global expert registry."""
    global _registry
    if _registry is None:
        _registry = ExpertModelRegistry()
    return _registry
