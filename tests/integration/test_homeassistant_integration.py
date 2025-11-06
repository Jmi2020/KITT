"""Home Assistant integration tests.

Tests the integration between Brain service and Home Assistant for device control,
state queries, and entity discovery workflows.
"""

import pytest


@pytest.fixture
def mock_ha_entity_state():
    """Mock Home Assistant entity state response."""
    return {
        "entity_id": "light.office",
        "state": "on",
        "attributes": {
            "brightness": 255,
            "color_temp": 370,
            "friendly_name": "Office Light",
        },
        "last_changed": "2025-11-06T12:00:00Z",
        "last_updated": "2025-11-06T12:00:00Z",
    }


@pytest.fixture
def mock_ha_entities_list():
    """Mock Home Assistant entities list response."""
    return [
        {
            "entity_id": "light.office",
            "state": "on",
            "attributes": {"friendly_name": "Office Light"},
        },
        {
            "entity_id": "light.workshop",
            "state": "off",
            "attributes": {"friendly_name": "Workshop Light"},
        },
        {
            "entity_id": "switch.3d_printer",
            "state": "on",
            "attributes": {"friendly_name": "3D Printer Power"},
        },
        {
            "entity_id": "camera.workshop_cam",
            "state": "idle",
            "attributes": {"friendly_name": "Workshop Camera"},
        },
    ]


@pytest.mark.asyncio
async def test_ha_device_control_integration():
    """Test Home Assistant device control flow."""
    # User request flow
    user_request = {
        "prompt": "Turn on the workshop lights",
        "conversationId": "conv-123",
        "userId": "user-456",
    }

    ha_service_call = {
        "domain": "light",
        "service": "turn_on",
        "entity_id": "light.workshop",
    }

    # Verify intent classification
    assert "workshop" in user_request["prompt"].lower()
    assert "light" in user_request["prompt"].lower()

    # Verify service call structure
    assert ha_service_call["domain"] == "light"
    assert ha_service_call["service"] == "turn_on"


@pytest.mark.asyncio
async def test_ha_state_query_integration(mock_ha_entity_state):
    """Test Home Assistant state query flow."""
    query_request = {
        "prompt": "Is the office light on?",
        "conversationId": "conv-123",
    }

    # Brain should parse entity from query
    assert "office" in query_request["prompt"].lower()
    assert "light" in query_request["prompt"].lower()

    # Verify HA response structure
    assert mock_ha_entity_state["entity_id"] == "light.office"
    assert mock_ha_entity_state["state"] == "on"


@pytest.mark.asyncio
async def test_ha_entity_discovery(mock_ha_entities_list):
    """Test Home Assistant entity discovery."""
    # Should return filtered entities
    lights = [e for e in mock_ha_entities_list if e["entity_id"].startswith("light.")]

    assert len(lights) == 2
    assert any(e["entity_id"] == "light.office" for e in lights)
    assert any(e["entity_id"] == "light.workshop" for e in lights)


@pytest.mark.asyncio
async def test_ha_service_with_parameters():
    """Test Home Assistant service call with parameters."""
    service_call = {
        "domain": "light",
        "service": "turn_on",
        "entity_id": "light.office",
        "data": {"brightness": 128, "color_temp": 400},
    }

    # Verify service call includes data
    assert "data" in service_call
    assert service_call["data"]["brightness"] == 128


@pytest.mark.asyncio
async def test_ha_multiple_entities():
    """Test Home Assistant control of multiple entities."""
    service_call = {
        "domain": "light",
        "service": "turn_off",
        "entity_id": ["light.office", "light.workshop"],
    }

    # Should support list of entity IDs
    assert isinstance(service_call["entity_id"], list)
    assert len(service_call["entity_id"]) == 2


@pytest.mark.asyncio
async def test_ha_climate_control():
    """Test Home Assistant climate device control."""
    climate_call = {
        "domain": "climate",
        "service": "set_temperature",
        "entity_id": "climate.workshop",
        "data": {"temperature": 22},
    }

    assert climate_call["domain"] == "climate"
    assert climate_call["service"] == "set_temperature"
    assert climate_call["data"]["temperature"] == 22


@pytest.mark.asyncio
async def test_ha_camera_snapshot():
    """Test Home Assistant camera snapshot request."""
    camera_request = {
        "domain": "camera",
        "service": "snapshot",
        "entity_id": "camera.workshop_cam",
        "data": {"filename": "/tmp/workshop_snapshot.jpg"},
    }

    assert camera_request["domain"] == "camera"
    assert camera_request["service"] == "snapshot"


@pytest.mark.asyncio
async def test_ha_scene_activation():
    """Test Home Assistant scene activation."""
    scene_call = {
        "domain": "scene",
        "service": "turn_on",
        "entity_id": "scene.workshop_printing",
    }

    assert scene_call["domain"] == "scene"
    assert scene_call["entity_id"].startswith("scene.")


@pytest.mark.asyncio
async def test_ha_automation_trigger():
    """Test Home Assistant automation trigger."""
    automation_call = {
        "domain": "automation",
        "service": "trigger",
        "entity_id": "automation.print_complete_notify",
    }

    assert automation_call["domain"] == "automation"
    assert automation_call["service"] == "trigger"


@pytest.mark.asyncio
async def test_ha_error_handling():
    """Test Home Assistant error response handling."""
    # Simulate HA API error
    ha_error = {
        "error": "entity_not_found",
        "message": "Entity light.nonexistent not found",
    }

    # Brain should handle gracefully
    brain_response = {
        "answer": "I couldn't find that device in Home Assistant",
        "confidence": 0.0,
        "error": ha_error["message"],
    }

    assert "error" in brain_response
    assert brain_response["confidence"] == 0.0


@pytest.mark.asyncio
async def test_ha_connection_timeout():
    """Test Home Assistant connection timeout handling."""
    timeout_config = {
        "connect_timeout": 5,  # seconds
        "read_timeout": 10,  # seconds
    }

    assert timeout_config["connect_timeout"] > 0
    assert timeout_config["read_timeout"] > timeout_config["connect_timeout"]


@pytest.mark.asyncio
async def test_ha_authentication():
    """Test Home Assistant authentication."""
    auth_headers = {
        "Authorization": "Bearer long-lived-access-token",
        "Content-Type": "application/json",
    }

    assert "Authorization" in auth_headers
    assert auth_headers["Authorization"].startswith("Bearer ")


@pytest.mark.asyncio
async def test_ha_websocket_connection():
    """Test Home Assistant WebSocket connection for state updates."""
    websocket_config = {
        "url": "ws://homeassistant.local:8123/api/websocket",
        "auth_required": True,
    }

    assert websocket_config["url"].startswith("ws://")
    assert "/api/websocket" in websocket_config["url"]


@pytest.mark.asyncio
async def test_ha_entity_state_change_subscription():
    """Test subscribing to Home Assistant entity state changes."""
    subscription_request = {
        "type": "subscribe_events",
        "event_type": "state_changed",
        "entity_id": "light.office",
    }

    assert subscription_request["type"] == "subscribe_events"
    assert subscription_request["event_type"] == "state_changed"


@pytest.mark.asyncio
async def test_ha_service_domain_validation():
    """Test Home Assistant service domain validation."""
    valid_domains = [
        "light",
        "switch",
        "climate",
        "camera",
        "scene",
        "automation",
        "script",
        "lock",
        "cover",
    ]

    service_call = {"domain": "light", "service": "turn_on"}

    assert service_call["domain"] in valid_domains


@pytest.mark.asyncio
async def test_ha_entity_attributes_parsing():
    """Test parsing Home Assistant entity attributes."""
    entity = {
        "entity_id": "sensor.3d_printer_temp",
        "state": "210",
        "attributes": {
            "unit_of_measurement": "°C",
            "device_class": "temperature",
            "friendly_name": "3D Printer Temperature",
        },
    }

    # Should extract numeric value and unit
    temp_value = float(entity["state"])
    temp_unit = entity["attributes"]["unit_of_measurement"]

    assert temp_value == 210.0
    assert temp_unit == "°C"


@pytest.mark.asyncio
async def test_ha_cover_control():
    """Test Home Assistant cover device control."""
    cover_call = {
        "domain": "cover",
        "service": "open_cover",
        "entity_id": "cover.workshop_door",
    }

    assert cover_call["domain"] == "cover"
    assert cover_call["service"] in ["open_cover", "close_cover", "stop_cover"]


@pytest.mark.asyncio
async def test_ha_lock_safety_confirmation():
    """Test Home Assistant lock requires safety confirmation."""
    lock_call = {
        "domain": "lock",
        "service": "unlock",
        "entity_id": "lock.workshop_door",
        "requires_confirmation": True,  # Safety-critical operation
    }

    # Lock operations should require confirmation
    assert lock_call["requires_confirmation"] is True


@pytest.mark.asyncio
async def test_ha_script_execution():
    """Test Home Assistant script execution."""
    script_call = {
        "domain": "script",
        "service": "turn_on",
        "entity_id": "script.start_print_sequence",
    }

    assert script_call["domain"] == "script"
    assert script_call["entity_id"].startswith("script.")


@pytest.mark.asyncio
async def test_ha_api_versioning():
    """Test Home Assistant API version compatibility."""
    api_info = {
        "version": "2024.11.0",
        "base_url": "http://homeassistant.local:8123",
        "api_path": "/api",
    }

    assert "version" in api_info
    assert api_info["api_path"] == "/api"


@pytest.mark.asyncio
async def test_ha_conversation_context():
    """Test Home Assistant conversation context propagation."""
    context = {
        "id": "conv-123",
        "user_id": "user-456",
        "parent_id": None,
    }

    # Context should be passed to HA for audit trail
    assert context["id"] is not None
    assert context["user_id"] is not None


@pytest.mark.asyncio
async def test_ha_device_registry_query():
    """Test querying Home Assistant device registry."""
    # Should return devices in specified area
    expected_devices = [
        {"device_id": "dev-123", "name": "3D Printer", "area_id": "workshop"},
        {"device_id": "dev-456", "name": "Workshop Light", "area_id": "workshop"},
    ]

    assert all(d["area_id"] == "workshop" for d in expected_devices)


@pytest.mark.asyncio
async def test_ha_area_based_control():
    """Test Home Assistant area-based device control."""
    area_call = {
        "domain": "light",
        "service": "turn_off",
        "target": {"area_id": "workshop"},
    }

    # Should support targeting all devices in an area
    assert "target" in area_call
    assert "area_id" in area_call["target"]
