from __future__ import annotations

from kitty_code.core.config import Backend
from kitty_code.core.llm.backend.generic import GenericBackend
from kitty_code.core.llm.backend.mistral import MistralBackend

BACKEND_FACTORY = {Backend.MISTRAL: MistralBackend, Backend.GENERIC: GenericBackend}
