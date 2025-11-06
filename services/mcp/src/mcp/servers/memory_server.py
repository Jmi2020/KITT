# noqa: D401
"""Memory MCP server providing semantic memory storage and retrieval tools."""

from __future__ import annotations

import os
from typing import Any, Dict

import httpx

from ..server import MCPServer, ResourceDefinition, ToolDefinition, ToolResult


class MemoryMCPServer(MCPServer):
    """MCP server for semantic memory operations using Qdrant vector storage."""

    def __init__(self, memory_service_url: str | None = None) -> None:
        """Initialize Memory MCP server.

        Args:
            memory_service_url: Base URL for memory service (default from env or http://mem0-mcp:8765)
        """
        super().__init__(
            name="memory",
            description="Store and retrieve semantic memories using vector similarity search",
        )

        self._memory_url = memory_service_url or os.getenv(
            "MEM0_MCP_URL", "http://mem0-mcp:8765"
        )

        # Register store_memory tool
        self.register_tool(
            ToolDefinition(
                name="store_memory",
                description="Store a memory in semantic vector storage. Memories are automatically embedded and can be retrieved later using semantic search.",
                parameters={
                    "type": "object",
                    "properties": {
                        "content": {
                            "type": "string",
                            "description": "The memory content to store (will be semantically embedded)",
                        },
                        "conversation_id": {
                            "type": "string",
                            "description": "Conversation ID this memory belongs to",
                        },
                        "user_id": {
                            "type": "string",
                            "description": "Optional user ID who created this memory",
                        },
                        "metadata": {
                            "type": "object",
                            "description": "Optional additional metadata to store with the memory",
                            "additionalProperties": True,
                        },
                    },
                    "required": ["content", "conversation_id"],
                },
            )
        )

        # Register recall_memory tool
        self.register_tool(
            ToolDefinition(
                name="recall_memory",
                description="Search for relevant memories using semantic similarity. Returns the most relevant memories matching the query.",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The search query (will be semantically matched against stored memories)",
                        },
                        "conversation_id": {
                            "type": "string",
                            "description": "Optional filter by conversation ID",
                        },
                        "user_id": {
                            "type": "string",
                            "description": "Optional filter by user ID",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of results to return (1-50)",
                            "minimum": 1,
                            "maximum": 50,
                            "default": 5,
                        },
                        "score_threshold": {
                            "type": "number",
                            "description": "Minimum similarity score threshold (0.0-1.0)",
                            "minimum": 0.0,
                            "maximum": 1.0,
                            "default": 0.7,
                        },
                    },
                    "required": ["query"],
                },
            )
        )

        # Register delete_memory tool
        self.register_tool(
            ToolDefinition(
                name="delete_memory",
                description="Delete a specific memory by its ID.",
                parameters={
                    "type": "object",
                    "properties": {
                        "memory_id": {
                            "type": "string",
                            "description": "The unique ID of the memory to delete",
                        },
                    },
                    "required": ["memory_id"],
                },
            )
        )

        # Register memory resources
        self.register_resource(
            ResourceDefinition(
                uri="memory://stats",
                name="memory_stats",
                description="Memory system statistics including vector count and embedding model info",
                mime_type="application/json",
            )
        )

    async def execute_tool(
        self, tool_name: str, arguments: Dict[str, Any]
    ) -> ToolResult:
        """Execute Memory tool.

        Args:
            tool_name: Name of the tool to execute
            arguments: Tool arguments

        Returns:
            ToolResult with success status and data/error
        """
        if tool_name == "store_memory":
            return await self._store_memory(arguments)
        elif tool_name == "recall_memory":
            return await self._recall_memory(arguments)
        elif tool_name == "delete_memory":
            return await self._delete_memory(arguments)

        return ToolResult(success=False, error=f"Unknown tool: {tool_name}")

    async def _store_memory(self, arguments: Dict[str, Any]) -> ToolResult:
        """Store a memory in vector storage.

        Args:
            arguments: Tool arguments with content, conversation_id, and optional user_id/metadata

        Returns:
            ToolResult with stored memory details
        """
        content = arguments.get("content")
        conversation_id = arguments.get("conversation_id")
        user_id = arguments.get("user_id")
        metadata = arguments.get("metadata", {})

        if not content or not conversation_id:
            return ToolResult(
                success=False,
                error="Missing required parameters: content, conversation_id",
            )

        try:
            # Call mem0-mcp service to add memory
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self._memory_url}/memory/add",
                    json={
                        "content": content,
                        "conversation_id": conversation_id,
                        "user_id": user_id,
                        "metadata": metadata,
                    },
                )
                response.raise_for_status()
                data = response.json()

            return ToolResult(
                success=True,
                data={
                    "memory_id": data.get("id"),
                    "content": data.get("content"),
                    "conversation_id": data.get("conversation_id"),
                    "user_id": data.get("user_id"),
                    "created_at": data.get("created_at"),
                    "metadata": data.get("metadata", {}),
                },
                metadata={"operation": "store"},
            )

        except httpx.HTTPStatusError as e:
            return ToolResult(
                success=False,
                error=f"Memory service returned error: {e.response.status_code} - {e.response.text}",
            )
        except httpx.RequestError as e:
            return ToolResult(
                success=False, error=f"Failed to connect to memory service: {str(e)}"
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to store memory: {str(e)}")

    async def _recall_memory(self, arguments: Dict[str, Any]) -> ToolResult:
        """Search for relevant memories using semantic similarity.

        Args:
            arguments: Tool arguments with query and optional filters

        Returns:
            ToolResult with matching memories and similarity scores
        """
        query = arguments.get("query")
        conversation_id = arguments.get("conversation_id")
        user_id = arguments.get("user_id")
        limit = arguments.get("limit", 5)
        score_threshold = arguments.get("score_threshold", 0.7)

        if not query:
            return ToolResult(success=False, error="Missing required parameter: query")

        try:
            # Call mem0-mcp service to search memories
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self._memory_url}/memory/search",
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

            memories = data.get("memories", [])

            return ToolResult(
                success=True,
                data={
                    "memories": [
                        {
                            "memory_id": mem.get("id"),
                            "content": mem.get("content"),
                            "conversation_id": mem.get("conversation_id"),
                            "user_id": mem.get("user_id"),
                            "created_at": mem.get("created_at"),
                            "score": mem.get("score"),
                            "metadata": mem.get("metadata", {}),
                        }
                        for mem in memories
                    ],
                    "count": data.get("count", 0),
                },
                metadata={
                    "operation": "recall",
                    "query": query,
                    "results_returned": len(memories),
                },
            )

        except httpx.HTTPStatusError as e:
            return ToolResult(
                success=False,
                error=f"Memory service returned error: {e.response.status_code} - {e.response.text}",
            )
        except httpx.RequestError as e:
            return ToolResult(
                success=False, error=f"Failed to connect to memory service: {str(e)}"
            )
        except Exception as e:
            return ToolResult(
                success=False, error=f"Failed to recall memories: {str(e)}"
            )

    async def _delete_memory(self, arguments: Dict[str, Any]) -> ToolResult:
        """Delete a specific memory.

        Args:
            arguments: Tool arguments with memory_id

        Returns:
            ToolResult with deletion confirmation
        """
        memory_id = arguments.get("memory_id")

        if not memory_id:
            return ToolResult(
                success=False, error="Missing required parameter: memory_id"
            )

        try:
            # Call mem0-mcp service to delete memory
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.delete(f"{self._memory_url}/memory/{memory_id}")
                response.raise_for_status()
                data = response.json()

            return ToolResult(
                success=True,
                data={
                    "memory_id": data.get("id"),
                    "status": data.get("status"),
                },
                metadata={"operation": "delete"},
            )

        except httpx.HTTPStatusError as e:
            return ToolResult(
                success=False,
                error=f"Memory service returned error: {e.response.status_code} - {e.response.text}",
            )
        except httpx.RequestError as e:
            return ToolResult(
                success=False, error=f"Failed to connect to memory service: {str(e)}"
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to delete memory: {str(e)}")

    async def fetch_resource(self, uri: str) -> Dict[str, Any]:
        """Fetch a Memory resource by URI.

        Args:
            uri: Resource URI (e.g., "memory://stats")

        Returns:
            Resource data as dictionary
        """
        if uri == "memory://stats":
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.get(f"{self._memory_url}/memory/stats")
                    response.raise_for_status()
                    return response.json()
            except Exception as e:
                raise ValueError(f"Failed to fetch memory stats: {str(e)}")

        raise ValueError(f"Unknown resource URI: {uri}")


__all__ = ["MemoryMCPServer"]
