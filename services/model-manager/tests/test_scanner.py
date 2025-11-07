# noqa: D401
"""Unit tests for model scanner module."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import List

import pytest

from model_manager.models import ModelInfo, QuantizationType, ToolCallFormat
from model_manager.scanner import (
    ModelScanner,
    detect_quantization,
    detect_tool_format,
    estimate_memory_gb,
    estimate_params_billions,
    extract_model_family,
    extract_model_name,
    parse_shard_info,
    validate_split_model,
)


class TestDetectQuantization:
    """Test quantization detection from filenames."""

    def test_fp16_detection(self) -> None:
        """Test FP16 detection."""
        assert detect_quantization("model-fp16.gguf") == QuantizationType.FP16
        assert detect_quantization("model-f16.gguf") == QuantizationType.FP16
        assert detect_quantization("MODEL-FP16.GGUF") == QuantizationType.FP16

    def test_fp32_detection(self) -> None:
        """Test FP32 detection."""
        assert detect_quantization("model-fp32.gguf") == QuantizationType.FP32
        assert detect_quantization("model-f32.gguf") == QuantizationType.FP32

    def test_q8_0_detection(self) -> None:
        """Test Q8_0 detection."""
        assert detect_quantization("model-q8_0.gguf") == QuantizationType.Q8_0
        assert detect_quantization("model-q8-0.gguf") == QuantizationType.Q8_0

    def test_q4_k_m_detection(self) -> None:
        """Test Q4_K_M detection."""
        assert detect_quantization("model-q4_k_m.gguf") == QuantizationType.Q4_K_M
        assert detect_quantization("model-q4-k-m.gguf") == QuantizationType.Q4_K_M
        assert detect_quantization("qwen-Q4_K_M.gguf") == QuantizationType.Q4_K_M

    def test_q3_k_m_detection(self) -> None:
        """Test Q3_K_M detection."""
        assert detect_quantization("model-q3_k_m.gguf") == QuantizationType.Q3_K_M
        assert detect_quantization("model-q3-k-m.gguf") == QuantizationType.Q3_K_M

    def test_unknown_detection(self) -> None:
        """Test unknown quantization fallback."""
        assert detect_quantization("model.gguf") == QuantizationType.UNKNOWN
        assert detect_quantization("model-unknown.gguf") == QuantizationType.UNKNOWN


class TestDetectToolFormat:
    """Test tool calling format detection."""

    def test_qwen_detection(self) -> None:
        """Test Qwen XML format detection."""
        assert detect_tool_format("Qwen2.5-72B") == ToolCallFormat.QWEN_XML
        assert detect_tool_format("qwen-coder") == ToolCallFormat.QWEN_XML
        assert detect_tool_format("QWEN2.5-INSTRUCT") == ToolCallFormat.QWEN_XML

    def test_mistral_detection(self) -> None:
        """Test Mistral JSON format detection."""
        assert detect_tool_format("Mistral-7B") == ToolCallFormat.MISTRAL_JSON
        assert detect_tool_format("mistral-instruct") == ToolCallFormat.MISTRAL_JSON

    def test_gemma_detection(self) -> None:
        """Test Gemma function format detection."""
        assert detect_tool_format("Gemma-2B") == ToolCallFormat.GEMMA_FUNCTION
        assert detect_tool_format("gemma-it") == ToolCallFormat.GEMMA_FUNCTION

    def test_generic_fallback(self) -> None:
        """Test generic XML fallback."""
        assert detect_tool_format("Llama-3-8B") == ToolCallFormat.GENERIC_XML
        assert detect_tool_format("Unknown-Model") == ToolCallFormat.GENERIC_XML


class TestParseShardInfo:
    """Test shard information parsing."""

    def test_standard_shard_pattern(self) -> None:
        """Test standard shard pattern parsing."""
        index, total = parse_shard_info("model-00001-of-00042.gguf")
        assert index == 1
        assert total == 42

    def test_short_shard_pattern(self) -> None:
        """Test short shard pattern parsing."""
        index, total = parse_shard_info("model-0001-of-0009.gguf")
        assert index == 1
        assert total == 9

    def test_part_prefix_pattern(self) -> None:
        """Test part-prefixed shard pattern."""
        index, total = parse_shard_info("model-part-00005-of-00010.gguf")
        assert index == 5
        assert total == 10

    def test_case_insensitive(self) -> None:
        """Test case insensitive matching."""
        index, total = parse_shard_info("MODEL-PART-00001-OF-00003.GGUF")
        assert index == 1
        assert total == 3

    def test_no_shard_pattern(self) -> None:
        """Test files without shard pattern."""
        index, total = parse_shard_info("model.gguf")
        assert index is None
        assert total is None


class TestExtractModelFamily:
    """Test model family extraction."""

    def test_extract_from_path(self) -> None:
        """Test family extraction from directory structure."""
        path = Path("/models/Qwen2.5-72B-Instruct-GGUF/model.gguf")
        assert extract_model_family(path) == "Qwen2.5-72B-Instruct-GGUF"

    def test_extract_from_nested_path(self) -> None:
        """Test family from nested path."""
        path = Path("/Users/Shared/Coding/models/Mistral-7B/model.gguf")
        assert extract_model_family(path) == "Mistral-7B"


class TestExtractModelName:
    """Test model name extraction."""

    def test_simple_name(self) -> None:
        """Test simple model name extraction."""
        path = Path("/models/Qwen2.5/qwen2.5-72b-instruct-q4_k_m.gguf")
        family = "Qwen2.5-72B-Instruct-GGUF"
        quant = QuantizationType.Q4_K_M

        name = extract_model_name(path, family, quant)
        assert "qwen2.5" in name.lower()
        assert "shard" not in name.lower()

    def test_remove_shard_info(self) -> None:
        """Test shard info removal from name."""
        path = Path("/models/Qwen/model-00001-of-00042.gguf")
        family = "Qwen2.5"
        quant = QuantizationType.FP16

        name = extract_model_name(path, family, quant)
        assert "-00001-of-00042" not in name
        assert "part-" not in name.lower()

    def test_long_name_shortening(self) -> None:
        """Test long name shortening logic."""
        # Create a very long filename
        long_name = "qwen2.5-very-long-model-name-with-many-parts-instruct-q4_k_m"
        path = Path(f"/models/Qwen/{long_name}.gguf")
        family = "Qwen2.5"
        quant = QuantizationType.Q4_K_M

        name = extract_model_name(path, family, quant)
        # Should be shortened if > 60 chars
        if len(long_name) > 60:
            assert len(name) < len(long_name)


class TestEstimateMemory:
    """Test memory estimation."""

    def test_fp16_memory(self) -> None:
        """Test FP16 memory estimation."""
        size_bytes = 10 * (1024**3)  # 10 GB
        mem = estimate_memory_gb(size_bytes, QuantizationType.FP16)
        assert mem > 10.0  # Should have overhead
        assert mem < 15.0  # But not too much (1.3x factor)

    def test_q4_k_m_memory(self) -> None:
        """Test Q4_K_M memory estimation."""
        size_bytes = 10 * (1024**3)  # 10 GB
        mem = estimate_memory_gb(size_bytes, QuantizationType.Q4_K_M)
        assert mem > 10.0  # Should have overhead
        assert mem < 11.0  # Small overhead (1.05x factor)

    def test_unknown_memory(self) -> None:
        """Test unknown quantization uses default overhead."""
        size_bytes = 10 * (1024**3)
        mem = estimate_memory_gb(size_bytes, QuantizationType.UNKNOWN)
        assert mem > 10.0


class TestEstimateParams:
    """Test parameter estimation."""

    def test_fp16_params(self) -> None:
        """Test FP16 parameter estimation."""
        # 140 GB FP16 model ≈ 70B params (2 bytes/param)
        size_bytes = 140 * (1024**3)
        params = estimate_params_billions(size_bytes, QuantizationType.FP16)
        assert params is not None
        assert 65 < params < 80  # Should be around 70B (approximate)

    def test_q4_k_m_params(self) -> None:
        """Test Q4_K_M parameter estimation."""
        # 36 GB Q4_K_M model ≈ 72B params (0.5 bytes/param)
        size_bytes = 36 * (1024**3)
        params = estimate_params_billions(size_bytes, QuantizationType.Q4_K_M)
        assert params is not None
        assert 68 < params < 80  # Should be around 72B (approximate)

    def test_unknown_params(self) -> None:
        """Test unknown quantization returns None."""
        size_bytes = 10 * (1024**3)
        params = estimate_params_billions(size_bytes, QuantizationType.UNKNOWN)
        assert params is None


class TestValidateSplitModel:
    """Test split model validation."""

    def _create_temp_shards(self, tmpdir: Path, base: str, total: int, missing: List[int] = None) -> List[Path]:
        """Create temporary shard files."""
        missing = missing or []
        files = []
        for i in range(1, total + 1):
            if i in missing:
                continue
            filename = f"{base}-{i:05d}-of-{total:05d}.gguf"
            filepath = tmpdir / filename
            filepath.touch()
            files.append(filepath)
        return files

    def test_complete_split_model(self, tmp_path: Path) -> None:
        """Test complete split model validation."""
        files = self._create_temp_shards(tmp_path, "model", 5)
        is_complete, missing = validate_split_model(files)
        assert is_complete is True
        assert len(missing) == 0

    def test_incomplete_split_model(self, tmp_path: Path) -> None:
        """Test incomplete split model detection."""
        files = self._create_temp_shards(tmp_path, "model", 10, missing=[3, 7])
        is_complete, missing = validate_split_model(files)
        assert is_complete is False
        assert 3 in missing
        assert 7 in missing
        assert len(missing) == 2

    def test_single_file_model(self, tmp_path: Path) -> None:
        """Test single-file model returns complete."""
        filepath = tmp_path / "model.gguf"
        filepath.touch()
        is_complete, missing = validate_split_model([filepath])
        assert is_complete is True
        assert len(missing) == 0


class TestModelScanner:
    """Test model scanner functionality."""

    def _create_test_models(self, tmpdir: Path) -> None:
        """Create test model directory structure."""
        # Create single-file model
        qwen_dir = tmpdir / "Qwen2.5-7B-Instruct-GGUF"
        qwen_dir.mkdir()
        (qwen_dir / "qwen2.5-7b-instruct-q4_k_m.gguf").write_bytes(b"x" * 1024 * 1024 * 100)  # 100 MB

        # Create split model (complete)
        qwen_72b_dir = tmpdir / "Qwen2.5-72B-Instruct-GGUF"
        qwen_72b_dir.mkdir()
        for i in range(1, 4):
            filename = f"qwen2.5-72b-instruct-fp16-{i:05d}-of-{3:05d}.gguf"
            (qwen_72b_dir / filename).write_bytes(b"x" * 1024 * 1024 * 500)  # 500 MB each

        # Create split model (incomplete - missing shard 2)
        mistral_dir = tmpdir / "Mistral-7B-Instruct-GGUF"
        mistral_dir.mkdir()
        (mistral_dir / "mistral-7b-00001-of-00003.gguf").write_bytes(b"x" * 1024 * 1024 * 200)
        (mistral_dir / "mistral-7b-00003-of-00003.gguf").write_bytes(b"x" * 1024 * 1024 * 200)

    def test_scan_single_file_model(self, tmp_path: Path) -> None:
        """Test scanning single-file models."""
        self._create_test_models(tmp_path)
        scanner = ModelScanner(tmp_path)
        registry = scanner.scan()

        # Should find Qwen 7B single-file model
        qwen_models = [m for m in registry.models if "7b" in m.name.lower() and m.file_count == 1]
        assert len(qwen_models) >= 1

        qwen = qwen_models[0]
        assert qwen.file_count == 1
        assert qwen.is_complete is True
        assert qwen.quantization == QuantizationType.Q4_K_M
        assert qwen.tool_format == ToolCallFormat.QWEN_XML

    def test_scan_split_model_complete(self, tmp_path: Path) -> None:
        """Test scanning complete split models."""
        self._create_test_models(tmp_path)
        scanner = ModelScanner(tmp_path)
        registry = scanner.scan()

        # Should find Qwen 72B split model (complete)
        qwen_72b = [m for m in registry.models if "72b" in m.name.lower()]
        assert len(qwen_72b) >= 1

        model = qwen_72b[0]
        assert model.file_count == 3
        assert model.shard_total == 3
        assert model.is_complete is True
        assert model.quantization == QuantizationType.FP16

    def test_scan_split_model_incomplete(self, tmp_path: Path) -> None:
        """Test scanning incomplete split models."""
        self._create_test_models(tmp_path)
        scanner = ModelScanner(tmp_path)
        registry = scanner.scan()

        # Should find Mistral split model (incomplete)
        mistral = [m for m in registry.models if "mistral" in m.name.lower()]
        assert len(mistral) >= 1

        model = mistral[0]
        assert model.shard_total == 3
        assert model.file_count == 2  # Only 2 shards present
        assert model.is_complete is False

    def test_registry_statistics(self, tmp_path: Path) -> None:
        """Test registry statistics."""
        self._create_test_models(tmp_path)
        scanner = ModelScanner(tmp_path)
        registry = scanner.scan()

        assert registry.total_models >= 3  # At least 3 models
        assert registry.total_families >= 3  # At least 3 families
        assert registry.total_size_gb > 0
        assert registry.scan_duration_seconds > 0

    def test_registry_family_grouping(self, tmp_path: Path) -> None:
        """Test model family grouping."""
        self._create_test_models(tmp_path)
        scanner = ModelScanner(tmp_path)
        registry = scanner.scan()

        # Should have models grouped by family
        assert len(registry.families) >= 3

        # Check that families contain models
        for family_name, models in registry.families.items():
            assert len(models) > 0
            for model in models:
                assert model.family == family_name

    def test_empty_directory(self, tmp_path: Path) -> None:
        """Test scanning empty directory."""
        scanner = ModelScanner(tmp_path)
        registry = scanner.scan()

        assert registry.total_models == 0
        assert registry.total_families == 0
        assert registry.total_size_gb == 0

    def test_no_gguf_files(self, tmp_path: Path) -> None:
        """Test directory with no GGUF files."""
        # Create some non-GGUF files
        (tmp_path / "model.safetensors").touch()
        (tmp_path / "config.json").touch()

        scanner = ModelScanner(tmp_path)
        registry = scanner.scan()

        assert registry.total_models == 0
