from __future__ import annotations

from typing import TYPE_CHECKING

from kitty_code.core.config import Backend
from kitty_code.core.llm.backend.generic import GenericBackend

if TYPE_CHECKING:
    from kitty_code.core.llm.backend.mistral import MistralBackend


def _get_mistral_backend():
    """Lazy import MistralBackend to avoid requiring mistralai when not used."""
    try:
        from kitty_code.core.llm.backend.mistral import MistralBackend
        return MistralBackend
    except ImportError:
        # mistralai not installed - return GenericBackend as fallback
        return GenericBackend


def get_backend(backend: Backend):
    """Get backend class for the given backend type."""
    if backend == Backend.MISTRAL:
        return _get_mistral_backend()
    return GenericBackend


# For backwards compatibility - lazy dict that resolves on access
class _LazyBackendFactory(dict):
    def __getitem__(self, key):
        return get_backend(key)


BACKEND_FACTORY = _LazyBackendFactory()
