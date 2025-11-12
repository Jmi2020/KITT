"""MCP memory server using Qdrant for semantic storage and retrieval."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from sentence_transformers import SentenceTransformer


# Configuration
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
COLLECTION_NAME = os.getenv("QDRANT_COLLECTION", "kitty_memory")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "384"))


# Pydantic models
class MemoryAddRequest(BaseModel):
    """Request to add a memory."""

    conversation_id: str = Field(
        ..., description="Conversation ID this memory belongs to"
    )
    user_id: Optional[str] = Field(None, description="User ID who created this memory")
    content: str = Field(..., description="The memory content to store")
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )
    tags: Optional[List[str]] = Field(
        None, description="Tags for categorizing and filtering memories (e.g., meta, dev, domain)"
    )


class MemorySearchRequest(BaseModel):
    """Request to search memories."""

    query: str = Field(..., description="The search query")
    conversation_id: Optional[str] = Field(
        None, description="Filter by conversation ID"
    )
    user_id: Optional[str] = Field(None, description="Filter by user ID")
    limit: int = Field(5, ge=1, le=50, description="Maximum number of results")
    score_threshold: float = Field(
        0.7, ge=0.0, le=1.0, description="Minimum similarity score"
    )
    include_tags: Optional[List[str]] = Field(
        None, description="Only return memories with at least one of these tags"
    )
    exclude_tags: Optional[List[str]] = Field(
        None, description="Exclude memories with any of these tags"
    )


class Memory(BaseModel):
    """A memory record."""

    id: str
    conversation_id: str
    user_id: Optional[str]
    content: str
    metadata: Dict[str, Any]
    created_at: datetime
    score: Optional[float] = None


class MemorySearchResponse(BaseModel):
    """Response from memory search."""

    memories: List[Memory]
    count: int


# Global state
encoder_model: Optional[SentenceTransformer] = None
qdrant_client: Optional[AsyncQdrantClient] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and cleanup resources."""
    global encoder_model, qdrant_client

    # Initialize sentence transformer
    encoder_model = SentenceTransformer(EMBEDDING_MODEL)

    # Initialize Qdrant client
    qdrant_client = AsyncQdrantClient(url=QDRANT_URL)

    # Create collection if it doesn't exist
    collections = await qdrant_client.get_collections()
    collection_names = [c.name for c in collections.collections]

    if COLLECTION_NAME not in collection_names:
        await qdrant_client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
        )

    yield

    # Cleanup
    if qdrant_client:
        await qdrant_client.close()


app = FastAPI(
    title="KITTY Memory MCP",
    description="MCP-based memory service using Qdrant for semantic storage",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "collection": COLLECTION_NAME}


@app.post("/memory/add", response_model=Memory)
async def add_memory(request: MemoryAddRequest):
    """Add a new memory to the vector store."""
    if not encoder_model or not qdrant_client:
        raise HTTPException(status_code=500, detail="Service not initialized")

    # Generate embedding
    embedding = encoder_model.encode(request.content).tolist()

    # Create memory ID and timestamp
    memory_id = str(uuid4())
    created_at = datetime.utcnow()

    # Prepare payload with tags
    tags = request.tags if request.tags is not None else ["domain"]  # Default to domain tag
    payload = {
        "conversation_id": request.conversation_id,
        "user_id": request.user_id,
        "content": request.content,
        "metadata": request.metadata,
        "tags": tags,
        "created_at": created_at.isoformat(),
    }

    # Store in Qdrant
    point = PointStruct(
        id=memory_id,
        vector=embedding,
        payload=payload,
    )

    await qdrant_client.upsert(
        collection_name=COLLECTION_NAME,
        points=[point],
    )

    return Memory(
        id=memory_id,
        conversation_id=request.conversation_id,
        user_id=request.user_id,
        content=request.content,
        metadata=request.metadata,
        created_at=created_at,
    )


@app.post("/memory/search", response_model=MemorySearchResponse)
async def search_memories(request: MemorySearchRequest):
    """Search for relevant memories using semantic similarity."""
    if not encoder_model or not qdrant_client:
        raise HTTPException(status_code=500, detail="Service not initialized")

    # Generate query embedding
    query_embedding = encoder_model.encode(request.query).tolist()

    # Build filter
    filter_conditions = []
    if request.conversation_id:
        filter_conditions.append(
            {"key": "conversation_id", "match": {"value": request.conversation_id}}
        )
    if request.user_id:
        filter_conditions.append(
            {"key": "user_id", "match": {"value": request.user_id}}
        )

    query_filter = None
    if filter_conditions:
        query_filter = {"must": filter_conditions}

    # Search Qdrant with increased limit for post-filtering
    # We fetch more results than requested to account for tag filtering
    search_limit = request.limit * 3 if (request.include_tags or request.exclude_tags) else request.limit

    search_result = await qdrant_client.search(
        collection_name=COLLECTION_NAME,
        query_vector=query_embedding,
        query_filter=query_filter,
        limit=search_limit,
        score_threshold=request.score_threshold,
    )

    # Helper function to check if memory passes tag filters
    def passes_tag_filter(memory_tags: List[str]) -> bool:
        memory_tag_set = set(memory_tags or [])

        # If exclude_tags specified, reject if any match
        if request.exclude_tags:
            if memory_tag_set & set(request.exclude_tags):
                return False

        # If include_tags specified, require at least one match
        if request.include_tags:
            if not (memory_tag_set & set(request.include_tags)):
                return False

        return True

    # Convert results to Memory objects, filtering by tags
    memories = []
    for hit in search_result:
        payload = hit.payload
        memory_tags = payload.get("tags", [])

        # Apply tag filter
        if not passes_tag_filter(memory_tags):
            continue

        memories.append(
            Memory(
                id=str(hit.id),
                conversation_id=payload["conversation_id"],
                user_id=payload.get("user_id"),
                content=payload["content"],
                metadata=payload.get("metadata", {}),
                created_at=datetime.fromisoformat(payload["created_at"]),
                score=hit.score,
            )
        )

        # Stop once we have enough results
        if len(memories) >= request.limit:
            break

    return MemorySearchResponse(
        memories=memories,
        count=len(memories),
    )


@app.delete("/memory/{memory_id}")
async def delete_memory(memory_id: str):
    """Delete a specific memory."""
    if not qdrant_client:
        raise HTTPException(status_code=500, detail="Service not initialized")

    await qdrant_client.delete(
        collection_name=COLLECTION_NAME,
        points_selector=[memory_id],
    )

    return {"status": "deleted", "id": memory_id}


@app.get("/memory/stats")
async def get_memory_stats():
    """Get memory collection statistics."""
    if not qdrant_client:
        raise HTTPException(status_code=500, detail="Service not initialized")

    collection_info = await qdrant_client.get_collection(COLLECTION_NAME)

    return {
        "collection": COLLECTION_NAME,
        "vector_count": collection_info.points_count,
        "vector_dim": EMBEDDING_DIM,
        "embedding_model": EMBEDDING_MODEL,
    }


__all__ = ["app"]
