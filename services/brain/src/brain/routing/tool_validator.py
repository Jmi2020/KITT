# noqa: D401
"""Tool call validation module for hallucination prevention.

Validates tool calls against JSON schemas before execution to prevent:
- Non-existent tool calls
- Missing required parameters
- Type mismatches
- Fabricated parameter values

Based on hallucination prevention best practices from Research/ToolCallingPrompts.md.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of tool call validation."""

    valid: bool
    error_message: Optional[str] = None
    is_retryable: bool = True
    missing_params: List[str] = None
    invalid_params: Dict[str, str] = None

    def __post_init__(self):
        """Initialize mutable default fields."""
        if self.missing_params is None:
            self.missing_params = []
        if self.invalid_params is None:
            self.invalid_params = {}


class ToolCallValidator:
    """Validates tool calls against tool definitions.

    Implements validation patterns from Research/ToolCallingPrompts.md for
    reliable offline tool calling with hallucination prevention.
    """

    def __init__(self, tools: List[Dict[str, Any]]) -> None:
        """Initialize validator with tool definitions.

        Args:
            tools: List of tool definitions in OpenAI/Anthropic format:
                [{"type": "function", "function": {"name": "...", "parameters": {...}}}]
        """
        self._tools: Dict[str, Dict[str, Any]] = {}

        # Index tools by name for fast lookup
        for tool in tools:
            if tool.get("type") == "function":
                func_def = tool.get("function", {})
                tool_name = func_def.get("name")
                if tool_name:
                    self._tools[tool_name] = func_def

        logger.debug(f"Initialized validator with {len(self._tools)} tools")

    def validate_tool_call(
        self, tool_name: str, parameters: Dict[str, Any]
    ) -> ValidationResult:
        """Validate a tool call against registered tool definitions.

        Args:
            tool_name: Name of the tool to call
            parameters: Tool parameters to validate

        Returns:
            ValidationResult with success status and error details
        """
        # Check 1: Tool exists
        if tool_name not in self._tools:
            return ValidationResult(
                valid=False,
                error_message=f"Tool '{tool_name}' does not exist. Available tools: {list(self._tools.keys())}",
                is_retryable=True,
            )

        tool_def = self._tools[tool_name]
        param_schema = tool_def.get("parameters", {})

        # Check 2: Required parameters are present
        required_params = param_schema.get("required", [])
        missing_params = []

        for param in required_params:
            if param not in parameters:
                missing_params.append(param)

        if missing_params:
            return ValidationResult(
                valid=False,
                error_message=(
                    f"Missing required parameters for '{tool_name}': {missing_params}. "
                    f"Required: {required_params}"
                ),
                is_retryable=True,
                missing_params=missing_params,
            )

        # Check 3: Parameter types match schema
        properties = param_schema.get("properties", {})
        invalid_params = {}

        for param_name, param_value in parameters.items():
            # Skip validation for unknown parameters (they'll be caught later if strict)
            if param_name not in properties:
                logger.warning(
                    f"Unknown parameter '{param_name}' for tool '{tool_name}'"
                )
                continue

            expected_type = properties[param_name].get("type")
            if expected_type:
                type_valid, error_msg = self._validate_parameter_type(
                    param_name, param_value, expected_type, properties[param_name]
                )
                if not type_valid:
                    invalid_params[param_name] = error_msg

        if invalid_params:
            error_details = "; ".join(
                [f"{param}: {msg}" for param, msg in invalid_params.items()]
            )
            return ValidationResult(
                valid=False,
                error_message=f"Type validation failed for '{tool_name}': {error_details}",
                is_retryable=True,
                invalid_params=invalid_params,
            )

        # All validations passed
        logger.debug(f"Tool call validated successfully: {tool_name}({parameters})")
        return ValidationResult(valid=True)

    def _validate_parameter_type(
        self,
        param_name: str,
        param_value: Any,
        expected_type: str,
        param_schema: Dict[str, Any],
    ) -> tuple[bool, str]:
        """Validate a single parameter's type.

        Args:
            param_name: Name of the parameter
            param_value: Value to validate
            expected_type: Expected JSON schema type (string, number, integer, boolean, array, object)
            param_schema: Full parameter schema with additional constraints

        Returns:
            (is_valid, error_message) tuple
        """
        # Type mapping from JSON Schema to Python types
        type_map = {
            "string": str,
            "number": (int, float),
            "integer": int,
            "boolean": bool,
            "array": list,
            "object": dict,
        }

        if expected_type not in type_map:
            # Unknown type, skip validation
            return True, ""

        expected_python_type = type_map[expected_type]
        actual_type = type(param_value).__name__

        # Check type match
        if not isinstance(param_value, expected_python_type):
            return False, f"Expected {expected_type}, got {actual_type}"

        # Additional validation for specific types
        if expected_type == "string":
            # Check enum constraints
            enum_values = param_schema.get("enum")
            if enum_values and param_value not in enum_values:
                return False, f"Must be one of {enum_values}, got '{param_value}'"

            # Check minLength/maxLength
            min_length = param_schema.get("minLength")
            max_length = param_schema.get("maxLength")
            if min_length and len(param_value) < min_length:
                return False, f"Minimum length {min_length}, got {len(param_value)}"
            if max_length and len(param_value) > max_length:
                return False, f"Maximum length {max_length}, got {len(param_value)}"

        elif expected_type in ("number", "integer"):
            # Check minimum/maximum
            minimum = param_schema.get("minimum")
            maximum = param_schema.get("maximum")
            if minimum is not None and param_value < minimum:
                return False, f"Minimum value {minimum}, got {param_value}"
            if maximum is not None and param_value > maximum:
                return False, f"Maximum value {maximum}, got {param_value}"

        elif expected_type == "array":
            # Check minItems/maxItems
            min_items = param_schema.get("minItems")
            max_items = param_schema.get("maxItems")
            if min_items and len(param_value) < min_items:
                return False, f"Minimum items {min_items}, got {len(param_value)}"
            if max_items and len(param_value) > max_items:
                return False, f"Maximum items {max_items}, got {len(param_value)}"

        return True, ""

    def get_recovery_prompt(self, validation_result: ValidationResult) -> str:
        """Generate a recovery prompt for invalid tool calls.

        This prompt can be injected into the conversation to help the model
        correct its tool call error.

        Args:
            validation_result: Failed validation result

        Returns:
            Recovery prompt with specific error details
        """
        if validation_result.valid:
            return ""

        prompt = f"""Tool call validation failed: {validation_result.error_message}

## Corrective Action Required
1. Do NOT repeat the same error
2. Review the tool requirements carefully
3. Either:
   a) Call the tool with corrected parameters
   b) Provide a direct text answer if no tool is appropriate

Remember:
- All required parameters must be provided
- Parameter types must match exactly
- Tool names must be spelled correctly
- Do NOT make up parameter values you don't have"""

        if validation_result.missing_params:
            prompt += f"\n\nMissing parameters: {validation_result.missing_params}"

        if validation_result.invalid_params:
            prompt += f"\n\nInvalid parameters: {validation_result.invalid_params}"

        return prompt

    def should_retry(self, validation_result: ValidationResult) -> bool:
        """Determine if a failed validation should trigger a retry.

        Args:
            validation_result: Failed validation result

        Returns:
            True if error is retryable, False otherwise
        """
        return validation_result.is_retryable

    def get_tool_schema(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """Get the full schema for a specific tool.

        Args:
            tool_name: Name of the tool

        Returns:
            Tool schema or None if tool doesn't exist
        """
        return self._tools.get(tool_name)

    def list_available_tools(self) -> List[str]:
        """List names of all available tools.

        Returns:
            List of tool names
        """
        return list(self._tools.keys())


__all__ = ["ToolCallValidator", "ValidationResult"]
