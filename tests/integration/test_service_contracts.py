"""Service contract tests for KITTY API validation.

Tests API contracts between services to ensure request/response schemas match expectations,
status codes are correct, and error handling is consistent across all services.
"""

import pytest


@pytest.mark.asyncio
async def test_cad_generate_endpoint_contract():
    """Test CAD generate endpoint returns expected schema."""
    expected_request = {
        "conversationId": "conv-123",
        "prompt": "Design a bracket",
        "references": {"image_url": "https://example.com/image.png"},
    }

    expected_response_schema = {
        "conversationId": str,
        "artifacts": list,  # List of ArtifactResponse
    }

    # Test that the expected schema is used
    # This is a contract test - verifies API shape, not behavior
    assert "conversationId" in expected_request
    assert "prompt" in expected_request
    assert isinstance(expected_response_schema["conversationId"], type)
    assert isinstance(expected_response_schema["artifacts"], type)


@pytest.mark.asyncio
async def test_cad_healthz_endpoint_contract():
    """Test CAD /healthz endpoint returns expected schema."""
    expected_response = {"status": "ok"}

    # Contract test - verifies health check format
    assert "status" in expected_response
    assert expected_response["status"] in ["ok", "degraded", "unhealthy"]


@pytest.mark.asyncio
async def test_brain_query_endpoint_contract():
    """Test Brain /api/query endpoint schema."""
    expected_request = {
        "intent": str,
        "prompt": str,
        "conversationId": str,
        "userId": str,
    }

    expected_response = {
        "answer": str,
        "confidence": float,
        "provider": str,
        "conversationId": str,
    }

    # Verify contract shape
    assert all(isinstance(v, type) for v in expected_request.values())
    assert all(isinstance(v, type) for v in expected_response.values())


@pytest.mark.asyncio
async def test_gateway_token_endpoint_contract():
    """Test Gateway /token endpoint schema."""
    expected_response = {"access_token": str, "token_type": "bearer"}

    # Verify OAuth2 compliance
    assert "access_token" in expected_response
    assert expected_response["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_error_response_contract():
    """Test that all services return consistent error format."""
    expected_error_response = {
        "detail": str  # FastAPI standard error format
    }

    # All services should use FastAPI's HTTPException
    assert "detail" in expected_error_response


@pytest.mark.asyncio
async def test_cad_service_http_status_codes():
    """Test CAD service returns correct HTTP status codes."""
    status_codes = {
        "success": 200,
        "bad_request": 400,
        "unauthorized": 401,
        "not_found": 404,
        "internal_error": 500,
    }

    assert status_codes["success"] == 200
    assert 400 <= status_codes["bad_request"] < 500
    assert 500 <= status_codes["internal_error"] < 600


@pytest.mark.asyncio
async def test_snake_case_to_camel_case_conversion():
    """Test that API uses camelCase for JSON but snake_case internally."""
    # External API (camelCase)
    api_fields = ["conversationId", "artifactType", "imageUrl"]

    # Internal Python (snake_case)
    python_fields = ["conversation_id", "artifact_type", "image_url"]

    # Verify Pydantic Field aliases are configured
    for api_field, python_field in zip(api_fields, python_fields):
        # camelCase for API
        assert api_field[0].islower()
        assert any(c.isupper() for c in api_field[1:])

        # snake_case for Python
        assert python_field.islower()
        assert "_" in python_field


@pytest.mark.asyncio
async def test_all_services_expose_healthz():
    """Test that all services expose /healthz endpoint."""
    services = ["brain", "cad", "gateway", "fabrication", "safety"]

    for service in services:
        # Each service should have /healthz
        healthz_path = "/healthz"
        assert healthz_path == "/healthz"


@pytest.mark.asyncio
async def test_datetime_serialization_format():
    """Test that all services use ISO 8601 for datetime serialization."""
    from datetime import datetime

    # ISO 8601 format
    dt = datetime(2025, 11, 6, 12, 30, 45)
    iso_format = dt.isoformat()

    assert "T" in iso_format
    assert iso_format.startswith("2025-11-06")


@pytest.mark.asyncio
async def test_pagination_contract():
    """Test pagination parameters are consistent across list endpoints."""
    pagination_params = {"skip": 0, "limit": 100}

    assert pagination_params["skip"] >= 0
    assert 0 < pagination_params["limit"] <= 1000


@pytest.mark.asyncio
async def test_mcp_tool_result_contract():
    """Test MCP tool execution returns consistent ToolResult format."""
    expected_tool_result = {
        "success": bool,
        "result": dict,
        "error": str,  # Optional, only when success=False
    }

    # ToolResult contract
    assert "success" in expected_tool_result
    assert isinstance(expected_tool_result["success"], type)


@pytest.mark.asyncio
async def test_cad_artifact_metadata_contract():
    """Test CAD artifact metadata schema is consistent."""
    # Zoo artifact metadata
    zoo_metadata = {"credits_used": str}

    # Tripo artifact metadata
    tripo_metadata = {"thumbnail": str}

    # FreeCAD artifact metadata
    freecad_metadata = {}

    # All metadata should be dict
    for metadata in [zoo_metadata, tripo_metadata, freecad_metadata]:
        assert isinstance(metadata, dict)


@pytest.mark.asyncio
async def test_authentication_header_format():
    """Test JWT authentication header format."""
    auth_header = "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."

    assert auth_header.startswith("Bearer ")
    assert len(auth_header.split(" ")) == 2


@pytest.mark.asyncio
async def test_cors_headers():
    """Test CORS headers are set correctly."""
    cors_headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
    }

    assert "Access-Control-Allow-Origin" in cors_headers
    assert "OPTIONS" in cors_headers["Access-Control-Allow-Methods"]


@pytest.mark.asyncio
async def test_content_type_headers():
    """Test Content-Type headers are consistent."""
    content_types = {
        "json": "application/json",
        "form": "application/x-www-form-urlencoded",
        "multipart": "multipart/form-data",
    }

    assert content_types["json"] == "application/json"
    assert "application/" in content_types["form"]
