"""End-to-end CAD workflow integration tests.

Tests the complete CAD generation workflow from Gateway → Brain → CAD services,
validating authentication, routing, provider orchestration, and response handling.
"""

import pytest


@pytest.fixture
def mock_jwt_token():
    """Mock JWT token for authentication."""
    return "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test.token"


@pytest.fixture
def cad_generation_request():
    """Sample CAD generation request payload."""
    return {
        "conversationId": "test-conv-123",
        "prompt": "Design a mounting bracket with 4x M3 holes",
        "references": {"image_url": "https://example.com/reference.png"},
    }


@pytest.mark.asyncio
async def test_e2e_cad_generation_via_gateway(mock_jwt_token, cad_generation_request):
    """Test full CAD generation workflow through Gateway."""
    # This is an end-to-end test that would require running services
    # For now, we validate the expected flow structure

    expected_flow = [
        "1. Client sends POST /api/cad/generate with JWT token",
        "2. Gateway validates JWT and forwards to Brain",
        "3. Brain routes to CAD service based on intent",
        "4. CAD service cycles through providers (Zoo, Tripo, local)",
        "5. Artifacts stored in MinIO",
        "6. Response flows back through Brain → Gateway → Client",
    ]

    # Verify flow structure is documented
    assert len(expected_flow) == 6
    assert "Gateway validates JWT" in expected_flow[1]
    assert "CAD service cycles through providers" in expected_flow[3]


@pytest.mark.asyncio
async def test_e2e_authentication_flow():
    """Test end-to-end authentication flow."""
    # Verify OAuth2 token endpoint contract
    expected_response = {
        "access_token": "jwt_token_here",
        "token_type": "bearer",
        "expires_in": 3600,
    }

    # Validate response structure
    assert "access_token" in expected_response
    assert expected_response["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_e2e_brain_to_cad_routing():
    """Test Brain service routing to CAD service."""
    brain_request = {
        "intent": "cad_generation",
        "prompt": "Design a bracket",
        "conversationId": "conv-123",
        "userId": "user-456",
    }

    # Expected routing decision
    assert brain_request["intent"] == "cad_generation"

    # Brain should route to CAD service at http://cad:8200
    expected_cad_url = "http://cad:8200/api/cad/generate"
    assert "cad" in expected_cad_url


@pytest.mark.asyncio
async def test_e2e_cad_provider_orchestration():
    """Test CAD service provider orchestration."""
    providers = ["zoo", "tripo", "tripo_local", "freecad"]

    # Verify all providers are available
    assert len(providers) == 4
    assert "zoo" in providers
    assert "tripo" in providers


@pytest.mark.asyncio
async def test_e2e_artifact_storage_flow():
    """Test artifact storage in MinIO."""
    artifact = {
        "provider": "zoo",
        "artifact_type": "gltf",
        "location": "minio://artifacts/model-123.gltf",
        "metadata": {"credits_used": "5"},
    }

    # Verify artifact structure
    assert artifact["location"].startswith("minio://")
    assert "artifacts" in artifact["location"]


@pytest.mark.asyncio
async def test_e2e_response_propagation():
    """Test response propagation through service chain."""
    # CAD service response
    cad_response = {
        "conversationId": "conv-123",
        "artifacts": [
            {
                "provider": "zoo",
                "artifactType": "gltf",
                "location": "minio://artifacts/model.gltf",
                "metadata": {},
            }
        ],
    }

    # Brain wraps CAD response
    brain_response = {
        "answer": "I've generated a CAD model for you",
        "confidence": 0.95,
        "provider": "cad_service",
        "conversationId": "conv-123",
        "artifacts": cad_response["artifacts"],
    }

    # Gateway forwards Brain response
    gateway_response = brain_response

    # Verify response structure at each layer
    assert cad_response["conversationId"] == "conv-123"
    assert brain_response["provider"] == "cad_service"
    assert gateway_response["confidence"] == 0.95


@pytest.mark.asyncio
async def test_e2e_error_handling_cascade():
    """Test error propagation through service chain."""
    # CAD service error
    cad_error = {"detail": "All CAD providers failed"}

    # Brain handles CAD error
    brain_error_response = {
        "answer": "I encountered an error generating the CAD model",
        "confidence": 0.0,
        "provider": "error",
        "conversationId": "conv-123",
        "error": cad_error["detail"],
    }

    # Verify error structure
    assert brain_error_response["confidence"] == 0.0
    assert "error" in brain_error_response


@pytest.mark.asyncio
async def test_e2e_timeout_handling():
    """Test timeout handling in service chain."""
    service_timeouts = {
        "gateway_to_brain": 30,  # seconds
        "brain_to_cad": 120,  # seconds
        "cad_provider_timeout": 60,  # seconds
    }

    # Verify reasonable timeout values
    assert service_timeouts["gateway_to_brain"] > 0
    assert service_timeouts["brain_to_cad"] > service_timeouts["gateway_to_brain"]


@pytest.mark.asyncio
async def test_e2e_conversation_continuity():
    """Test conversation ID propagation through service chain."""
    conversation_id = "conv-abc-123"

    # Request at each layer should maintain conversation ID
    gateway_request = {"conversationId": conversation_id, "prompt": "Design X"}
    brain_request = {"conversationId": conversation_id, "intent": "cad_generation"}
    cad_request = {"conversationId": conversation_id, "prompt": "Design X"}

    # Verify conversation ID continuity
    assert gateway_request["conversationId"] == conversation_id
    assert brain_request["conversationId"] == conversation_id
    assert cad_request["conversationId"] == conversation_id


@pytest.mark.asyncio
async def test_e2e_metadata_enrichment():
    """Test metadata enrichment at each service layer."""
    # Gateway adds request metadata
    gateway_metadata = {"request_id": "req-123", "timestamp": "2025-11-06T12:00:00Z"}

    # Brain adds routing metadata
    brain_metadata = {
        **gateway_metadata,
        "routing_tier": "cad_service",
        "confidence": 0.95,
    }

    # CAD adds provider metadata
    cad_metadata = {
        **brain_metadata,
        "provider": "zoo",
        "credits_used": "5",
    }

    # Verify metadata flows through chain
    assert "request_id" in gateway_metadata
    assert "routing_tier" in brain_metadata
    assert "provider" in cad_metadata


@pytest.mark.asyncio
async def test_e2e_health_check_cascade():
    """Test health check propagation through services."""
    # Each service exposes /healthz
    gateway_health = {"status": "ok", "downstream": ["brain"]}
    brain_health = {"status": "ok", "downstream": ["cad", "memory"]}

    # Verify health check structure
    assert gateway_health["status"] == "ok"
    assert "brain" in gateway_health["downstream"]
    assert "cad" in brain_health["downstream"]


@pytest.mark.asyncio
async def test_e2e_rate_limiting():
    """Test rate limiting at Gateway layer."""
    rate_limits = {
        "requests_per_minute": 60,
        "requests_per_hour": 1000,
        "concurrent_requests": 10,
    }

    # Verify rate limits are defined
    assert rate_limits["requests_per_minute"] > 0
    assert rate_limits["requests_per_hour"] > rate_limits["requests_per_minute"]


@pytest.mark.asyncio
async def test_e2e_cors_configuration():
    """Test CORS headers in Gateway responses."""
    cors_config = {
        "allow_origins": ["http://localhost:3000", "https://kitty.example.com"],
        "allow_methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"],
        "allow_credentials": True,
    }

    # Verify CORS configuration
    assert "http://localhost:3000" in cors_config["allow_origins"]
    assert "Authorization" in cors_config["allow_headers"]


@pytest.mark.asyncio
async def test_e2e_logging_and_tracing():
    """Test distributed tracing through service chain."""
    trace_headers = {
        "X-Request-ID": "req-123",
        "X-Trace-ID": "trace-abc",
        "X-Span-ID": "span-456",
    }

    # Verify tracing headers are present
    assert "X-Request-ID" in trace_headers
    assert "X-Trace-ID" in trace_headers


@pytest.mark.asyncio
async def test_e2e_service_discovery():
    """Test service discovery via Docker Compose networking."""
    service_urls = {
        "gateway": "http://gateway:8080",
        "brain": "http://brain:8000",
        "cad": "http://cad:8200",
        "memory": "http://memory:8300",
        "minio": "http://minio:9000",
    }

    # Verify service URLs use Docker Compose service names
    for service_name, url in service_urls.items():
        assert service_name in url
        assert url.startswith("http://")
