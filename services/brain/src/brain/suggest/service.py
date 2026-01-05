# noqa: D401
"""Prompt suggestion service with model routing.

Routes suggestion requests to appropriate models:
- Gemma 3 21B for general contexts (chat, cad, image, research)
- Qwen2.5-Coder-32B for coding context
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any, AsyncIterator, Dict, List, Optional

from .contexts import SuggestionContext, get_system_prompt, get_context_from_string

logger = logging.getLogger(__name__)

# Model configuration
GEMMA_MODEL_PATH = os.getenv(
    "PROMPT_SUGGEST_MODEL",
    "gemma-3-21b"  # Model alias or path
)
QWEN_CODER_MODEL_PATH = os.getenv(
    "PROMPT_SUGGEST_CODER_MODEL",
    "/Users/Shared/Coding/models/Qwen2.5-Coder-32B-Instruct-GGUF"
)

# Feature configuration
SUGGEST_ENABLED = os.getenv("ENABLE_PROMPT_SUGGESTIONS", "true").lower() == "true"
SUGGEST_MAX_TOKENS = int(os.getenv("PROMPT_SUGGEST_MAX_TOKENS", "512"))
SUGGEST_TEMPERATURE = float(os.getenv("PROMPT_SUGGEST_TEMPERATURE", "0.7"))
SUGGEST_CODER_TEMPERATURE = float(os.getenv("PROMPT_SUGGEST_CODER_TEMPERATURE", "0.3"))


@dataclass
class Suggestion:
    """A single prompt suggestion."""

    text: str
    reason: str


@dataclass
class SuggestionEvent:
    """Event emitted during suggestion streaming."""

    type: str  # 'start', 'suggestion', 'complete', 'error'
    request_id: Optional[str] = None
    index: Optional[int] = None
    text: Optional[str] = None
    reason: Optional[str] = None
    suggestions_count: Optional[int] = None
    error: Optional[str] = None


class PromptSuggestionService:
    """Service for generating context-aware prompt suggestions."""

    def __init__(self):
        """Initialize the suggestion service."""
        self._llm_client = None
        self._ollama_client = None
        logger.info(
            f"PromptSuggestionService initialized (enabled={SUGGEST_ENABLED}, "
            f"default_model={GEMMA_MODEL_PATH}, coder_model={QWEN_CODER_MODEL_PATH})"
        )

    def _get_model_for_context(self, context: SuggestionContext) -> tuple[str, float]:
        """Get the model path and temperature for a given context.

        Args:
            context: The suggestion context

        Returns:
            Tuple of (model_path_or_alias, temperature)
        """
        if context == SuggestionContext.CODING:
            return QWEN_CODER_MODEL_PATH, SUGGEST_CODER_TEMPERATURE
        return GEMMA_MODEL_PATH, SUGGEST_TEMPERATURE

    async def _get_llm_client(self):
        """Get or create the LLM client for suggestions."""
        if self._llm_client is None:
            # Import here to avoid circular imports
            from brain.routing.multi_server_client import MultiServerLlamaCppClient
            self._llm_client = MultiServerLlamaCppClient()
        return self._llm_client

    async def _get_ollama_client(self):
        """Get or create the Ollama client for Gemma model."""
        if self._ollama_client is None:
            from brain.routing.ollama_client import OllamaReasonerClient
            ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
            self._ollama_client = OllamaReasonerClient(
                base_url=ollama_host,
                model=GEMMA_MODEL_PATH,
                timeout_s=30,
            )
        return self._ollama_client

    async def suggest(
        self,
        input_text: str,
        context: str,
        field_id: str = "",
        history: Optional[List[Dict[str, str]]] = None,
        max_suggestions: int = 3,
    ) -> AsyncIterator[SuggestionEvent]:
        """Generate prompt suggestions as a stream.

        Args:
            input_text: The user's current input
            context: The context type (chat, coding, cad, image, research)
            field_id: Optional field identifier for analytics
            history: Optional conversation history
            max_suggestions: Maximum number of suggestions to generate

        Yields:
            SuggestionEvent objects as they are generated
        """
        import uuid
        request_id = str(uuid.uuid4())[:8]

        # Check if feature is enabled
        if not SUGGEST_ENABLED:
            yield SuggestionEvent(type="error", error="Prompt suggestions are disabled")
            return

        # Validate input
        if not input_text or len(input_text.strip()) < 5:
            yield SuggestionEvent(type="error", error="Input too short for suggestions")
            return

        # Parse context
        ctx = get_context_from_string(context)
        model_path, temperature = self._get_model_for_context(ctx)

        # Get system prompt
        system_prompt = get_system_prompt(ctx, input_text)

        logger.info(
            f"Generating suggestions: context={ctx.value}, model={model_path}, "
            f"input_len={len(input_text)}, request_id={request_id}"
        )

        yield SuggestionEvent(type="start", request_id=request_id)

        try:
            # Generate suggestions using the appropriate model
            suggestions = await self._generate_suggestions(
                system_prompt=system_prompt,
                model_path=model_path,
                temperature=temperature,
                max_suggestions=max_suggestions,
                context=ctx,
            )

            # Emit each suggestion
            for idx, suggestion in enumerate(suggestions[:max_suggestions]):
                yield SuggestionEvent(
                    type="suggestion",
                    index=idx,
                    text=suggestion.text,
                    reason=suggestion.reason,
                )

            yield SuggestionEvent(
                type="complete",
                suggestions_count=len(suggestions),
            )

        except Exception as e:
            logger.error(f"Error generating suggestions: {e}", exc_info=True)
            yield SuggestionEvent(type="error", error=str(e))

    async def _generate_suggestions(
        self,
        system_prompt: str,
        model_path: str,
        temperature: float,
        max_suggestions: int,
        context: SuggestionContext,
    ) -> List[Suggestion]:
        """Generate suggestions using the LLM.

        Args:
            system_prompt: The formatted system prompt
            model_path: Path or alias of the model to use
            temperature: Sampling temperature
            max_suggestions: Maximum suggestions to generate
            context: The suggestion context

        Returns:
            List of Suggestion objects
        """
        try:
            # Try using Ollama for Gemma model
            if "gemma" in model_path.lower():
                return await self._generate_with_ollama(
                    system_prompt, model_path, temperature, max_suggestions
                )
            else:
                # Use llama.cpp for other models (e.g., Qwen Coder)
                return await self._generate_with_llamacpp(
                    system_prompt, model_path, temperature, max_suggestions
                )
        except Exception as e:
            logger.warning(f"Primary model failed, trying fallback: {e}")
            # Fallback: try the other method
            try:
                if "gemma" in model_path.lower():
                    return await self._generate_with_llamacpp(
                        system_prompt, "kitty-q4", temperature, max_suggestions
                    )
                else:
                    return await self._generate_with_ollama(
                        system_prompt, GEMMA_MODEL_PATH, temperature, max_suggestions
                    )
            except Exception as fallback_error:
                logger.error(f"Fallback also failed: {fallback_error}")
                raise

    async def _generate_with_ollama(
        self,
        system_prompt: str,
        model: str,
        temperature: float,
        max_suggestions: int,
    ) -> List[Suggestion]:
        """Generate suggestions using Ollama."""
        from brain.routing.ollama_client import OllamaReasonerClient

        ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        client = OllamaReasonerClient(
            base_url=ollama_host,
            model=model,
            timeout_s=30,
        )

        # Generate response
        result = await client.generate(
            prompt=system_prompt,
            temperature=temperature,
            max_tokens=SUGGEST_MAX_TOKENS,
        )

        response_text = result.get("response", "")
        return self._parse_suggestions(response_text, max_suggestions)

    async def _generate_with_llamacpp(
        self,
        system_prompt: str,
        model: str,
        temperature: float,
        max_suggestions: int,
    ) -> List[Suggestion]:
        """Generate suggestions using llama.cpp."""
        client = await self._get_llm_client()

        result = await client.generate(
            prompt=system_prompt,
            model=model,
        )

        response_text = result.get("response", "")
        return self._parse_suggestions(response_text, max_suggestions)

    def _parse_suggestions(
        self,
        response_text: str,
        max_suggestions: int,
    ) -> List[Suggestion]:
        """Parse LLM response into Suggestion objects.

        Args:
            response_text: Raw LLM response
            max_suggestions: Maximum number of suggestions

        Returns:
            List of parsed Suggestion objects
        """
        suggestions: List[Suggestion] = []

        # Try to extract JSON from response
        try:
            # Handle potential markdown code blocks
            text = response_text.strip()
            if text.startswith("```"):
                # Remove markdown code block
                lines = text.split("\n")
                text = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])

            # Find JSON object
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                json_str = text[start:end]
                data = json.loads(json_str)

                if "suggestions" in data and isinstance(data["suggestions"], list):
                    for item in data["suggestions"][:max_suggestions]:
                        if isinstance(item, dict) and "text" in item:
                            suggestions.append(Suggestion(
                                text=item.get("text", ""),
                                reason=item.get("reason", ""),
                            ))

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse suggestions JSON: {e}")
            # Fallback: try to extract any reasonable text
            if response_text.strip():
                suggestions.append(Suggestion(
                    text=response_text.strip()[:500],
                    reason="Generated suggestion",
                ))

        return suggestions


# Global service instance
_suggestion_service: Optional[PromptSuggestionService] = None


def get_suggestion_service() -> PromptSuggestionService:
    """Get or create the global suggestion service instance."""
    global _suggestion_service
    if _suggestion_service is None:
        _suggestion_service = PromptSuggestionService()
    return _suggestion_service
