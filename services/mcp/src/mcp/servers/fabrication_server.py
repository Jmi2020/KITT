# noqa: D401
"""Fabrication MCP server providing mesh segmentation and 3D printing tools."""

from __future__ import annotations

import os
from typing import Any, Dict

import httpx

from ..server import MCPServer, ResourceDefinition, ToolDefinition, ToolResult


class FabricationMCPServer(MCPServer):
    """MCP server for mesh segmentation and fabrication orchestration."""

    def __init__(self, fabrication_service_url: str | None = None) -> None:
        """Initialize Fabrication MCP server.

        Args:
            fabrication_service_url: Base URL for Fabrication service
        """
        super().__init__(
            name="fabrication",
            description="Segment large 3D models for multi-part printing, manage print jobs, and orchestrate fabrication",
        )

        self._fab_url = fabrication_service_url or os.getenv(
            "FABRICATION_SERVICE_URL", "http://fabrication:8300"
        )

        # Register segment_mesh tool
        self.register_tool(
            ToolDefinition(
                name="segment_mesh",
                description=(
                    "Segment a 3D model that exceeds printer build volume into printable parts. "
                    "Automatically applies hollowing and generates alignment joints. "
                    "Returns segmented parts as 3MF files with assembly instructions."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "mesh_path": {
                            "type": "string",
                            "description": "Absolute path to 3MF or STL mesh file to segment",
                        },
                        "printer_id": {
                            "type": "string",
                            "description": "Target printer ID for build volume constraints (e.g., 'bamboo_h2d', 'elegoo_giga')",
                        },
                        "wall_thickness_mm": {
                            "type": "number",
                            "description": "Wall thickness for hollowing in mm (default: 2.0)",
                            "default": 2.0,
                        },
                        "enable_hollowing": {
                            "type": "boolean",
                            "description": "Enable mesh hollowing to save material (default: true)",
                            "default": True,
                        },
                        "joint_type": {
                            "type": "string",
                            "description": "Joint type for part assembly. 'integrated' prints pins directly on parts (no external hardware needed)",
                            "enum": ["dowel", "integrated", "dovetail", "pyramid", "none"],
                            "default": "dowel",
                        },
                        "joint_tolerance_mm": {
                            "type": "number",
                            "description": "Joint clearance/tolerance in mm (default: 0.3, recommended for FDM prints)",
                            "default": 0.3,
                        },
                        "max_parts": {
                            "type": "integer",
                            "description": "Maximum number of parts to generate (default: 10)",
                            "default": 10,
                        },
                    },
                    "required": ["mesh_path"],
                },
            )
        )

        # Register check_segmentation tool
        self.register_tool(
            ToolDefinition(
                name="check_segmentation",
                description=(
                    "Check if a 3D model needs segmentation based on printer build volume. "
                    "Returns model dimensions, build volume, and recommended number of cuts."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "mesh_path": {
                            "type": "string",
                            "description": "Absolute path to 3MF or STL mesh file to check",
                        },
                        "printer_id": {
                            "type": "string",
                            "description": "Target printer ID for build volume constraints",
                        },
                    },
                    "required": ["mesh_path"],
                },
            )
        )

        # Register list_printers tool
        self.register_tool(
            ToolDefinition(
                name="list_printers",
                description="List available printers with their build volumes and capabilities.",
                parameters={
                    "type": "object",
                    "properties": {},
                },
            )
        )

        # Register resources
        self.register_resource(
            ResourceDefinition(
                uri="fabrication://printers",
                name="printer_list",
                description="List of configured printers with build volumes",
                mime_type="application/json",
            )
        )

        self.register_resource(
            ResourceDefinition(
                uri="fabrication://jobs",
                name="print_jobs",
                description="Current print job queue and status",
                mime_type="application/json",
            )
        )

    async def execute_tool(
        self, tool_name: str, arguments: Dict[str, Any]
    ) -> ToolResult:
        """Execute fabrication tool.

        Args:
            tool_name: Name of the tool to execute
            arguments: Tool arguments

        Returns:
            ToolResult with success status and data/error
        """
        if tool_name == "segment_mesh":
            return await self._segment_mesh(arguments)
        elif tool_name == "check_segmentation":
            return await self._check_segmentation(arguments)
        elif tool_name == "list_printers":
            return await self._list_printers()

        return ToolResult(success=False, error=f"Unknown tool: {tool_name}")

    async def _segment_mesh(self, arguments: Dict[str, Any]) -> ToolResult:
        """Segment a mesh using the Fabrication service API.

        Args:
            arguments: Tool arguments with mesh_path and options

        Returns:
            ToolResult with segmented parts and assembly info
        """
        # Support both mesh_path and legacy stl_path
        mesh_path = arguments.get("mesh_path") or arguments.get("stl_path")

        if not mesh_path:
            return ToolResult(success=False, error="Missing required parameter: mesh_path")

        try:
            # Build request payload (uses stl_path alias for backwards compat)
            payload = {
                "stl_path": mesh_path,  # API accepts via alias
                "printer_id": arguments.get("printer_id"),
                "wall_thickness_mm": arguments.get("wall_thickness_mm", 2.0),
                "enable_hollowing": arguments.get("enable_hollowing", True),
                "joint_type": arguments.get("joint_type", "dowel"),
                "joint_tolerance_mm": arguments.get("joint_tolerance_mm", 0.3),
                "max_parts": arguments.get("max_parts", 10),
            }

            # Call Fabrication service API (segmentation can take time)
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(
                    f"{self._fab_url}/api/segmentation/segment",
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()

            if not data.get("success"):
                return ToolResult(
                    success=False,
                    error=data.get("error", "Segmentation failed"),
                )

            # Transform to tool result format
            result_data = {
                "needs_segmentation": data.get("needs_segmentation"),
                "num_parts": data.get("num_parts"),
                "parts": data.get("parts", []),
                "combined_3mf_path": data.get("combined_3mf_path"),
                "combined_3mf_uri": data.get("combined_3mf_uri"),
                "hardware_required": data.get("hardware_required", {}),
                "assembly_notes": data.get("assembly_notes"),
            }

            return ToolResult(
                success=True,
                data=result_data,
                metadata={
                    "num_parts": data.get("num_parts", 0),
                    "needs_segmentation": data.get("needs_segmentation", False),
                },
            )

        except httpx.HTTPStatusError as e:
            return ToolResult(
                success=False,
                error=f"Fabrication service returned error: {e.response.status_code} - {e.response.text}",
            )
        except httpx.RequestError as e:
            return ToolResult(
                success=False,
                error=f"Failed to connect to Fabrication service: {str(e)}",
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Segmentation failed: {str(e)}")

    async def _check_segmentation(self, arguments: Dict[str, Any]) -> ToolResult:
        """Check if mesh needs segmentation.

        Args:
            arguments: Tool arguments with mesh_path

        Returns:
            ToolResult with segmentation analysis
        """
        # Support both mesh_path and legacy stl_path
        mesh_path = arguments.get("mesh_path") or arguments.get("stl_path")

        if not mesh_path:
            return ToolResult(success=False, error="Missing required parameter: mesh_path")

        try:
            payload = {
                "stl_path": mesh_path,  # API accepts via alias
                "printer_id": arguments.get("printer_id"),
            }

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self._fab_url}/api/segmentation/check",
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()

            return ToolResult(
                success=True,
                data=data,
                metadata={
                    "needs_segmentation": data.get("needs_segmentation", False),
                },
            )

        except httpx.HTTPStatusError as e:
            return ToolResult(
                success=False,
                error=f"Fabrication service returned error: {e.response.status_code}",
            )
        except httpx.RequestError as e:
            return ToolResult(
                success=False,
                error=f"Failed to connect to Fabrication service: {str(e)}",
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Check failed: {str(e)}")

    async def _list_printers(self) -> ToolResult:
        """List available printers.

        Returns:
            ToolResult with printer list
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self._fab_url}/api/segmentation/printers",
                )
                response.raise_for_status()
                data = response.json()

            return ToolResult(
                success=True,
                data={"printers": data},
                metadata={"num_printers": len(data)},
            )

        except httpx.HTTPStatusError as e:
            return ToolResult(
                success=False,
                error=f"Failed to list printers: {e.response.status_code}",
            )
        except httpx.RequestError as e:
            return ToolResult(
                success=False,
                error=f"Failed to connect to Fabrication service: {str(e)}",
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to list printers: {str(e)}")

    async def fetch_resource(self, uri: str) -> Dict[str, Any]:
        """Fetch a fabrication resource by URI.

        Args:
            uri: Resource URI (e.g., "fabrication://printers")

        Returns:
            Resource data as dictionary
        """
        if uri == "fabrication://printers":
            result = await self._list_printers()
            if result.success:
                return result.data
            return {"printers": [], "error": result.error}

        if uri == "fabrication://jobs":
            # TODO: Implement job queue fetching
            return {
                "jobs": [],
                "message": "Print job queue resource not yet implemented",
            }

        raise ValueError(f"Unknown resource URI: {uri}")


__all__ = ["FabricationMCPServer"]
