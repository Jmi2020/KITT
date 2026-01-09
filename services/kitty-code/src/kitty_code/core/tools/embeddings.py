"""Semantic tool search using sentence embeddings.

Provides accuracy-focused tool selection by understanding
semantic similarity between queries and tool descriptions.
Uses disk-based caching for persistence across restarts.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
import pickle
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from kitty_code.core.types import AvailableTool

logger = logging.getLogger(__name__)


class ToolEmbeddingManager:
    """Manages tool embeddings with disk caching.

    Features:
    - Lazy-loads SentenceTransformer model (~80MB, ~2s first load)
    - Caches embeddings to disk for persistence across restarts
    - Fast cosine similarity search using normalized embeddings
    - Automatic cache invalidation via tool set hash comparison
    """

    DEFAULT_MODEL = "all-MiniLM-L6-v2"
    CACHE_FILE = "tool_embeddings.pkl"

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        cache_dir: Path | None = None,
    ) -> None:
        """Initialize embedding manager.

        Args:
            model_name: SentenceTransformer model name
            cache_dir: Directory for embedding cache (defaults to ~/.kitty-code/cache)
        """
        self._model_name = model_name
        self._model: Any = None  # Lazy load
        self._cache_dir = cache_dir or Path.home() / ".kitty-code" / "cache"
        self._tool_embeddings: dict[str, Any] = {}  # name -> numpy array
        self._tools_by_name: dict[str, AvailableTool] = {}
        self._tools_hash: str = ""

        logger.debug(f"ToolEmbeddingManager initialized with model: {model_name}")

    def _load_model(self) -> Any:
        """Lazy-load SentenceTransformer model (~80MB, ~2s first load)."""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer

                logger.info(f"Loading SentenceTransformer: {self._model_name}")
                self._model = SentenceTransformer(self._model_name)
                logger.info("SentenceTransformer model loaded successfully")
            except ImportError:
                logger.error(
                    "sentence-transformers not installed. "
                    "Install with: pip install sentence-transformers"
                )
                raise
        return self._model

    def _tool_to_text(self, tool: AvailableTool) -> str:
        """Convert tool definition to searchable text.

        Combines tool name, description, and parameter info for embedding.
        Richer text produces better semantic matching.

        Args:
            tool: Tool definition

        Returns:
            Text representation for embedding
        """
        func = tool.function
        parts = [f"Tool: {func.name}"]

        if func.description:
            parts.append(f"Description: {func.description}")

        # Include parameter descriptions for richer embeddings
        params = func.parameters.get("properties", {})
        if params:
            param_descs = []
            for name, info in params.items():
                if isinstance(info, dict):
                    desc = info.get("description", "")
                    param_type = info.get("type", "")
                    param_descs.append(f"{name} ({param_type}): {desc}")
            if param_descs:
                parts.append("Parameters: " + ", ".join(param_descs))

        return "\n".join(parts)

    def _compute_hash(self, tools: list[AvailableTool]) -> str:
        """Compute hash of tool set for cache invalidation.

        Args:
            tools: List of tool definitions

        Returns:
            Short hash string for comparison
        """
        sorted_names = sorted(t.function.name for t in tools)
        return hashlib.sha256("|".join(sorted_names).encode()).hexdigest()[:16]

    def _load_cache(self) -> bool:
        """Load embeddings from disk cache.

        Returns:
            True if cache was loaded successfully and hash matches
        """
        cache_path = self._cache_dir / self.CACHE_FILE
        if not cache_path.exists():
            return False

        try:
            with open(cache_path, "rb") as f:
                data = pickle.load(f)

            # Validate cache hash matches current tool set
            if data.get("hash") != self._tools_hash:
                logger.debug("Cache hash mismatch, will recompute embeddings")
                return False

            self._tool_embeddings = data.get("embeddings", {})
            logger.info(
                f"Loaded {len(self._tool_embeddings)} tool embeddings from cache"
            )
            return True

        except Exception as e:
            logger.warning(f"Failed to load embedding cache: {e}")
            return False

    def _save_cache(self) -> None:
        """Save embeddings to disk cache."""
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path = self._cache_dir / self.CACHE_FILE

        try:
            with open(cache_path, "wb") as f:
                pickle.dump(
                    {
                        "hash": self._tools_hash,
                        "embeddings": self._tool_embeddings,
                        "model": self._model_name,
                    },
                    f,
                )
            logger.info(f"Saved {len(self._tool_embeddings)} tool embeddings to cache")
        except Exception as e:
            logger.warning(f"Failed to save embedding cache: {e}")

    def compute_embeddings(self, tools: list[AvailableTool]) -> None:
        """Pre-compute embeddings for all tools.

        Uses disk cache if available and valid, otherwise computes fresh.

        Args:
            tools: List of tool definitions
        """
        if not tools:
            logger.warning("No tools provided to compute embeddings")
            return

        # Build name -> tool mapping
        self._tools_by_name = {t.function.name: t for t in tools}
        self._tools_hash = self._compute_hash(tools)

        # Try loading from cache first
        if self._load_cache():
            return

        # Compute fresh embeddings
        logger.info(f"Computing embeddings for {len(tools)} tools")
        model = self._load_model()

        texts = [self._tool_to_text(t) for t in tools]
        embeddings = model.encode(
            texts, convert_to_numpy=True, normalize_embeddings=True
        )

        for i, tool in enumerate(tools):
            self._tool_embeddings[tool.function.name] = embeddings[i]

        # Save to cache for next startup
        self._save_cache()
        logger.info(f"Computed and cached embeddings for {len(tools)} tools")

    def search(
        self,
        query: str,
        top_k: int = 10,
        threshold: float = 0.25,
    ) -> list[AvailableTool]:
        """Find most relevant tools using cosine similarity.

        Args:
            query: Natural language query
            top_k: Maximum number of tools to return
            threshold: Minimum similarity score (0-1)

        Returns:
            List of tool definitions most relevant to the query
        """
        if not self._tool_embeddings:
            logger.warning("No tool embeddings available, returning empty list")
            return []

        import numpy as np

        model = self._load_model()
        query_embedding = model.encode(
            query, convert_to_numpy=True, normalize_embeddings=True
        )

        # Cosine similarity (dot product for normalized vectors)
        similarities: dict[str, float] = {}
        for name, tool_embedding in self._tool_embeddings.items():
            similarity = float(np.dot(query_embedding, tool_embedding))
            similarities[name] = similarity

        # Sort by similarity (highest first)
        sorted_tools = sorted(similarities.items(), key=lambda x: x[1], reverse=True)

        # Filter by threshold and take top_k
        results: list[AvailableTool] = []
        for name, score in sorted_tools[:top_k]:
            if score >= threshold:
                tool = self._tools_by_name.get(name)
                if tool:
                    results.append(tool)
                    logger.debug(f"Semantic match: {name} (score: {score:.3f})")

        # Fallback: return top_k if nothing meets threshold
        if not results and sorted_tools:
            logger.info(
                f"No tools above threshold {threshold}, returning top {top_k}"
            )
            for name, score in sorted_tools[:top_k]:
                tool = self._tools_by_name.get(name)
                if tool:
                    results.append(tool)
                    logger.debug(f"Fallback match: {name} (score: {score:.3f})")

        logger.info(
            f"Semantic search for '{query[:50]}...' returned {len(results)} tools"
        )
        return results

    def get_similarity_scores(
        self, query: str
    ) -> list[tuple[str, float]]:
        """Get similarity scores for all tools (for debugging).

        Args:
            query: Natural language query

        Returns:
            List of (tool_name, score) tuples sorted by score descending
        """
        if not self._tool_embeddings:
            return []

        import numpy as np

        model = self._load_model()
        query_embedding = model.encode(
            query, convert_to_numpy=True, normalize_embeddings=True
        )

        similarities: dict[str, float] = {}
        for name, tool_embedding in self._tool_embeddings.items():
            similarity = float(np.dot(query_embedding, tool_embedding))
            similarities[name] = similarity

        return sorted(similarities.items(), key=lambda x: x[1], reverse=True)

    def clear_cache(self) -> bool:
        """Clear the disk cache.

        Returns:
            True if cache was cleared
        """
        cache_path = self._cache_dir / self.CACHE_FILE
        if cache_path.exists():
            try:
                cache_path.unlink()
                self._tool_embeddings.clear()
                logger.info("Cleared embedding cache")
                return True
            except Exception as e:
                logger.warning(f"Failed to clear cache: {e}")
                return False
        return False


# Singleton instance
_manager: ToolEmbeddingManager | None = None


def get_embedding_manager() -> ToolEmbeddingManager:
    """Get the singleton embedding manager instance.

    Returns:
        ToolEmbeddingManager instance
    """
    global _manager
    if _manager is None:
        _manager = ToolEmbeddingManager()
    return _manager


__all__ = [
    "ToolEmbeddingManager",
    "get_embedding_manager",
]
