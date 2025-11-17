# noqa: D401
"""Discovery MCP server providing device discovery and management tools."""

from __future__ import annotations

import os
from typing import Any, Dict

import httpx

from ..server import MCPServer, ResourceDefinition, ToolDefinition, ToolResult


class DiscoveryMCPServer(MCPServer):
    """MCP server for network device discovery and management."""

    def __init__(self, discovery_service_url: str | None = None) -> None:
        """Initialize Discovery MCP server.

        Args:
            discovery_service_url: Base URL for discovery service (default from env or http://discovery:8500)
        """
        super().__init__(
            name="discovery",
            description="Discover and manage network devices (3D printers, IoT devices, etc.)",
        )

        self._discovery_url = discovery_service_url or os.getenv(
            "DISCOVERY_SERVICE_URL", "http://discovery:8500"
        )

        # Register discover_devices tool
        self.register_tool(
            ToolDefinition(
                name="discover_devices",
                description="Trigger a network scan to discover devices. Scans using mDNS, SSDP, and manufacturer-specific protocols (Bamboo Labs, Snapmaker, etc.).",
                parameters={
                    "type": "object",
                    "properties": {
                        "methods": {
                            "type": "array",
                            "description": "Discovery methods to use (mdns, ssdp, bamboo_udp, snapmaker_udp, network_scan). If not specified, all enabled methods are used.",
                            "items": {"type": "string"},
                        },
                        "timeout_seconds": {
                            "type": "integer",
                            "description": "Timeout for scan in seconds",
                            "minimum": 5,
                            "maximum": 120,
                            "default": 30,
                        },
                    },
                },
            )
        )

        # Register list_devices tool
        self.register_tool(
            ToolDefinition(
                name="list_devices",
                description="List discovered devices with optional filters. Returns all devices that have been discovered on the network.",
                parameters={
                    "type": "object",
                    "properties": {
                        "device_type": {
                            "type": "string",
                            "description": "Filter by device type (printer_3d, printer_cnc, printer_laser, camera, hub, etc.)",
                        },
                        "approved": {
                            "type": "boolean",
                            "description": "Filter by approval status (true = approved, false = not approved)",
                        },
                        "is_online": {
                            "type": "boolean",
                            "description": "Filter by online status (true = currently online)",
                        },
                        "manufacturer": {
                            "type": "string",
                            "description": "Filter by manufacturer name",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of results to return",
                            "minimum": 1,
                            "maximum": 500,
                            "default": 100,
                        },
                    },
                },
            )
        )

        # Register search_devices tool
        self.register_tool(
            ToolDefinition(
                name="search_devices",
                description="Search for devices by hostname, model, manufacturer, or IP address.",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query to match against hostname, model, manufacturer, or IP address",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of results",
                            "minimum": 1,
                            "maximum": 500,
                            "default": 50,
                        },
                    },
                    "required": ["query"],
                },
            )
        )

        # Register get_device_status tool
        self.register_tool(
            ToolDefinition(
                name="get_device_status",
                description="Get detailed status and information about a specific device by its ID.",
                parameters={
                    "type": "object",
                    "properties": {
                        "device_id": {
                            "type": "string",
                            "description": "The UUID of the device to query",
                        },
                    },
                    "required": ["device_id"],
                },
            )
        )

        # Register approve_device tool
        self.register_tool(
            ToolDefinition(
                name="approve_device",
                description="Approve a discovered device for integration and control. Once approved, the device can be used by other services (like fabrication for printers).",
                parameters={
                    "type": "object",
                    "properties": {
                        "device_id": {
                            "type": "string",
                            "description": "The UUID of the device to approve",
                        },
                        "notes": {
                            "type": "string",
                            "description": "Optional notes about the approval",
                        },
                    },
                    "required": ["device_id"],
                },
            )
        )

        # Register reject_device tool
        self.register_tool(
            ToolDefinition(
                name="reject_device",
                description="Reject or unapprove a device. The device will no longer be available for use by other services.",
                parameters={
                    "type": "object",
                    "properties": {
                        "device_id": {
                            "type": "string",
                            "description": "The UUID of the device to reject",
                        },
                        "notes": {
                            "type": "string",
                            "description": "Optional notes about the rejection",
                        },
                    },
                    "required": ["device_id"],
                },
            )
        )

        # Register list_printers tool
        self.register_tool(
            ToolDefinition(
                name="list_printers",
                description="List all discovered printers (3D, CNC, laser). Convenience method for finding fabrication devices.",
                parameters={"type": "object", "properties": {}},
            )
        )

        # Register discovery resources
        self.register_resource(
            ResourceDefinition(
                uri="discovery://devices",
                name="discovered_devices",
                description="All discovered devices with full details",
                mime_type="application/json",
            )
        )

        self.register_resource(
            ResourceDefinition(
                uri="discovery://printers",
                name="discovered_printers",
                description="All discovered fabrication devices (3D/CNC/laser printers)",
                mime_type="application/json",
            )
        )

    async def execute_tool(
        self, tool_name: str, arguments: Dict[str, Any]
    ) -> ToolResult:
        """Execute Discovery tool.

        Args:
            tool_name: Name of the tool to execute
            arguments: Tool arguments

        Returns:
            ToolResult with success status and data/error
        """
        if tool_name == "discover_devices":
            return await self._discover_devices(arguments)
        elif tool_name == "list_devices":
            return await self._list_devices(arguments)
        elif tool_name == "search_devices":
            return await self._search_devices(arguments)
        elif tool_name == "get_device_status":
            return await self._get_device_status(arguments)
        elif tool_name == "approve_device":
            return await self._approve_device(arguments)
        elif tool_name == "reject_device":
            return await self._reject_device(arguments)
        elif tool_name == "list_printers":
            return await self._list_printers(arguments)

        return ToolResult(success=False, error=f"Unknown tool: {tool_name}")

    async def _discover_devices(self, arguments: Dict[str, Any]) -> ToolResult:
        """Trigger a network discovery scan.

        Args:
            arguments: Tool arguments with optional methods and timeout

        Returns:
            ToolResult with scan status
        """
        methods = arguments.get("methods")
        timeout_seconds = arguments.get("timeout_seconds", 30)

        try:
            async with httpx.AsyncClient(timeout=float(timeout_seconds + 10)) as client:
                response = await client.post(
                    f"{self._discovery_url}/api/discovery/scan",
                    json={
                        "methods": methods,
                        "timeout_seconds": timeout_seconds,
                    },
                )
                response.raise_for_status()
                data = response.json()

            return ToolResult(
                success=True,
                data={
                    "scan_id": data.get("scan_id"),
                    "status": data.get("status"),
                    "started_at": data.get("started_at"),
                    "methods": data.get("methods", []),
                    "devices_found": data.get("devices_found", 0),
                    "message": f"Discovery scan initiated with methods: {data.get('methods', [])}",
                },
                metadata={"operation": "discover"},
            )

        except httpx.HTTPStatusError as e:
            return ToolResult(
                success=False,
                error=f"Discovery service returned error: {e.response.status_code} - {e.response.text}",
            )
        except httpx.RequestError as e:
            return ToolResult(
                success=False,
                error=f"Failed to connect to discovery service: {str(e)}",
            )
        except Exception as e:
            return ToolResult(
                success=False, error=f"Failed to trigger discovery scan: {str(e)}"
            )

    async def _list_devices(self, arguments: Dict[str, Any]) -> ToolResult:
        """List discovered devices with optional filters.

        Args:
            arguments: Tool arguments with optional filters

        Returns:
            ToolResult with device list
        """
        params = {}
        if "device_type" in arguments:
            params["device_type"] = arguments["device_type"]
        if "approved" in arguments:
            params["approved"] = arguments["approved"]
        if "is_online" in arguments:
            params["is_online"] = arguments["is_online"]
        if "manufacturer" in arguments:
            params["manufacturer"] = arguments["manufacturer"]
        if "limit" in arguments:
            params["limit"] = arguments["limit"]

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self._discovery_url}/api/discovery/devices",
                    params=params,
                )
                response.raise_for_status()
                data = response.json()

            devices = data.get("devices", [])

            return ToolResult(
                success=True,
                data={
                    "devices": [
                        {
                            "device_id": dev.get("id"),
                            "device_type": dev.get("device_type"),
                            "manufacturer": dev.get("manufacturer"),
                            "model": dev.get("model"),
                            "hostname": dev.get("hostname"),
                            "ip_address": dev.get("ip_address"),
                            "approved": dev.get("approved", False),
                            "is_online": dev.get("is_online", True),
                            "discovered_at": dev.get("discovered_at"),
                            "last_seen": dev.get("last_seen"),
                        }
                        for dev in devices
                    ],
                    "total": data.get("total", 0),
                    "filters_applied": data.get("filters_applied", {}),
                },
                metadata={"operation": "list", "count": len(devices)},
            )

        except httpx.HTTPStatusError as e:
            return ToolResult(
                success=False,
                error=f"Discovery service returned error: {e.response.status_code} - {e.response.text}",
            )
        except httpx.RequestError as e:
            return ToolResult(
                success=False,
                error=f"Failed to connect to discovery service: {str(e)}",
            )
        except Exception as e:
            return ToolResult(
                success=False, error=f"Failed to list devices: {str(e)}"
            )

    async def _search_devices(self, arguments: Dict[str, Any]) -> ToolResult:
        """Search for devices.

        Args:
            arguments: Tool arguments with query and limit

        Returns:
            ToolResult with matching devices
        """
        query = arguments.get("query")
        limit = arguments.get("limit", 50)

        if not query:
            return ToolResult(success=False, error="Missing required parameter: query")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self._discovery_url}/api/discovery/search",
                    params={"q": query, "limit": limit},
                )
                response.raise_for_status()
                data = response.json()

            devices = data.get("devices", [])

            return ToolResult(
                success=True,
                data={
                    "devices": [
                        {
                            "device_id": dev.get("id"),
                            "device_type": dev.get("device_type"),
                            "manufacturer": dev.get("manufacturer"),
                            "model": dev.get("model"),
                            "hostname": dev.get("hostname"),
                            "ip_address": dev.get("ip_address"),
                            "approved": dev.get("approved", False),
                            "is_online": dev.get("is_online", True),
                        }
                        for dev in devices
                    ],
                    "total": data.get("total", 0),
                    "query": query,
                },
                metadata={"operation": "search", "query": query, "count": len(devices)},
            )

        except httpx.HTTPStatusError as e:
            return ToolResult(
                success=False,
                error=f"Discovery service returned error: {e.response.status_code} - {e.response.text}",
            )
        except httpx.RequestError as e:
            return ToolResult(
                success=False,
                error=f"Failed to connect to discovery service: {str(e)}",
            )
        except Exception as e:
            return ToolResult(
                success=False, error=f"Failed to search devices: {str(e)}"
            )

    async def _get_device_status(self, arguments: Dict[str, Any]) -> ToolResult:
        """Get device details.

        Args:
            arguments: Tool arguments with device_id

        Returns:
            ToolResult with device details
        """
        device_id = arguments.get("device_id")

        if not device_id:
            return ToolResult(
                success=False, error="Missing required parameter: device_id"
            )

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self._discovery_url}/api/discovery/devices/{device_id}"
                )
                response.raise_for_status()
                device = response.json()

            return ToolResult(
                success=True,
                data={
                    "device_id": device.get("id"),
                    "device_type": device.get("device_type"),
                    "manufacturer": device.get("manufacturer"),
                    "model": device.get("model"),
                    "hostname": device.get("hostname"),
                    "ip_address": device.get("ip_address"),
                    "mac_address": device.get("mac_address"),
                    "firmware_version": device.get("firmware_version"),
                    "services": device.get("services", []),
                    "capabilities": device.get("capabilities", {}),
                    "approved": device.get("approved", False),
                    "approved_at": device.get("approved_at"),
                    "approved_by": device.get("approved_by"),
                    "is_online": device.get("is_online", True),
                    "confidence_score": device.get("confidence_score", 0.5),
                    "discovered_at": device.get("discovered_at"),
                    "last_seen": device.get("last_seen"),
                    "notes": device.get("notes"),
                },
                metadata={"operation": "get_status"},
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return ToolResult(success=False, error="Device not found")
            return ToolResult(
                success=False,
                error=f"Discovery service returned error: {e.response.status_code} - {e.response.text}",
            )
        except httpx.RequestError as e:
            return ToolResult(
                success=False,
                error=f"Failed to connect to discovery service: {str(e)}",
            )
        except Exception as e:
            return ToolResult(
                success=False, error=f"Failed to get device status: {str(e)}"
            )

    async def _approve_device(self, arguments: Dict[str, Any]) -> ToolResult:
        """Approve a device.

        Args:
            arguments: Tool arguments with device_id and optional notes

        Returns:
            ToolResult with approval confirmation
        """
        device_id = arguments.get("device_id")
        notes = arguments.get("notes")

        if not device_id:
            return ToolResult(
                success=False, error="Missing required parameter: device_id"
            )

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self._discovery_url}/api/discovery/devices/{device_id}/approve",
                    json={"notes": notes} if notes else {},
                )
                response.raise_for_status()
                data = response.json()

            return ToolResult(
                success=True,
                data={
                    "device_id": data.get("id"),
                    "approved": data.get("approved"),
                    "approved_at": data.get("approved_at"),
                    "approved_by": data.get("approved_by"),
                    "message": "Device approved successfully and is now available for use",
                },
                metadata={"operation": "approve"},
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return ToolResult(success=False, error="Device not found")
            return ToolResult(
                success=False,
                error=f"Discovery service returned error: {e.response.status_code} - {e.response.text}",
            )
        except httpx.RequestError as e:
            return ToolResult(
                success=False,
                error=f"Failed to connect to discovery service: {str(e)}",
            )
        except Exception as e:
            return ToolResult(
                success=False, error=f"Failed to approve device: {str(e)}"
            )

    async def _reject_device(self, arguments: Dict[str, Any]) -> ToolResult:
        """Reject or unapprove a device.

        Args:
            arguments: Tool arguments with device_id and optional notes

        Returns:
            ToolResult with rejection confirmation
        """
        device_id = arguments.get("device_id")
        notes = arguments.get("notes")

        if not device_id:
            return ToolResult(
                success=False, error="Missing required parameter: device_id"
            )

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self._discovery_url}/api/discovery/devices/{device_id}/reject",
                    json={"notes": notes} if notes else {},
                )
                response.raise_for_status()
                data = response.json()

            return ToolResult(
                success=True,
                data={
                    "device_id": data.get("id"),
                    "approved": data.get("approved"),
                    "notes": data.get("notes"),
                    "message": "Device rejected successfully and is no longer available for use",
                },
                metadata={"operation": "reject"},
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return ToolResult(success=False, error="Device not found")
            return ToolResult(
                success=False,
                error=f"Discovery service returned error: {e.response.status_code} - {e.response.text}",
            )
        except httpx.RequestError as e:
            return ToolResult(
                success=False,
                error=f"Failed to connect to discovery service: {str(e)}",
            )
        except Exception as e:
            return ToolResult(
                success=False, error=f"Failed to reject device: {str(e)}"
            )

    async def _list_printers(self, arguments: Dict[str, Any]) -> ToolResult:
        """List all printers.

        Args:
            arguments: Tool arguments (unused)

        Returns:
            ToolResult with printer list
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self._discovery_url}/api/discovery/printers"
                )
                response.raise_for_status()
                data = response.json()

            devices = data.get("devices", [])

            return ToolResult(
                success=True,
                data={
                    "printers": [
                        {
                            "device_id": dev.get("id"),
                            "device_type": dev.get("device_type"),
                            "manufacturer": dev.get("manufacturer"),
                            "model": dev.get("model"),
                            "hostname": dev.get("hostname"),
                            "ip_address": dev.get("ip_address"),
                            "approved": dev.get("approved", False),
                            "is_online": dev.get("is_online", True),
                        }
                        for dev in devices
                    ],
                    "total": data.get("total", 0),
                },
                metadata={"operation": "list_printers", "count": len(devices)},
            )

        except httpx.HTTPStatusError as e:
            return ToolResult(
                success=False,
                error=f"Discovery service returned error: {e.response.status_code} - {e.response.text}",
            )
        except httpx.RequestError as e:
            return ToolResult(
                success=False,
                error=f"Failed to connect to discovery service: {str(e)}",
            )
        except Exception as e:
            return ToolResult(
                success=False, error=f"Failed to list printers: {str(e)}"
            )

    async def fetch_resource(self, uri: str) -> Dict[str, Any]:
        """Fetch a Discovery resource by URI.

        Args:
            uri: Resource URI (e.g., "discovery://devices")

        Returns:
            Resource data as dictionary
        """
        if uri == "discovery://devices":
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.get(
                        f"{self._discovery_url}/api/discovery/devices",
                        params={"limit": 500},
                    )
                    response.raise_for_status()
                    return response.json()
            except Exception as e:
                raise ValueError(f"Failed to fetch devices: {str(e)}")

        elif uri == "discovery://printers":
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.get(
                        f"{self._discovery_url}/api/discovery/printers"
                    )
                    response.raise_for_status()
                    return response.json()
            except Exception as e:
                raise ValueError(f"Failed to fetch printers: {str(e)}")

        raise ValueError(f"Unknown resource URI: {uri}")


__all__ = ["DiscoveryMCPServer"]
