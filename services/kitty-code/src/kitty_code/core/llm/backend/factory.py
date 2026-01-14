from __future__ import annotations

from typing import TYPE_CHECKING

from kitty_code.core.config import Backend
from kitty_code.core.llm.backend.generic import GenericBackend

if TYPE_CHECKING:
    from kitty_code.core.llm.backend.mistral import MistralBackend


def _get_mistral_backend() -> type[MistralBackend]:
    """Lazy import MistralBackend to avoid requiring mistralai dependency at startup."""
    try:
        from kitty_code.core.llm.backend.mistral import MistralBackend
        return MistralBackend
    except ImportError as e:
        raise ImportError(
            "MistralBackend requires the 'mistralai' package. "
            "Install it with: pip install kitty-code[cloud] or pip install mistralai"
        ) from e


class _LazyBackendFactory(dict):
    """Factory that lazily loads optional backends on first access."""

    def __getitem__(self, key: Backend):
        if key == Backend.MISTRAL:
            return _get_mistral_backend()
        return super().__getitem__(key)


BACKEND_FACTORY = _LazyBackendFactory({Backend.GENERIC: GenericBackend})
