# noqa: D401
"""Prompt suggestion and enhancement module.

Provides intelligent prompt suggestions as users type in various input fields
across the KITT Web UI and Shell interfaces.
"""

from .service import PromptSuggestionService
from .contexts import SuggestionContext, CONTEXT_PROMPTS
from .router import router

__all__ = [
    "PromptSuggestionService",
    "SuggestionContext",
    "CONTEXT_PROMPTS",
    "router",
]
