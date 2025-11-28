# noqa: D401
"""Tool embedding manager for semantic tool selection.

Uses SentenceTransformer embeddings with Redis caching for cluster-wide sharing.
Reduces context usage by ~90% when many tools are available.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Dict, List, Optional

import numpy as np
import redis

from common.config import settings

logger = logging.getLogger(__name__)

# Singleton instance
_embedding_manager: Optional[ToolEmbeddingManager] = None


class ToolEmbeddingManager:
    """Manages tool embeddings with Redis caching for cluster support.

    Features:
    - Lazy-loads embedding model (~80MB, ~2s first load)
    - Caches embeddings to Redis for cluster-wide sharing
    - Fast cosine similarity search
    - Automatic cache invalidation via hash comparison
    """

    REDIS_PREFIX = "kitt:tool_embeddings:"
    META_KEY = "kitt:tool_embeddings:_meta"
    DEFAULT_MODEL = "all-MiniLM-L6-v2"

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        redis_url: Optional[str] = None,
    ) -> None:
        """Initialize embedding manager.

        Args:
            model_name: SentenceTransformer model name
            redis_url: Redis connection URL (defaults to settings.redis_url)
        """
        self._model_name = model_name
        self._model = None  # Lazy load
        self._redis = redis.from_url(
            redis_url or settings.redis_url,
            decode_responses=False  # We store binary numpy arrays
        )
        self._tool_embeddings: Dict[str, np.ndarray] = {}
        self._tools_by_name: Dict[str, Dict[str, Any]] = {}

        logger.info(f"ToolEmbeddingManager initialized with model: {model_name}")

    def _load_model(self):
        """Lazy-load embedding model (~80MB, ~2s first load)."""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                logger.info(f"Loading SentenceTransformer model: {self._model_name}")
                self._model = SentenceTransformer(self._model_name)
                logger.info("SentenceTransformer model loaded successfully")
            except ImportError:
                logger.error(
                    "sentence-transformers not installed. "
                    "Run: pip install sentence-transformers"
                )
                raise
        return self._model

    def _tool_to_text(self, tool: Dict[str, Any]) -> str:
        """Convert tool definition to searchable text.

        Combines tool name, description, and parameter info for embedding.

        Args:
            tool: Tool definition in OpenAI format

        Returns:
            Text representation for embedding
        """
        func = tool.get("function", tool)  # Handle both wrapped and unwrapped formats
        name = func.get("name", "")
        description = func.get("description", "")

        text_parts = [f"Tool: {name}", f"Description: {description}"]

        # Add parameter information for richer embeddings
        params = func.get("parameters", {}).get("properties", {})
        if params:
            param_descriptions = []
            for param_name, param_info in params.items():
                param_desc = param_info.get("description", "")
                param_type = param_info.get("type", "")
                param_descriptions.append(f"{param_name} ({param_type}): {param_desc}")

            if param_descriptions:
                text_parts.append("Parameters: " + ", ".join(param_descriptions))

        return "\n".join(text_parts)

    def _get_tool_name(self, tool: Dict[str, Any]) -> str:
        """Extract tool name from definition."""
        func = tool.get("function", tool)
        return func.get("name", "")

    def _compute_tools_hash(self, tools: List[Dict[str, Any]]) -> str:
        """Compute hash of tool definitions for cache invalidation."""
        # Sort by name for consistent hashing
        sorted_tools = sorted(tools, key=lambda t: self._get_tool_name(t))
        tools_json = json.dumps(sorted_tools, sort_keys=True)
        return hashlib.sha256(tools_json.encode()).hexdigest()[:16]

    def _load_from_redis(self, tool_names: List[str]) -> bool:
        """Load cached embeddings from Redis.

        Args:
            tool_names: List of tool names to load

        Returns:
            True if all embeddings were found in cache
        """
        all_found = True
        for name in tool_names:
            key = f"{self.REDIS_PREFIX}{name}"
            data = self._redis.get(key)
            if data:
                self._tool_embeddings[name] = np.frombuffer(data, dtype=np.float32)
            else:
                all_found = False
        return all_found

    def _save_to_redis(self, tool_name: str, embedding: np.ndarray) -> None:
        """Save embedding to Redis.

        Args:
            tool_name: Tool name
            embedding: Embedding vector
        """
        key = f"{self.REDIS_PREFIX}{tool_name}"
        self._redis.set(key, embedding.astype(np.float32).tobytes())

    def _save_meta(self, tools_hash: str, count: int) -> None:
        """Save metadata to Redis for cache validation."""
        meta = {
            "version": "v1",
            "model": self._model_name,
            "count": count,
            "hash": tools_hash,
        }
        self._redis.set(self.META_KEY, json.dumps(meta).encode())

    def _get_meta(self) -> Optional[Dict[str, Any]]:
        """Get metadata from Redis."""
        data = self._redis.get(self.META_KEY)
        if data:
            return json.loads(data.decode())
        return None

    def compute_embeddings(self, tools: List[Dict[str, Any]]) -> None:
        """Pre-compute embeddings for all tools, using Redis cache.

        Args:
            tools: List of tool definitions in OpenAI format
        """
        if not tools:
            logger.warning("No tools provided to compute embeddings")
            return

        # Build name -> tool mapping
        self._tools_by_name = {self._get_tool_name(t): t for t in tools}
        tool_names = list(self._tools_by_name.keys())
        tools_hash = self._compute_tools_hash(tools)

        # Check if cached embeddings are still valid
        meta = self._get_meta()
        if meta and meta.get("hash") == tools_hash:
            # Try to load from Redis
            if self._load_from_redis(tool_names):
                logger.info(
                    f"Loaded {len(tool_names)} tool embeddings from Redis cache"
                )
                return

        # Hash changed or cache miss - clear stale embeddings before recomputing
        if meta and meta.get("hash") != tools_hash:
            logger.info(
                f"Tool set changed (hash {meta.get('hash')[:8]}... → {tools_hash[:8]}...), "
                "clearing stale cache"
            )
            self.clear_cache()

        # Need to compute embeddings
        logger.info(f"Computing embeddings for {len(tools)} tools")
        model = self._load_model()

        # Convert tools to text and compute embeddings
        tool_texts = [self._tool_to_text(t) for t in tools]
        embeddings = model.encode(tool_texts, convert_to_numpy=True, normalize_embeddings=True)

        # Store in memory and Redis
        for i, name in enumerate(tool_names):
            embedding = embeddings[i]
            self._tool_embeddings[name] = embedding
            self._save_to_redis(name, embedding)

        # Save metadata
        self._save_meta(tools_hash, len(tools))
        logger.info(f"Computed and cached embeddings for {len(tools)} tools")

    def search(
        self,
        query: str,
        top_k: int = 5,
        threshold: float = 0.3,
    ) -> List[Dict[str, Any]]:
        """Find most relevant tools for a query using cosine similarity.

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

        # Embed the query
        model = self._load_model()
        query_embedding = model.encode(query, convert_to_numpy=True, normalize_embeddings=True)

        # Calculate cosine similarity (dot product since embeddings are normalized)
        similarities = {}
        for name, tool_embedding in self._tool_embeddings.items():
            similarity = float(np.dot(query_embedding, tool_embedding))
            similarities[name] = similarity

        # Sort by similarity (highest first)
        sorted_tools = sorted(similarities.items(), key=lambda x: x[1], reverse=True)

        # Filter by threshold and take top_k
        results = []
        for name, score in sorted_tools[:top_k]:
            if score >= threshold:
                tool = self._tools_by_name.get(name)
                if tool:
                    results.append(tool)
                    logger.debug(f"Tool match: {name} (score: {score:.3f})")

        # If no tools meet threshold, return top_k regardless (fallback)
        if not results and sorted_tools:
            logger.info(
                f"No tools above threshold {threshold}, "
                f"returning top {top_k} regardless"
            )
            for name, score in sorted_tools[:top_k]:
                tool = self._tools_by_name.get(name)
                if tool:
                    results.append(tool)

        logger.info(
            f"Tool search for '{query[:50]}...' returned {len(results)} tools"
        )
        return results

    def get_tool_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Get a specific tool by name.

        Args:
            name: Tool name

        Returns:
            Tool definition or None if not found
        """
        return self._tools_by_name.get(name)

    def clear_cache(self) -> int:
        """Clear all cached embeddings from Redis.

        Returns:
            Number of keys deleted
        """
        keys = list(self._redis.scan_iter(f"{self.REDIS_PREFIX}*"))
        if keys:
            deleted = self._redis.delete(*keys)
            logger.info(f"Cleared {deleted} embedding cache keys")
            return deleted
        return 0


def get_embedding_manager() -> ToolEmbeddingManager:
    """Get the singleton embedding manager instance.

    Returns:
        ToolEmbeddingManager instance
    """
    global _embedding_manager
    if _embedding_manager is None:
        _embedding_manager = ToolEmbeddingManager()
    return _embedding_manager


__all__ = [
    "ToolEmbeddingManager",
    "get_embedding_manager",
]
