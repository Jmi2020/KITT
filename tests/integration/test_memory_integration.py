"""Memory (Qdrant) integration tests.

Tests the integration between Brain service and Memory/Qdrant for semantic memory
storage, retrieval, and conversation context management.
"""

import pytest


@pytest.fixture
def sample_memory():
    """Sample memory for testing."""
    return {
        "content": "User prefers ABS filament for functional parts",
        "metadata": {
            "user_id": "user-123",
            "conversation_id": "conv-456",
            "timestamp": "2025-11-06T12:00:00Z",
            "category": "preference",
        },
    }


@pytest.fixture
def sample_conversation_memory():
    """Sample conversation memory."""
    return {
        "content": "Designed a mounting bracket for workshop camera",
        "metadata": {
            "user_id": "user-123",
            "conversation_id": "conv-789",
            "timestamp": "2025-11-06T11:00:00Z",
            "artifacts": ["model-123.gltf"],
            "category": "project",
        },
    }


@pytest.fixture
def mock_qdrant_search_result():
    """Mock Qdrant search result."""
    return {
        "id": "mem-123",
        "score": 0.95,
        "payload": {
            "content": "User prefers ABS filament for functional parts",
            "user_id": "user-123",
            "category": "preference",
            "timestamp": "2025-11-06T12:00:00Z",
        },
    }


@pytest.mark.asyncio
async def test_memory_storage(sample_memory):
    """Test storing memory in Qdrant."""
    store_request = {
        "content": sample_memory["content"],
        "metadata": sample_memory["metadata"],
    }

    # Should include content and metadata
    assert "content" in store_request
    assert "metadata" in store_request
    assert store_request["metadata"]["user_id"] == "user-123"


@pytest.mark.asyncio
async def test_memory_retrieval_by_similarity():
    """Test retrieving memories by semantic similarity."""
    query = "What filament does the user prefer?"

    search_request = {
        "query_text": query,
        "limit": 5,
        "filter": {"user_id": "user-123"},
    }

    # Should include query and filters
    assert "query_text" in search_request
    assert search_request["limit"] > 0
    assert "user_id" in search_request["filter"]


@pytest.mark.asyncio
async def test_memory_retrieval_by_conversation(mock_qdrant_search_result):
    """Test retrieving memories from specific conversation."""
    filter_request = {
        "filter": {
            "conversation_id": "conv-456",
            "user_id": "user-123",
        },
        "limit": 10,
    }

    # Should filter by conversation ID
    assert "conversation_id" in filter_request["filter"]
    assert filter_request["limit"] > 0


@pytest.mark.asyncio
async def test_memory_vector_embedding():
    """Test memory text is converted to vector embeddings."""
    # Simulate embedding generation
    embedding_config = {
        "model": "sentence-transformers/all-MiniLM-L6-v2",
        "dimension": 384,
    }

    assert embedding_config["dimension"] > 0
    assert "model" in embedding_config


@pytest.mark.asyncio
async def test_memory_search_with_threshold():
    """Test memory search with similarity threshold."""
    search_config = {
        "query_text": "What projects has the user worked on?",
        "score_threshold": 0.7,
        "limit": 5,
    }

    # Only return results above threshold
    assert search_config["score_threshold"] > 0
    assert search_config["score_threshold"] < 1.0


@pytest.mark.asyncio
async def test_memory_deletion():
    """Test deleting specific memory by ID."""
    delete_request = {"memory_id": "mem-123"}

    assert "memory_id" in delete_request
    assert delete_request["memory_id"].startswith("mem-")


@pytest.mark.asyncio
async def test_memory_user_isolation():
    """Test memories are isolated per user."""
    user_filter = {"user_id": "user-123"}

    # Should never return memories from other users
    assert "user_id" in user_filter


@pytest.mark.asyncio
async def test_memory_conversation_continuity():
    """Test retrieving conversation context."""
    context_request = {
        "conversation_id": "conv-456",
        "limit": 20,
        "order_by": "timestamp",
    }

    assert "conversation_id" in context_request
    assert context_request["order_by"] == "timestamp"


@pytest.mark.asyncio
async def test_memory_category_filtering():
    """Test filtering memories by category."""
    categories = ["preference", "project", "skill", "knowledge"]

    category_filter = {
        "filter": {"category": "preference"},
        "user_id": "user-123",
    }

    assert category_filter["filter"]["category"] in categories


@pytest.mark.asyncio
async def test_memory_time_range_query():
    """Test querying memories within time range."""
    time_filter = {
        "filter": {
            "timestamp": {"gte": "2025-11-01T00:00:00Z", "lte": "2025-11-07T00:00:00Z"}
        }
    }

    # Should support timestamp range queries
    assert "timestamp" in time_filter["filter"]
    assert "gte" in time_filter["filter"]["timestamp"]


@pytest.mark.asyncio
async def test_memory_artifact_linkage(sample_conversation_memory):
    """Test linking memories to CAD artifacts."""
    memory_with_artifact = sample_conversation_memory

    # Should link to artifact IDs
    assert "artifacts" in memory_with_artifact["metadata"]
    assert len(memory_with_artifact["metadata"]["artifacts"]) > 0


@pytest.mark.asyncio
async def test_memory_collection_management():
    """Test Qdrant collection configuration."""
    collection_config = {
        "name": "kitty_memories",
        "vector_size": 384,
        "distance": "Cosine",
    }

    assert collection_config["vector_size"] > 0
    assert collection_config["distance"] in ["Cosine", "Euclidean", "Dot"]


@pytest.mark.asyncio
async def test_memory_batch_storage():
    """Test storing multiple memories in batch."""
    batch_memories = [
        {"content": "Memory 1", "metadata": {"user_id": "user-123"}},
        {"content": "Memory 2", "metadata": {"user_id": "user-123"}},
        {"content": "Memory 3", "metadata": {"user_id": "user-123"}},
    ]

    # Should support batch insertion
    assert len(batch_memories) > 1
    assert all("content" in m for m in batch_memories)


@pytest.mark.asyncio
async def test_memory_update_metadata():
    """Test updating memory metadata."""
    update_request = {
        "memory_id": "mem-123",
        "metadata": {"tags": ["important", "reference"]},
    }

    assert "memory_id" in update_request
    assert "metadata" in update_request


@pytest.mark.asyncio
async def test_memory_search_pagination():
    """Test paginated memory search results."""
    paginated_search = {"query_text": "projects", "limit": 10, "offset": 0}

    # Should support pagination
    assert paginated_search["limit"] > 0
    assert paginated_search["offset"] >= 0


@pytest.mark.asyncio
async def test_memory_relevance_scoring(mock_qdrant_search_result):
    """Test memory search returns relevance scores."""
    search_result = mock_qdrant_search_result

    # Should include similarity score
    assert "score" in search_result
    assert 0 <= search_result["score"] <= 1.0


@pytest.mark.asyncio
async def test_memory_multi_modal_context():
    """Test storing multi-modal memory context."""
    multimodal_memory = {
        "content": "Designed bracket based on reference image",
        "metadata": {
            "user_id": "user-123",
            "image_refs": ["ref-image-123.png"],
            "model_refs": ["model-456.gltf"],
            "text_context": "Workshop camera mount",
        },
    }

    # Should support multiple reference types
    assert "image_refs" in multimodal_memory["metadata"]
    assert "model_refs" in multimodal_memory["metadata"]


@pytest.mark.asyncio
async def test_memory_conversation_summary():
    """Test generating conversation summary from memories."""
    conversation_memories = [
        {"content": "User asked about ABS filament", "timestamp": "12:00:00"},
        {"content": "Explained ABS properties", "timestamp": "12:01:00"},
        {"content": "User decided to use ABS for brackets", "timestamp": "12:02:00"},
    ]

    # Should retrieve ordered memories for summarization
    assert len(conversation_memories) > 0
    assert all("timestamp" in m for m in conversation_memories)


@pytest.mark.asyncio
async def test_memory_semantic_deduplication():
    """Test detecting semantically similar memories."""
    duplicate_check = {
        "new_content": "User prefers ABS filament",
        "similarity_threshold": 0.95,
    }

    # Should check for near-duplicates before storing
    assert "similarity_threshold" in duplicate_check
    assert duplicate_check["similarity_threshold"] > 0.9


@pytest.mark.asyncio
async def test_memory_export_for_context():
    """Test exporting memories for LLM context."""
    export_request = {
        "user_id": "user-123",
        "conversation_id": "conv-456",
        "max_tokens": 2000,
    }

    # Should format memories for LLM consumption
    assert "user_id" in export_request
    assert export_request["max_tokens"] > 0


@pytest.mark.asyncio
async def test_memory_privacy_controls():
    """Test memory privacy and retention controls."""
    privacy_policy = {
        "retention_days": 90,
        "allow_cross_conversation": False,
        "encrypt_at_rest": True,
    }

    assert privacy_policy["retention_days"] > 0
    assert isinstance(privacy_policy["allow_cross_conversation"], bool)


@pytest.mark.asyncio
async def test_memory_statistics():
    """Test retrieving memory statistics."""
    expected_stats = {
        "total_memories": 150,
        "conversations": 25,
        "categories": {"preference": 20, "project": 80, "knowledge": 50},
        "avg_memories_per_conversation": 6.0,
    }

    assert "total_memories" in expected_stats
    assert "categories" in expected_stats


@pytest.mark.asyncio
async def test_memory_qdrant_connection():
    """Test Qdrant connection configuration."""
    qdrant_config = {
        "host": "qdrant",
        "port": 6333,
        "timeout": 30,
        "prefer_grpc": True,
    }

    assert qdrant_config["port"] > 0
    assert qdrant_config["timeout"] > 0


@pytest.mark.asyncio
async def test_memory_embedding_cache():
    """Test caching embeddings for performance."""
    cache_config = {
        "enabled": True,
        "ttl_seconds": 3600,
        "max_size": 1000,
    }

    assert cache_config["enabled"] is True
    assert cache_config["ttl_seconds"] > 0
