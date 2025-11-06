# noqa: D401
"""Home Assistant MCP server providing device control tools."""

from __future__ import annotations

from typing import Any, Dict

from ..server import MCPServer, ResourceDefinition, ToolDefinition, ToolResult


class HomeAssistantMCPServer(MCPServer):
    """MCP server for Home Assistant device control."""

    def __init__(self, ha_client: Any = None) -> None:
        """Initialize Home Assistant MCP server.

        Args:
            ha_client: HomeAssistantClient instance (injected dependency)
        """
        super().__init__(
            name="homeassistant",
            description="Control Home Assistant devices and query entity states",
        )

        self._ha_client = ha_client

        # Register control_device tool
        self.register_tool(
            ToolDefinition(
                name="control_device",
                description="Control a Home Assistant device by calling a service. Examples: turn on lights, set thermostat, lock doors, etc.",
                parameters={
                    "type": "object",
                    "properties": {
                        "domain": {
                            "type": "string",
                            "description": "The Home Assistant domain (e.g., 'light', 'switch', 'climate', 'lock')",
                        },
                        "service": {
                            "type": "string",
                            "description": "The service to call (e.g., 'turn_on', 'turn_off', 'toggle', 'set_temperature')",
                        },
                        "entity_id": {
                            "type": "string",
                            "description": "The entity ID to control (e.g., 'light.living_room', 'switch.bedroom_fan')",
                        },
                        "service_data": {
                            "type": "object",
                            "description": "Optional additional service data (e.g., brightness, temperature, color)",
                            "additionalProperties": True,
                        },
                    },
                    "required": ["domain", "service", "entity_id"],
                },
            )
        )

        # Register get_entity_state tool
        self.register_tool(
            ToolDefinition(
                name="get_entity_state",
                description="Get the current state of a Home Assistant entity. Returns state, attributes, and metadata.",
                parameters={
                    "type": "object",
                    "properties": {
                        "entity_id": {
                            "type": "string",
                            "description": "The entity ID to query (e.g., 'light.living_room', 'sensor.temperature')",
                        },
                    },
                    "required": ["entity_id"],
                },
            )
        )

        # Register list_entities tool
        self.register_tool(
            ToolDefinition(
                name="list_entities",
                description="List all available Home Assistant entities, optionally filtered by domain.",
                parameters={
                    "type": "object",
                    "properties": {
                        "domain": {
                            "type": "string",
                            "description": "Optional domain filter (e.g., 'light', 'switch', 'sensor')",
                        },
                    },
                },
            )
        )

        # Register Home Assistant resources
        self.register_resource(
            ResourceDefinition(
                uri="homeassistant://entities",
                name="all_entities",
                description="All Home Assistant entities and their current states",
                mime_type="application/json",
            )
        )

    async def execute_tool(
        self, tool_name: str, arguments: Dict[str, Any]
    ) -> ToolResult:
        """Execute Home Assistant tool.

        Args:
            tool_name: Name of the tool to execute
            arguments: Tool arguments

        Returns:
            ToolResult with success status and data/error
        """
        if not self._ha_client:
            return ToolResult(
                success=False, error="Home Assistant client not configured"
            )

        if tool_name == "control_device":
            return await self._control_device(arguments)
        elif tool_name == "get_entity_state":
            return await self._get_entity_state(arguments)
        elif tool_name == "list_entities":
            return await self._list_entities(arguments)

        return ToolResult(success=False, error=f"Unknown tool: {tool_name}")

    async def _control_device(self, arguments: Dict[str, Any]) -> ToolResult:
        """Control a Home Assistant device.

        Args:
            arguments: Tool arguments with domain, service, entity_id, and optional service_data

        Returns:
            ToolResult with service call response
        """
        domain = arguments.get("domain")
        service = arguments.get("service")
        entity_id = arguments.get("entity_id")
        service_data = arguments.get("service_data", {})

        if not domain or not service or not entity_id:
            return ToolResult(
                success=False,
                error="Missing required parameters: domain, service, entity_id",
            )

        try:
            # Build service data payload
            data = {"entity_id": entity_id}
            if service_data:
                data.update(service_data)

            # Call Home Assistant service
            response = await self._ha_client.call_service(domain, service, data)

            return ToolResult(
                success=True,
                data={
                    "domain": domain,
                    "service": service,
                    "entity_id": entity_id,
                    "response": response,
                },
                metadata={"service_call": f"{domain}.{service}"},
            )

        except Exception as e:
            return ToolResult(
                success=False, error=f"Failed to control device: {str(e)}"
            )

    async def _get_entity_state(self, arguments: Dict[str, Any]) -> ToolResult:
        """Get the state of a Home Assistant entity.

        Args:
            arguments: Tool arguments with entity_id

        Returns:
            ToolResult with entity state and attributes
        """
        entity_id = arguments.get("entity_id")

        if not entity_id:
            return ToolResult(
                success=False, error="Missing required parameter: entity_id"
            )

        try:
            # Get all states and find the requested entity
            states_response = await self._ha_client.get_states()

            # Handle different response formats
            if isinstance(states_response, dict):
                states = states_response.get("states", [])
            elif isinstance(states_response, list):
                states = states_response
            else:
                return ToolResult(
                    success=False,
                    error=f"Unexpected states response format: {type(states_response)}",
                )

            # Find the entity
            entity = None
            for state in states:
                if state.get("entity_id") == entity_id:
                    entity = state
                    break

            if not entity:
                return ToolResult(success=False, error=f"Entity not found: {entity_id}")

            return ToolResult(
                success=True,
                data={
                    "entity_id": entity.get("entity_id"),
                    "state": entity.get("state"),
                    "attributes": entity.get("attributes", {}),
                    "last_changed": entity.get("last_changed"),
                    "last_updated": entity.get("last_updated"),
                },
            )

        except Exception as e:
            return ToolResult(
                success=False, error=f"Failed to get entity state: {str(e)}"
            )

    async def _list_entities(self, arguments: Dict[str, Any]) -> ToolResult:
        """List all Home Assistant entities, optionally filtered by domain.

        Args:
            arguments: Tool arguments with optional domain filter

        Returns:
            ToolResult with list of entities
        """
        domain_filter = arguments.get("domain")

        try:
            # Get all states
            states_response = await self._ha_client.get_states()

            # Handle different response formats
            if isinstance(states_response, dict):
                states = states_response.get("states", [])
            elif isinstance(states_response, list):
                states = states_response
            else:
                return ToolResult(
                    success=False,
                    error=f"Unexpected states response format: {type(states_response)}",
                )

            # Filter by domain if specified
            entities = []
            for state in states:
                entity_id = state.get("entity_id", "")
                if domain_filter and not entity_id.startswith(f"{domain_filter}."):
                    continue

                entities.append(
                    {
                        "entity_id": entity_id,
                        "state": state.get("state"),
                        "friendly_name": state.get("attributes", {}).get(
                            "friendly_name", entity_id
                        ),
                    }
                )

            return ToolResult(
                success=True,
                data={"entities": entities, "count": len(entities)},
                metadata={
                    "domain_filter": domain_filter if domain_filter else "none",
                    "total_count": len(entities),
                },
            )

        except Exception as e:
            return ToolResult(success=False, error=f"Failed to list entities: {str(e)}")

    async def fetch_resource(self, uri: str) -> Dict[str, Any]:
        """Fetch a Home Assistant resource by URI.

        Args:
            uri: Resource URI (e.g., "homeassistant://entities")

        Returns:
            Resource data as dictionary
        """
        if uri == "homeassistant://entities":
            if not self._ha_client:
                raise ValueError("Home Assistant client not configured")

            try:
                states_response = await self._ha_client.get_states()

                # Handle different response formats
                if isinstance(states_response, dict):
                    states = states_response.get("states", [])
                elif isinstance(states_response, list):
                    states = states_response
                else:
                    raise ValueError(
                        f"Unexpected states response format: {type(states_response)}"
                    )

                return {"entities": states, "count": len(states)}
            except Exception as e:
                raise ValueError(f"Failed to fetch entities: {str(e)}")

        raise ValueError(f"Unknown resource URI: {uri}")


__all__ = ["HomeAssistantMCPServer"]
