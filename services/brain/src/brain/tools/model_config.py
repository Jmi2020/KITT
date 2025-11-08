# noqa: D401
"""Model-aware configuration for tool calling formats."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ToolCallFormat(Enum):
    """Supported tool calling formats."""

    QWEN_XML = "qwen_xml"  # Qwen2.5/3: <tool_call>{...}</tool_call>
    MISTRAL_JSON = "mistral_json"  # Mistral: [TOOL_CALLS] {...}
    GEMMA_FUNCTION = "gemma_function"  # Gemma: <function_call>...</function_call>
    LLAMA_JSON = "llama_json"  # Llama 3.1+/3.3: JSON tool calls
    GENERIC_XML = "generic_xml"  # Generic fallback


@dataclass
class ModelConfig:
    """Configuration for a specific model family."""

    format: ToolCallFormat
    requires_jinja: bool = True
    requires_function_auth: bool = True  # -fa flag
    supports_parallel_calls: bool = False


def detect_model_format(model_path_or_alias: str) -> ToolCallFormat:
    """Detect tool calling format from model path or alias.

    Args:
        model_path_or_alias: Model file path or alias (e.g., "kitty-primary")

    Returns:
        ToolCallFormat enum

    Examples:
        >>> detect_model_format("Qwen2.5-72B-Instruct-GGUF/qwen2.5-72b-instruct.gguf")
        ToolCallFormat.QWEN_XML
        >>> detect_model_format("Mistral-7B-v0.3/mistral.gguf")
        ToolCallFormat.MISTRAL_JSON
        >>> detect_model_format("Llama-3.3-70B-Instruct-UD-Q4_K_XL.gguf")
        ToolCallFormat.LLAMA_JSON
        >>> detect_model_format("kitty-primary")
        ToolCallFormat.LLAMA_JSON
    """
    model_lower = model_path_or_alias.lower()

    # Check for known KITTY aliases first (based on .env configuration)
    # kitty-primary = Llama-3.3-70B (from LLAMACPP_PRIMARY_MODEL)
    if "kitty-primary" in model_lower:
        return ToolCallFormat.LLAMA_JSON
    # kitty-coder = Qwen2.5-Coder (from LLAMACPP_CODER_MODEL)
    elif "kitty-coder" in model_lower:
        return ToolCallFormat.QWEN_XML
    # kitty-q4 = Athene V2 Agent (from LLAMACPP_Q4_MODEL)
    elif "kitty-q4" in model_lower or "athene" in model_lower:
        return ToolCallFormat.LLAMA_JSON
    # Model path-based detection
    elif "qwen" in model_lower or "qwen2.5" in model_lower or "qwen3" in model_lower:
        return ToolCallFormat.QWEN_XML
    elif "llama-3.1" in model_lower or "llama-3.3" in model_lower or "llama3.1" in model_lower or "llama3.3" in model_lower or "llama-3-70b" in model_lower:
        return ToolCallFormat.LLAMA_JSON
    elif "mistral" in model_lower:
        return ToolCallFormat.MISTRAL_JSON
    elif "gemma" in model_lower:
        return ToolCallFormat.GEMMA_FUNCTION
    else:
        # Default fallback for unknown models
        return ToolCallFormat.GENERIC_XML


def get_model_config(model_path_or_alias: str) -> ModelConfig:
    """Get configuration for a specific model.

    Args:
        model_path_or_alias: Model file path or alias

    Returns:
        ModelConfig with format and flags
    """
    format_type = detect_model_format(model_path_or_alias)

    if format_type == ToolCallFormat.QWEN_XML:
        return ModelConfig(
            format=ToolCallFormat.QWEN_XML,
            requires_jinja=True,
            requires_function_auth=True,
            supports_parallel_calls=True,
        )
    elif format_type == ToolCallFormat.LLAMA_JSON:
        return ModelConfig(
            format=ToolCallFormat.LLAMA_JSON,
            requires_jinja=True,
            requires_function_auth=True,
            supports_parallel_calls=True,
        )
    elif format_type == ToolCallFormat.MISTRAL_JSON:
        return ModelConfig(
            format=ToolCallFormat.MISTRAL_JSON,
            requires_jinja=True,
            requires_function_auth=True,
            supports_parallel_calls=False,
        )
    elif format_type == ToolCallFormat.GEMMA_FUNCTION:
        return ModelConfig(
            format=ToolCallFormat.GEMMA_FUNCTION,
            requires_jinja=False,
            requires_function_auth=False,
            supports_parallel_calls=False,
        )
    else:
        # Generic fallback
        return ModelConfig(
            format=ToolCallFormat.GENERIC_XML,
            requires_jinja=True,
            requires_function_auth=True,
            supports_parallel_calls=False,
        )


__all__ = ["ToolCallFormat", "ModelConfig", "detect_model_format", "get_model_config"]
