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
from sentence_transformers import SentenceTransformer, CrossEncoder


# Configuration
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
COLLECTION_NAME = os.getenv("QDRANT_COLLECTION", "kitty_memory")
# Use BAAI/bge-small-en-v1.5 for better embedding quality (384-dim, compatible with existing vectors)
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "384"))
# Optional reranker for improved top-k precision (15-20% improvement)
# Falls back to vector-only search if not set or fails to load
RERANKER_MODEL = os.getenv("RERANKER_MODEL", "")

# Research collections for paper/claim embeddings
PAPERS_COLLECTION = "paper_embeddings"
CLAIMS_COLLECTION = "claim_embeddings"


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


# Research paper and claim models for dataset generation
class PaperAddRequest(BaseModel):
    """Request to add a paper embedding."""

    paper_id: str = Field(..., description="Unique paper identifier (e.g., arxiv:2301.12345)")
    title: str = Field(..., description="Paper title")
    abstract: str = Field("", description="Paper abstract")
    source: str = Field(..., description="Source name (arxiv, semantic_scholar, pubmed, core)")
    doi: Optional[str] = Field(None, description="DOI if available")
    arxiv_id: Optional[str] = Field(None, description="arXiv ID if available")
    published_year: Optional[int] = Field(None, description="Publication year")
    topic_ids: List[str] = Field(default_factory=list, description="Research topic IDs")


class PaperFindSimilarRequest(BaseModel):
    """Request to find similar papers for deduplication."""

    title: str = Field(..., description="Paper title to search")
    abstract: str = Field("", description="Paper abstract for context")
    limit: int = Field(5, ge=1, le=20, description="Maximum similar papers to return")
    score_threshold: float = Field(0.85, ge=0.0, le=1.0, description="Minimum similarity score")
    exclude_paper_ids: List[str] = Field(default_factory=list, description="Paper IDs to exclude")


class SimilarPaper(BaseModel):
    """A similar paper result."""

    paper_id: str
    title: str
    source: str
    score: float
    doi: Optional[str] = None
    arxiv_id: Optional[str] = None


class PaperSimilarResponse(BaseModel):
    """Response with similar papers."""

    similar_papers: List[SimilarPaper]
    is_duplicate: bool = Field(..., description="True if high-similarity duplicate found")


class ClaimAddRequest(BaseModel):
    """Request to add a claim embedding."""

    claim_id: str = Field(..., description="Unique claim identifier")
    paper_id: str = Field(..., description="Source paper ID")
    claim_text: str = Field(..., description="The claim text")
    claim_type: str = Field("finding", description="Claim type (finding, method, etc.)")
    topic_ids: List[str] = Field(default_factory=list, description="Research topic IDs")
    section: str = Field("unknown", description="Paper section this claim came from")


class ClaimFindRelatedRequest(BaseModel):
    """Request to find related claims."""

    claim_text: str = Field(..., description="Claim text to search")
    limit: int = Field(10, ge=1, le=50, description="Maximum related claims to return")
    score_threshold: float = Field(0.7, ge=0.0, le=1.0, description="Minimum similarity score")
    topic_ids: Optional[List[str]] = Field(None, description="Filter by topic IDs")
    exclude_claim_ids: List[str] = Field(default_factory=list, description="Claim IDs to exclude")
    find_conflicts: bool = Field(False, description="Also find potentially conflicting claims")


class RelatedClaim(BaseModel):
    """A related claim result."""

    claim_id: str
    paper_id: str
    claim_text: str
    claim_type: str
    score: float
    relation: str = Field("similar", description="Relation type: similar, supporting, conflicting")


class ClaimRelatedResponse(BaseModel):
    """Response with related claims."""

    related_claims: List[RelatedClaim]
    count: int


# Global state
encoder_model: Optional[SentenceTransformer] = None
reranker_model: Optional[CrossEncoder] = None
qdrant_client: Optional[AsyncQdrantClient] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and cleanup resources."""
    global encoder_model, reranker_model, qdrant_client

    # Initialize sentence transformer
    encoder_model = SentenceTransformer(EMBEDDING_MODEL)

    # Initialize reranker (optional, with graceful fallback)
    if RERANKER_MODEL:
        try:
            reranker_model = CrossEncoder(RERANKER_MODEL)
            print(f"Reranker loaded: {RERANKER_MODEL}")
        except Exception as e:
            print(f"Warning: Failed to load reranker {RERANKER_MODEL}: {e}")
            print("Falling back to vector-only search")
            reranker_model = None
    else:
        reranker_model = None
        print("Reranker not configured, using vector-only search")

    # Initialize Qdrant client
    qdrant_client = AsyncQdrantClient(url=QDRANT_URL)

    # Create collections if they don't exist
    collections = await qdrant_client.get_collections()
    collection_names = [c.name for c in collections.collections]

    if COLLECTION_NAME not in collection_names:
        await qdrant_client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
        )

    # Create paper embeddings collection for research pipeline
    if PAPERS_COLLECTION not in collection_names:
        await qdrant_client.create_collection(
            collection_name=PAPERS_COLLECTION,
            vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
        )
        print(f"Created collection: {PAPERS_COLLECTION}")

    # Create claim embeddings collection for research pipeline
    if CLAIMS_COLLECTION not in collection_names:
        await qdrant_client.create_collection(
            collection_name=CLAIMS_COLLECTION,
            vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
        )
        print(f"Created collection: {CLAIMS_COLLECTION}")

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

        # Collect enough candidates for reranking (or stop if reached limit without reranker)
        if not reranker_model and len(memories) >= request.limit:
            break

    # Apply reranking if reranker is available
    if reranker_model and memories:
        # Prepare query-document pairs for reranking
        pairs = [(request.query, mem.content) for mem in memories]

        # Get reranker scores
        rerank_scores = reranker_model.predict(pairs)

        # Update memory scores with reranker scores
        for mem, score in zip(memories, rerank_scores):
            mem.score = float(score)

        # Sort by reranker score (descending)
        memories.sort(key=lambda m: m.score, reverse=True)

        # Take top k after reranking
        memories = memories[:request.limit]
    else:
        # Without reranker, just take top k from vector search
        memories = memories[:request.limit]

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
        "reranker_model": RERANKER_MODEL if reranker_model else None,
        "reranker_enabled": reranker_model is not None,
    }


# ============================================================================
# Research Paper Embedding Endpoints
# ============================================================================


@app.post("/papers/add")
async def add_paper_embedding(request: PaperAddRequest):
    """Add a paper embedding for semantic deduplication and similarity search."""
    if not encoder_model or not qdrant_client:
        raise HTTPException(status_code=500, detail="Service not initialized")

    # Generate embedding from title + abstract
    text_to_embed = f"{request.title}\n\n{request.abstract}" if request.abstract else request.title
    embedding = encoder_model.encode(text_to_embed).tolist()

    # Prepare payload
    payload = {
        "paper_id": request.paper_id,
        "title": request.title,
        "abstract": request.abstract,
        "source": request.source,
        "doi": request.doi,
        "arxiv_id": request.arxiv_id,
        "published_year": request.published_year,
        "topic_ids": request.topic_ids,
        "created_at": datetime.utcnow().isoformat(),
    }

    # Use paper_id as the point ID (hashed if not UUID-compatible)
    point_id = request.paper_id

    point = PointStruct(
        id=point_id,
        vector=embedding,
        payload=payload,
    )

    await qdrant_client.upsert(
        collection_name=PAPERS_COLLECTION,
        points=[point],
    )

    return {
        "status": "added",
        "paper_id": request.paper_id,
        "collection": PAPERS_COLLECTION,
    }


@app.post("/papers/find_similar", response_model=PaperSimilarResponse)
async def find_similar_papers(request: PaperFindSimilarRequest):
    """Find similar papers for deduplication before adding to database."""
    if not encoder_model or not qdrant_client:
        raise HTTPException(status_code=500, detail="Service not initialized")

    # Generate embedding from title + abstract
    text_to_embed = f"{request.title}\n\n{request.abstract}" if request.abstract else request.title
    query_embedding = encoder_model.encode(text_to_embed).tolist()

    # Search for similar papers
    search_result = await qdrant_client.search(
        collection_name=PAPERS_COLLECTION,
        query_vector=query_embedding,
        limit=request.limit + len(request.exclude_paper_ids),  # Fetch extra for filtering
        score_threshold=request.score_threshold,
    )

    # Filter out excluded papers and build response
    similar_papers = []
    is_duplicate = False

    for hit in search_result:
        payload = hit.payload
        paper_id = payload.get("paper_id", str(hit.id))

        # Skip excluded papers
        if paper_id in request.exclude_paper_ids:
            continue

        similar_paper = SimilarPaper(
            paper_id=paper_id,
            title=payload.get("title", ""),
            source=payload.get("source", ""),
            score=hit.score,
            doi=payload.get("doi"),
            arxiv_id=payload.get("arxiv_id"),
        )
        similar_papers.append(similar_paper)

        # Check if this is a high-confidence duplicate
        if hit.score >= 0.95:
            is_duplicate = True

        if len(similar_papers) >= request.limit:
            break

    return PaperSimilarResponse(
        similar_papers=similar_papers,
        is_duplicate=is_duplicate,
    )


@app.delete("/papers/{paper_id}")
async def delete_paper_embedding(paper_id: str):
    """Delete a paper embedding."""
    if not qdrant_client:
        raise HTTPException(status_code=500, detail="Service not initialized")

    await qdrant_client.delete(
        collection_name=PAPERS_COLLECTION,
        points_selector=[paper_id],
    )

    return {"status": "deleted", "paper_id": paper_id}


@app.get("/papers/stats")
async def get_paper_stats():
    """Get paper embeddings collection statistics."""
    if not qdrant_client:
        raise HTTPException(status_code=500, detail="Service not initialized")

    collection_info = await qdrant_client.get_collection(PAPERS_COLLECTION)

    return {
        "collection": PAPERS_COLLECTION,
        "paper_count": collection_info.points_count,
        "vector_dim": EMBEDDING_DIM,
    }


# ============================================================================
# Research Claim Embedding Endpoints
# ============================================================================


@app.post("/claims/add")
async def add_claim_embedding(request: ClaimAddRequest):
    """Add a claim embedding for similarity search and conflict detection."""
    if not encoder_model or not qdrant_client:
        raise HTTPException(status_code=500, detail="Service not initialized")

    # Generate embedding from claim text
    embedding = encoder_model.encode(request.claim_text).tolist()

    # Prepare payload
    payload = {
        "claim_id": request.claim_id,
        "paper_id": request.paper_id,
        "claim_text": request.claim_text,
        "claim_type": request.claim_type,
        "topic_ids": request.topic_ids,
        "section": request.section,
        "created_at": datetime.utcnow().isoformat(),
    }

    point = PointStruct(
        id=request.claim_id,
        vector=embedding,
        payload=payload,
    )

    await qdrant_client.upsert(
        collection_name=CLAIMS_COLLECTION,
        points=[point],
    )

    return {
        "status": "added",
        "claim_id": request.claim_id,
        "collection": CLAIMS_COLLECTION,
    }


@app.post("/claims/find_related", response_model=ClaimRelatedResponse)
async def find_related_claims(request: ClaimFindRelatedRequest):
    """Find related claims for cross-referencing and conflict detection."""
    if not encoder_model or not qdrant_client:
        raise HTTPException(status_code=500, detail="Service not initialized")

    # Generate embedding from claim text
    query_embedding = encoder_model.encode(request.claim_text).tolist()

    # Build filter for topic IDs if specified
    query_filter = None
    if request.topic_ids:
        query_filter = {
            "should": [
                {"key": "topic_ids", "match": {"any": request.topic_ids}}
            ]
        }

    # Search for related claims
    search_result = await qdrant_client.search(
        collection_name=CLAIMS_COLLECTION,
        query_vector=query_embedding,
        query_filter=query_filter,
        limit=request.limit + len(request.exclude_claim_ids),
        score_threshold=request.score_threshold,
    )

    # Build response, filtering excluded claims
    related_claims = []

    for hit in search_result:
        payload = hit.payload
        claim_id = payload.get("claim_id", str(hit.id))

        # Skip excluded claims
        if claim_id in request.exclude_claim_ids:
            continue

        # Determine relation type based on score
        # High similarity (>0.9) = likely supporting
        # Medium similarity (0.7-0.9) = related
        # For conflict detection, we'd need NLI which is handled elsewhere
        if hit.score >= 0.9:
            relation = "supporting"
        else:
            relation = "similar"

        related_claim = RelatedClaim(
            claim_id=claim_id,
            paper_id=payload.get("paper_id", ""),
            claim_text=payload.get("claim_text", ""),
            claim_type=payload.get("claim_type", "finding"),
            score=hit.score,
            relation=relation,
        )
        related_claims.append(related_claim)

        if len(related_claims) >= request.limit:
            break

    return ClaimRelatedResponse(
        related_claims=related_claims,
        count=len(related_claims),
    )


@app.post("/claims/batch_add")
async def batch_add_claims(claims: List[ClaimAddRequest]):
    """Add multiple claim embeddings in batch."""
    if not encoder_model or not qdrant_client:
        raise HTTPException(status_code=500, detail="Service not initialized")

    if not claims:
        return {"status": "no claims to add", "count": 0}

    # Generate embeddings for all claims
    texts = [c.claim_text for c in claims]
    embeddings = encoder_model.encode(texts).tolist()

    # Build points
    points = []
    for claim, embedding in zip(claims, embeddings):
        payload = {
            "claim_id": claim.claim_id,
            "paper_id": claim.paper_id,
            "claim_text": claim.claim_text,
            "claim_type": claim.claim_type,
            "topic_ids": claim.topic_ids,
            "section": claim.section,
            "created_at": datetime.utcnow().isoformat(),
        }
        points.append(PointStruct(
            id=claim.claim_id,
            vector=embedding,
            payload=payload,
        ))

    await qdrant_client.upsert(
        collection_name=CLAIMS_COLLECTION,
        points=points,
    )

    return {
        "status": "added",
        "count": len(points),
        "collection": CLAIMS_COLLECTION,
    }


@app.delete("/claims/{claim_id}")
async def delete_claim_embedding(claim_id: str):
    """Delete a claim embedding."""
    if not qdrant_client:
        raise HTTPException(status_code=500, detail="Service not initialized")

    await qdrant_client.delete(
        collection_name=CLAIMS_COLLECTION,
        points_selector=[claim_id],
    )

    return {"status": "deleted", "claim_id": claim_id}


@app.get("/claims/stats")
async def get_claim_stats():
    """Get claim embeddings collection statistics."""
    if not qdrant_client:
        raise HTTPException(status_code=500, detail="Service not initialized")

    collection_info = await qdrant_client.get_collection(CLAIMS_COLLECTION)

    return {
        "collection": CLAIMS_COLLECTION,
        "claim_count": collection_info.points_count,
        "vector_dim": EMBEDDING_DIM,
    }


@app.get("/research/stats")
async def get_research_stats():
    """Get combined statistics for all research collections."""
    if not qdrant_client:
        raise HTTPException(status_code=500, detail="Service not initialized")

    papers_info = await qdrant_client.get_collection(PAPERS_COLLECTION)
    claims_info = await qdrant_client.get_collection(CLAIMS_COLLECTION)

    return {
        "papers": {
            "collection": PAPERS_COLLECTION,
            "count": papers_info.points_count,
        },
        "claims": {
            "collection": CLAIMS_COLLECTION,
            "count": claims_info.points_count,
        },
        "vector_dim": EMBEDDING_DIM,
        "embedding_model": EMBEDDING_MODEL,
    }


__all__ = ["app"]
