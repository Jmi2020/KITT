# noqa: D401
"""Unit tests for configuration manager."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from model_manager.config import ConfigManager, load_config, save_config
from model_manager.models import ServerConfig


class TestConfigManager:
    """Test configuration manager functionality."""

    def _create_test_env(self, tmpdir: Path, **overrides: str) -> Path:
        """Create a test .env file with configurable values."""
        defaults = {
            "LLAMACPP_PRIMARY_MODEL": "Qwen2.5-72B/model.gguf",
            "LLAMACPP_MODELS_DIR": "/Users/Shared/Coding/models",
            "LLAMACPP_PRIMARY_ALIAS": "kitty-primary",
            "LLAMACPP_HOST": "localhost",
            "LLAMACPP_PORT": "8080",
            "LLAMACPP_BIN": "llama-server",
            "LLAMACPP_CTX": "8192",
            "LLAMACPP_N_PREDICT": "896",
            "LLAMACPP_TEMPERATURE": "0.7",
            "LLAMACPP_TOP_P": "0.95",
            "LLAMACPP_REPEAT_PENALTY": "1.1",
            "LLAMACPP_N_GPU_LAYERS": "999",
            "LLAMACPP_THREADS": "20",
            "LLAMACPP_BATCH_SIZE": "4096",
            "LLAMACPP_UBATCH_SIZE": "1024",
            "LLAMACPP_PARALLEL": "6",
            "LLAMACPP_FLASH_ATTN": "1",
            "LLAMACPP_TOOL_CALLING": "0",
        }
        defaults.update(overrides)

        env_path = tmpdir / ".env"
        lines = [f"{key}={value}\n" for key, value in defaults.items()]
        env_path.write_text("".join(lines))
        return env_path

    def test_load_basic_config(self, tmp_path: Path) -> None:
        """Test loading basic configuration."""
        env_path = self._create_test_env(tmp_path)
        manager = ConfigManager(env_path)
        config = manager.load()

        assert config.primary_model == "Qwen2.5-72B/model.gguf"
        assert config.models_dir == Path("/Users/Shared/Coding/models")
        assert config.model_alias == "kitty-primary"
        assert config.host == "localhost"
        assert config.port == 8080

    def test_load_context_settings(self, tmp_path: Path) -> None:
        """Test loading context and generation settings."""
        env_path = self._create_test_env(tmp_path)
        manager = ConfigManager(env_path)
        config = manager.load()

        assert config.context_size == 8192
        assert config.n_predict == 896
        assert config.temperature == 0.7
        assert config.top_p == 0.95
        assert config.repeat_penalty == 1.1

    def test_load_gpu_settings(self, tmp_path: Path) -> None:
        """Test loading GPU and performance settings."""
        env_path = self._create_test_env(tmp_path)
        manager = ConfigManager(env_path)
        config = manager.load()

        assert config.n_gpu_layers == 999
        assert config.threads == 20
        assert config.batch_size == 4096
        assert config.ubatch_size == 1024
        assert config.parallel == 6

    def test_load_boolean_flags(self, tmp_path: Path) -> None:
        """Test loading boolean flags."""
        env_path = self._create_test_env(
            tmp_path,
            LLAMACPP_FLASH_ATTN="1",
            LLAMACPP_TOOL_CALLING="true",
        )
        manager = ConfigManager(env_path)
        config = manager.load()

        assert config.flash_attention is True
        assert config.tool_calling is True

    def test_load_boolean_false(self, tmp_path: Path) -> None:
        """Test loading boolean flags set to false."""
        env_path = self._create_test_env(
            tmp_path,
            LLAMACPP_FLASH_ATTN="0",
            LLAMACPP_TOOL_CALLING="false",
        )
        manager = ConfigManager(env_path)
        config = manager.load()

        assert config.flash_attention is False
        assert config.tool_calling is False

    def test_load_with_defaults(self, tmp_path: Path) -> None:
        """Test loading with missing variables uses defaults."""
        env_path = tmp_path / ".env"
        env_path.write_text("LLAMACPP_PRIMARY_MODEL=model.gguf\n")

        manager = ConfigManager(env_path)
        config = manager.load()

        # Should use defaults for missing values
        assert config.primary_model == "model.gguf"
        assert config.models_dir == Path("/Users/Shared/Coding/models")
        assert config.model_alias == "kitty-primary"
        assert config.port == 8080

    def test_load_stop_tokens(self, tmp_path: Path) -> None:
        """Test loading comma-separated stop tokens."""
        env_path = self._create_test_env(
            tmp_path,
            LLAMACPP_STOP="<|im_end|>,<|endoftext|>,</s>",
        )
        manager = ConfigManager(env_path)
        config = manager.load()

        assert len(config.stop_tokens) == 3
        assert "<|im_end|>" in config.stop_tokens
        assert "<|endoftext|>" in config.stop_tokens
        assert "</s>" in config.stop_tokens

    def test_load_extra_args(self, tmp_path: Path) -> None:
        """Test loading space-separated extra arguments."""
        env_path = self._create_test_env(
            tmp_path,
            LLAMACPP_EXTRA_ARGS="--verbose --log-disable",
        )
        manager = ConfigManager(env_path)
        config = manager.load()

        assert len(config.extra_args) == 2
        assert "--verbose" in config.extra_args
        assert "--log-disable" in config.extra_args

    def test_save_creates_backup(self, tmp_path: Path) -> None:
        """Test that save creates backup of existing .env."""
        env_path = self._create_test_env(tmp_path)
        original_content = env_path.read_text()

        manager = ConfigManager(env_path)
        config = manager.load()
        config.port = 9090
        manager.save(config, backup=True)

        backup_path = env_path.with_suffix(".env.backup")
        assert backup_path.exists()
        assert backup_path.read_text() == original_content

    def test_save_no_backup(self, tmp_path: Path) -> None:
        """Test saving without backup."""
        env_path = self._create_test_env(tmp_path)
        manager = ConfigManager(env_path)
        config = manager.load()
        config.port = 9090
        manager.save(config, backup=False)

        backup_path = env_path.with_suffix(".env.backup")
        assert not backup_path.exists()

    @patch("model_manager.config.set_key")
    def test_save_writes_all_variables(self, mock_set_key: MagicMock, tmp_path: Path) -> None:
        """Test that save writes all configuration variables."""
        env_path = self._create_test_env(tmp_path)
        manager = ConfigManager(env_path)
        config = manager.load()

        # Modify some values
        config.port = 9090
        config.context_size = 16384
        config.flash_attention = False

        manager.save(config, backup=False)

        # Verify set_key was called for each variable
        call_keys = [call[0][1] for call in mock_set_key.call_args_list]
        assert "LLAMACPP_PRIMARY_MODEL" in call_keys
        assert "LLAMACPP_PORT" in call_keys
        assert "LLAMACPP_CTX" in call_keys
        assert "LLAMACPP_FLASH_ATTN" in call_keys

    def test_update_model_basic(self, tmp_path: Path) -> None:
        """Test updating model path and alias."""
        env_path = self._create_test_env(tmp_path)
        manager = ConfigManager(env_path)

        manager.update_model("Qwen2.5-Coder-32B/model-q4_k_m.gguf", "kitty-coder")

        # Reload and verify
        config = manager.load()
        assert config.primary_model == "Qwen2.5-Coder-32B/model-q4_k_m.gguf"
        assert config.model_alias == "kitty-coder"

    def test_update_model_auto_alias(self, tmp_path: Path) -> None:
        """Test update_model with automatic alias generation."""
        env_path = self._create_test_env(tmp_path)
        manager = ConfigManager(env_path)

        manager.update_model("Mistral-7B/mistral-7b-instruct-q4_k_m.gguf")

        # Should use filename stem as alias
        config = manager.load()
        assert config.primary_model == "Mistral-7B/mistral-7b-instruct-q4_k_m.gguf"
        assert config.model_alias == "mistral-7b-instruct-q4_k_m"

    def test_get_env_vars(self, tmp_path: Path) -> None:
        """Test getting all environment variables."""
        env_path = self._create_test_env(tmp_path)
        manager = ConfigManager(env_path)

        env_vars = manager.get_env_vars()

        assert isinstance(env_vars, dict)
        assert "LLAMACPP_PRIMARY_MODEL" in env_vars
        assert "LLAMACPP_PORT" in env_vars
        assert env_vars["LLAMACPP_PORT"] == "8080"

    def test_parse_list_comma_separated(self, tmp_path: Path) -> None:
        """Test parsing comma-separated lists."""
        env_path = self._create_test_env(tmp_path)
        manager = ConfigManager(env_path)

        result = manager._parse_list("token1,token2,token3")
        assert result == ["token1", "token2", "token3"]

    def test_parse_list_space_separated(self, tmp_path: Path) -> None:
        """Test parsing space-separated lists."""
        env_path = self._create_test_env(tmp_path)
        manager = ConfigManager(env_path)

        result = manager._parse_list("arg1 arg2 arg3")
        assert result == ["arg1", "arg2", "arg3"]

    def test_parse_list_empty(self, tmp_path: Path) -> None:
        """Test parsing empty string."""
        env_path = self._create_test_env(tmp_path)
        manager = ConfigManager(env_path)

        result = manager._parse_list("")
        assert result == []

    def test_parse_list_strips_whitespace(self, tmp_path: Path) -> None:
        """Test that parsing strips whitespace."""
        env_path = self._create_test_env(tmp_path)
        manager = ConfigManager(env_path)

        result = manager._parse_list(" token1 , token2 , token3 ")
        assert result == ["token1", "token2", "token3"]

    def test_nonexistent_env_file(self, tmp_path: Path) -> None:
        """Test handling of nonexistent .env file."""
        env_path = tmp_path / "nonexistent.env"
        manager = ConfigManager(env_path)

        # Should not raise an error, just warn
        config = manager.load()

        # Should use all defaults
        assert config.models_dir == Path("/Users/Shared/Coding/models")
        assert config.port == 8080


class TestHelperFunctions:
    """Test helper functions."""

    def test_load_config_helper(self, tmp_path: Path) -> None:
        """Test load_config helper function."""
        env_path = tmp_path / ".env"
        env_path.write_text("LLAMACPP_PRIMARY_MODEL=test.gguf\nLLAMACPP_PORT=9999\n")

        config = load_config(env_path)

        assert isinstance(config, ServerConfig)
        assert config.primary_model == "test.gguf"
        assert config.port == 9999

    def test_save_config_helper(self, tmp_path: Path) -> None:
        """Test save_config helper function."""
        env_path = tmp_path / ".env"
        env_path.write_text("LLAMACPP_PRIMARY_MODEL=old.gguf\n")

        config = ServerConfig(
            primary_model="new.gguf",
            models_dir=Path("/models"),
            port=7777,
        )

        save_config(config, env_path, backup=False)

        # Reload and verify
        reloaded = load_config(env_path)
        assert reloaded.primary_model == "new.gguf"
        assert reloaded.port == 7777


class TestServerConfigCommandGeneration:
    """Test ServerConfig command generation."""

    def test_to_command_basic(self) -> None:
        """Test basic command generation."""
        config = ServerConfig(
            primary_model="model.gguf",
            models_dir=Path("/models"),
            model_alias="test-model",
        )

        cmd = config.to_command()

        assert "llama-server" in cmd
        assert "-m" in cmd
        assert "/models/model.gguf" in cmd
        assert "--host" in cmd
        assert "localhost" in cmd
        assert "--port" in cmd
        assert "8080" in cmd

    def test_to_command_with_alias(self) -> None:
        """Test command generation with model alias."""
        config = ServerConfig(
            primary_model="model.gguf",
            models_dir=Path("/models"),
            model_alias="kitty-coder",
        )

        cmd = config.to_command()

        assert "-a" in cmd
        assert "kitty-coder" in cmd

    def test_to_command_flash_attention(self) -> None:
        """Test command generation with flash attention."""
        config = ServerConfig(
            primary_model="model.gguf",
            models_dir=Path("/models"),
            flash_attention=True,
        )

        cmd = config.to_command()
        assert "-fa" in cmd

    def test_to_command_tool_calling(self) -> None:
        """Test command generation with tool calling."""
        config = ServerConfig(
            primary_model="model.gguf",
            models_dir=Path("/models"),
            tool_calling=True,
        )

        cmd = config.to_command()
        assert "--jinja" in cmd
        assert "-fa" in cmd  # Tool calling enables flash attention

    def test_to_command_stop_tokens(self) -> None:
        """Test command generation with stop tokens."""
        config = ServerConfig(
            primary_model="model.gguf",
            models_dir=Path("/models"),
            stop_tokens=["<|im_end|>", "</s>"],
        )

        cmd = config.to_command()
        assert "--stop" in cmd
        assert "<|im_end|>" in cmd
        assert "</s>" in cmd

    def test_to_command_extra_args(self) -> None:
        """Test command generation with extra arguments."""
        config = ServerConfig(
            primary_model="model.gguf",
            models_dir=Path("/models"),
            extra_args=["--verbose", "--log-disable"],
        )

        cmd = config.to_command()
        assert "--verbose" in cmd
        assert "--log-disable" in cmd

    def test_to_command_gpu_settings(self) -> None:
        """Test command generation with GPU settings."""
        config = ServerConfig(
            primary_model="model.gguf",
            models_dir=Path("/models"),
            n_gpu_layers=999,
            threads=20,
            batch_size=4096,
            ubatch_size=1024,
            parallel=6,
        )

        cmd = config.to_command()

        assert "-ngl" in cmd
        assert "999" in cmd
        assert "-t" in cmd
        assert "20" in cmd
        assert "-b" in cmd
        assert "4096" in cmd
        assert "-ub" in cmd
        assert "1024" in cmd
        assert "-np" in cmd
        assert "6" in cmd

    def test_endpoint_property(self) -> None:
        """Test endpoint URL generation."""
        config = ServerConfig(
            primary_model="model.gguf",
            models_dir=Path("/models"),
            host="127.0.0.1",
            port=9090,
        )

        assert config.endpoint == "http://127.0.0.1:9090"

    def test_full_model_path_property(self) -> None:
        """Test full model path generation."""
        config = ServerConfig(
            primary_model="Qwen2.5/model.gguf",
            models_dir=Path("/Users/Shared/Coding/models"),
        )

        expected = Path("/Users/Shared/Coding/models/Qwen2.5/model.gguf")
        assert config.full_model_path == expected
