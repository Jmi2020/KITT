"""Memory client for interacting with the MCP memory service."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import httpx
from pydantic import BaseModel


class Memory(BaseModel):
    """A memory record."""

    id: str
    conversation_id: str
    user_id: Optional[str]
    content: str
    metadata: Dict[str, Any]
    created_at: str
    score: Optional[float] = None


class MemoryClient:
    """Client for MCP memory service."""

    def __init__(self, base_url: Optional[str] = None):
        """Initialize memory client.

        Args:
            base_url: Base URL of the memory service (defaults to MEM0_MCP_URL env var)
        """
        self.base_url = base_url or os.getenv("MEM0_MCP_URL", "http://mem0-mcp:8765")
        self.timeout = 30.0

    async def add_memory(
        self,
        conversation_id: str,
        content: str,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Memory:
        """Add a new memory.

        Args:
            conversation_id: Conversation ID this memory belongs to
            content: The memory content to store
            user_id: Optional user ID
            metadata: Optional additional metadata

        Returns:
            The created memory record
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/memory/add",
                json={
                    "conversation_id": conversation_id,
                    "user_id": user_id,
                    "content": content,
                    "metadata": metadata or {},
                },
            )
            response.raise_for_status()
            return Memory(**response.json())

    async def search_memories(
        self,
        query: str,
        conversation_id: Optional[str] = None,
        user_id: Optional[str] = None,
        limit: int = 5,
        score_threshold: float = 0.7,
    ) -> List[Memory]:
        """Search for relevant memories.

        Args:
            query: The search query
            conversation_id: Optional filter by conversation ID
            user_id: Optional filter by user ID
            limit: Maximum number of results (1-50)
            score_threshold: Minimum similarity score (0.0-1.0)

        Returns:
            List of matching memory records
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/memory/search",
                json={
                    "query": query,
                    "conversation_id": conversation_id,
                    "user_id": user_id,
                    "limit": limit,
                    "score_threshold": score_threshold,
                },
            )
            response.raise_for_status()
            data = response.json()
            return [Memory(**m) for m in data["memories"]]

    async def delete_memory(self, memory_id: str) -> None:
        """Delete a specific memory.

        Args:
            memory_id: ID of the memory to delete
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.delete(f"{self.base_url}/memory/{memory_id}")
            response.raise_for_status()

    async def get_stats(self) -> Dict[str, Any]:
        """Get memory collection statistics.

        Returns:
            Statistics about the memory collection
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.base_url}/memory/stats")
            response.raise_for_status()
            return response.json()

    async def health_check(self) -> bool:
        """Check if memory service is healthy.

        Returns:
            True if service is healthy, False otherwise
        """
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/health")
                response.raise_for_status()
                return True
        except Exception:
            return False


__all__ = ["MemoryClient", "Memory"]
