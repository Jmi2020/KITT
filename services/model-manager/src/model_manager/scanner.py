# noqa: D401
"""GGUF model scanner for discovering and indexing models."""

from __future__ import annotations

import logging
import re
import time
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Set

from .models import ModelInfo, ModelRegistry, QuantizationType, ToolCallFormat

logger = logging.getLogger(__name__)


def detect_quantization(filename: str) -> QuantizationType:
    """Detect quantization type from filename.

    Args:
        filename: GGUF filename

    Returns:
        QuantizationType enum value
    """
    filename_lower = filename.lower()

    # Check for quantization patterns
    if "fp16" in filename_lower or "f16" in filename_lower:
        return QuantizationType.FP16
    elif "fp32" in filename_lower or "f32" in filename_lower:
        return QuantizationType.FP32
    elif "q8_0" in filename_lower or "q8-0" in filename_lower:
        return QuantizationType.Q8_0
    elif "q6_k" in filename_lower or "q6-k" in filename_lower:
        return QuantizationType.Q6_K
    elif "q5_k_m" in filename_lower or "q5-k-m" in filename_lower:
        return QuantizationType.Q5_K_M
    elif "q5_k_s" in filename_lower or "q5-k-s" in filename_lower:
        return QuantizationType.Q5_K_S
    elif "q4_k_m" in filename_lower or "q4-k-m" in filename_lower:
        return QuantizationType.Q4_K_M
    elif "q4_k_s" in filename_lower or "q4-k-s" in filename_lower:
        return QuantizationType.Q4_K_S
    elif "q3_k_m" in filename_lower or "q3-k-m" in filename_lower:
        return QuantizationType.Q3_K_M
    elif "q3_k_s" in filename_lower or "q3-k-s" in filename_lower:
        return QuantizationType.Q3_K_S
    elif "q2_k" in filename_lower or "q2-k" in filename_lower:
        return QuantizationType.Q2_K

    return QuantizationType.UNKNOWN


def detect_tool_format(model_name: str) -> ToolCallFormat:
    """Detect tool calling format from model name.

    Args:
        model_name: Model name or family

    Returns:
        ToolCallFormat enum value
    """
    name_lower = model_name.lower()

    if "qwen" in name_lower:
        return ToolCallFormat.QWEN_XML
    elif "mistral" in name_lower:
        return ToolCallFormat.MISTRAL_JSON
    elif "gemma" in name_lower:
        return ToolCallFormat.GEMMA_FUNCTION
    else:
        return ToolCallFormat.GENERIC_XML


def parse_shard_info(filename: str) -> tuple[Optional[int], Optional[int]]:
    """Parse shard index and total from filename.

    Patterns supported:
    - 00001-of-00042
    - 0001-of-0042
    - part-00001-of-00042

    Args:
        filename: GGUF filename

    Returns:
        Tuple of (shard_index, shard_total) or (None, None)
    """
    # Pattern: 00001-of-00042 or similar
    pattern = r"(?:part-)?(\d+)-of-(\d+)"
    match = re.search(pattern, filename, re.IGNORECASE)

    if match:
        shard_index = int(match.group(1))
        shard_total = int(match.group(2))
        return shard_index, shard_total

    return None, None


def extract_model_family(path: Path) -> str:
    """Extract model family from directory structure.

    Args:
        path: Path to GGUF file

    Returns:
        Model family name (parent directory name)
    """
    return path.parent.name


def extract_model_name(path: Path, family: str, quantization: QuantizationType) -> str:
    """Generate clean model name from path.

    Args:
        path: Path to GGUF file
        family: Model family
        quantization: Quantization type

    Returns:
        Clean model name
    """
    # Use filename without extension as base
    name = path.stem

    # Remove shard information if present
    name = re.sub(r"-\d+-of-\d+", "", name)
    name = re.sub(r"part-\d+-of-\d+", "", name, flags=re.IGNORECASE)

    # If name is very long, try to shorten it intelligently
    if len(name) > 60:
        # Try to extract core model info
        # Example: qwen2.5-72b-instruct-fp16 -> qwen2.5-72b-fp16
        parts = name.split("-")
        if len(parts) > 3:
            # Keep first 2 parts and quantization
            name = "-".join(parts[:2] + [quantization.value])

    return name


def estimate_memory_gb(size_bytes: int, quantization: QuantizationType) -> float:
    """Estimate memory requirements for model.

    This is a rough estimate. Actual requirements depend on:
    - Context size
    - Batch size
    - Number of layers offloaded to GPU

    Args:
        size_bytes: File size in bytes
        quantization: Quantization type

    Returns:
        Estimated memory in GB
    """
    # Base memory is file size
    file_size_gb = size_bytes / (1024**3)

    # Add overhead based on quantization
    # Higher quantization = more compute overhead
    overhead_factor = {
        QuantizationType.FP32: 1.5,
        QuantizationType.FP16: 1.3,
        QuantizationType.Q8_0: 1.2,
        QuantizationType.Q6_K: 1.15,
        QuantizationType.Q5_K_M: 1.1,
        QuantizationType.Q5_K_S: 1.1,
        QuantizationType.Q4_K_M: 1.05,
        QuantizationType.Q4_K_S: 1.05,
        QuantizationType.Q3_K_M: 1.0,
        QuantizationType.Q3_K_S: 1.0,
        QuantizationType.Q2_K: 1.0,
        QuantizationType.UNKNOWN: 1.2,
    }.get(quantization, 1.2)

    return file_size_gb * overhead_factor


def estimate_params_billions(size_bytes: int, quantization: QuantizationType) -> Optional[float]:
    """Estimate model parameters in billions from file size.

    Very rough estimation based on quantization and file size.

    Args:
        size_bytes: File size in bytes
        quantization: Quantization type

    Returns:
        Estimated parameters in billions, or None if unknown
    """
    size_gb = size_bytes / (1024**3)

    # Bytes per parameter for different quantizations (approximate)
    bytes_per_param = {
        QuantizationType.FP32: 4.0,
        QuantizationType.FP16: 2.0,
        QuantizationType.Q8_0: 1.0,
        QuantizationType.Q6_K: 0.75,
        QuantizationType.Q5_K_M: 0.625,
        QuantizationType.Q5_K_S: 0.625,
        QuantizationType.Q4_K_M: 0.5,
        QuantizationType.Q4_K_S: 0.5,
        QuantizationType.Q3_K_M: 0.375,
        QuantizationType.Q3_K_S: 0.375,
        QuantizationType.Q2_K: 0.25,
    }.get(quantization)

    if bytes_per_param is None:
        return None

    # Calculate params in billions
    total_bytes = size_gb * (1024**3)
    params = total_bytes / bytes_per_param
    params_billions = params / 1e9

    return round(params_billions, 1)


def validate_split_model(files: List[Path]) -> tuple[bool, Set[int]]:
    """Validate that all shards of a split model are present.

    Args:
        files: List of GGUF files that appear to be part of the same model

    Returns:
        Tuple of (is_complete, missing_shards)
    """
    shard_indices: Set[int] = set()
    shard_total: Optional[int] = None

    for file_path in files:
        shard_index, total = parse_shard_info(file_path.name)
        if shard_index is not None and total is not None:
            shard_indices.add(shard_index)
            if shard_total is None:
                shard_total = total
            elif shard_total != total:
                logger.warning(f"Inconsistent shard totals: {shard_total} vs {total} in {file_path}")

    if shard_total is None:
        # Not a split model
        return True, set()

    # Check if all shards from 1 to shard_total are present
    expected = set(range(1, shard_total + 1))
    missing = expected - shard_indices

    is_complete = len(missing) == 0
    return is_complete, missing


class ModelScanner:
    """Scans directory for GGUF models and builds registry."""

    def __init__(self, models_dir: Path) -> None:
        """Initialize scanner.

        Args:
            models_dir: Root directory to scan for models
        """
        self.models_dir = Path(models_dir)

    def scan(self) -> ModelRegistry:
        """Scan models directory and build registry.

        Returns:
            ModelRegistry with all discovered models
        """
        start_time = time.time()
        logger.info(f"Scanning {self.models_dir} for GGUF models...")

        registry = ModelRegistry()

        # Find all GGUF files
        gguf_files = list(self.models_dir.rglob("*.gguf"))
        logger.info(f"Found {len(gguf_files)} GGUF files")

        # Group files by potential model (to detect split models)
        grouped: Dict[str, List[Path]] = defaultdict(list)
        for file_path in gguf_files:
            # Group key: family + base name without shard info
            family = extract_model_family(file_path)
            base_name = re.sub(r"-\d+-of-\d+", "", file_path.stem)
            group_key = f"{family}/{base_name}"
            grouped[group_key].append(file_path)

        # Process each group
        for group_key, files in grouped.items():
            # Determine if this is a split model
            shard_index, shard_total = parse_shard_info(files[0].name)
            is_split = shard_total is not None and shard_total > 1

            if is_split:
                # Validate split model completeness
                is_complete, missing = validate_split_model(files)

                if not is_complete:
                    logger.warning(f"Incomplete split model {group_key}: missing shards {missing}")

                # Create single ModelInfo for the split model (representing all shards)
                total_size = sum(f.stat().st_size for f in files)
                quantization = detect_quantization(files[0].name)
                family = extract_model_family(files[0])
                name = extract_model_name(files[0], family, quantization)

                model = ModelInfo(
                    path=files[0],  # Use first shard as representative path
                    name=name,
                    family=family,
                    quantization=quantization,
                    tool_format=detect_tool_format(family),
                    size_bytes=total_size,
                    file_count=len(files),
                    shard_index=1,  # Represents the first shard
                    shard_total=shard_total,
                    is_complete=is_complete,
                    estimated_params_billions=estimate_params_billions(total_size, quantization),
                    estimated_memory_gb=estimate_memory_gb(total_size, quantization),
                )

                registry.add_model(model)
                logger.debug(f"Added split model: {model.display_name} ({model.file_count} shards, {model.size_gb:.1f} GB)")

            else:
                # Single-file models - create ModelInfo for each
                for file_path in files:
                    quantization = detect_quantization(file_path.name)
                    family = extract_model_family(file_path)
                    name = extract_model_name(file_path, family, quantization)
                    size = file_path.stat().st_size

                    model = ModelInfo(
                        path=file_path,
                        name=name,
                        family=family,
                        quantization=quantization,
                        tool_format=detect_tool_format(family),
                        size_bytes=size,
                        file_count=1,
                        is_complete=True,
                        estimated_params_billions=estimate_params_billions(size, quantization),
                        estimated_memory_gb=estimate_memory_gb(size, quantization),
                    )

                    registry.add_model(model)
                    logger.debug(f"Added model: {model.display_name} ({model.size_gb:.1f} GB)")

        # Finalize registry
        scan_duration = time.time() - start_time
        registry.scan_duration_seconds = scan_duration

        logger.info(
            f"Scan complete: {registry.total_models} models in {registry.total_families} families "
            f"({registry.total_size_gb:.1f} GB total) in {scan_duration:.2f}s"
        )

        return registry


__all__ = [
    "ModelScanner",
    "detect_quantization",
    "detect_tool_format",
    "parse_shard_info",
    "extract_model_family",
    "extract_model_name",
    "estimate_memory_gb",
    "estimate_params_billions",
    "validate_split_model",
]
