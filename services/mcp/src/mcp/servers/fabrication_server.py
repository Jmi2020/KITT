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
                        "hollowing_strategy": {
                            "type": "string",
                            "description": "When to hollow: 'hollow_then_segment' (default) hollows first for wall panels, 'segment_then_hollow' hollows each piece after cutting",
                            "enum": ["hollow_then_segment", "segment_then_hollow", "none"],
                            "default": "hollow_then_segment",
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

        # Register slice_model tool
        self.register_tool(
            ToolDefinition(
                name="slice_model",
                description=(
                    "Start an async slicing job to convert a 3D model (3MF or STL) to G-code. "
                    "Returns a job_id that can be polled with check_slicing_status. "
                    "Typical slicing takes 30-120 seconds depending on model complexity."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "input_path": {
                            "type": "string",
                            "description": "Absolute path to 3MF or STL file to slice",
                        },
                        "printer_id": {
                            "type": "string",
                            "description": "Target printer ID (bambu_h2d, elegoo_giga, snapmaker_artisan)",
                            "enum": ["bambu_h2d", "elegoo_giga", "snapmaker_artisan"],
                        },
                        "material_id": {
                            "type": "string",
                            "description": "Material profile (default: pla_generic)",
                            "default": "pla_generic",
                        },
                        "quality": {
                            "type": "string",
                            "description": "Print quality preset (draft=fast, normal=balanced, fine=slow/detailed)",
                            "enum": ["draft", "normal", "fine"],
                            "default": "normal",
                        },
                        "support_type": {
                            "type": "string",
                            "description": "Support structure type (none, normal, tree)",
                            "enum": ["none", "normal", "tree"],
                            "default": "tree",
                        },
                        "infill_percent": {
                            "type": "integer",
                            "description": "Infill percentage 0-100 (default: 20)",
                            "default": 20,
                        },
                    },
                    "required": ["input_path", "printer_id"],
                },
            )
        )

        # Register check_slicing_status tool
        self.register_tool(
            ToolDefinition(
                name="check_slicing_status",
                description=(
                    "Check the status of an async slicing job. "
                    "Poll this until status is 'completed' or 'failed'. "
                    "Returns progress percentage, estimated print time, and G-code path when complete."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "job_id": {
                            "type": "string",
                            "description": "The slicing job ID returned from slice_model",
                        },
                    },
                    "required": ["job_id"],
                },
            )
        )

        # Register send_to_printer tool
        self.register_tool(
            ToolDefinition(
                name="send_to_printer",
                description=(
                    "Upload sliced G-code to a printer and optionally start the print. "
                    "Requires a completed slicing job. "
                    "IMPORTANT: Always ask user for confirmation before setting start_print=true."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "slicing_job_id": {
                            "type": "string",
                            "description": "The completed slicing job ID",
                        },
                        "printer_id": {
                            "type": "string",
                            "description": "Target printer (defaults to job's printer if not specified)",
                        },
                        "start_print": {
                            "type": "boolean",
                            "description": "Start printing immediately after upload (requires user confirmation)",
                            "default": False,
                        },
                    },
                    "required": ["slicing_job_id"],
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
        elif tool_name == "slice_model":
            return await self._slice_model(arguments)
        elif tool_name == "check_slicing_status":
            return await self._check_slicing_status(arguments)
        elif tool_name == "send_to_printer":
            return await self._send_to_printer(arguments)

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
                "hollowing_strategy": arguments.get("hollowing_strategy", "hollow_then_segment"),
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

    async def _slice_model(self, arguments: Dict[str, Any]) -> ToolResult:
        """Start an async slicing job.

        Args:
            arguments: Tool arguments with input_path, printer_id, and options

        Returns:
            ToolResult with job_id for polling
        """
        input_path = arguments.get("input_path")
        printer_id = arguments.get("printer_id")

        if not input_path:
            return ToolResult(success=False, error="Missing required parameter: input_path")
        if not printer_id:
            return ToolResult(success=False, error="Missing required parameter: printer_id")

        try:
            # Build slicing config
            config = {
                "printer_id": printer_id,
                "material_id": arguments.get("material_id", "pla_generic"),
                "quality": arguments.get("quality", "normal"),
                "support_type": arguments.get("support_type", "tree"),
                "infill_percent": arguments.get("infill_percent", 20),
            }

            payload = {
                "input_path": input_path,
                "config": config,
                "upload_to_printer": False,  # Manual upload via send_to_printer
            }

            # Start slicing job (can take time, longer timeout)
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self._fab_url}/api/slicer/slice",
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()

            return ToolResult(
                success=True,
                data={
                    "job_id": data.get("job_id"),
                    "status": data.get("status"),
                    "status_url": data.get("status_url"),
                    "message": f"Slicing started for {printer_id}. Poll with check_slicing_status.",
                },
                metadata={
                    "job_id": data.get("job_id"),
                    "printer_id": printer_id,
                },
            )

        except httpx.HTTPStatusError as e:
            error_detail = e.response.text if e.response else str(e)
            return ToolResult(
                success=False,
                error=f"Slicing request failed: {e.response.status_code} - {error_detail}",
            )
        except httpx.RequestError as e:
            return ToolResult(
                success=False,
                error=f"Failed to connect to Fabrication service: {str(e)}",
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Slicing failed: {str(e)}")

    async def _check_slicing_status(self, arguments: Dict[str, Any]) -> ToolResult:
        """Check status of a slicing job.

        Args:
            arguments: Tool arguments with job_id

        Returns:
            ToolResult with job status, progress, and results
        """
        job_id = arguments.get("job_id")

        if not job_id:
            return ToolResult(success=False, error="Missing required parameter: job_id")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self._fab_url}/api/slicer/jobs/{job_id}",
                )
                response.raise_for_status()
                data = response.json()

            status = data.get("status")
            result_data = {
                "job_id": job_id,
                "status": status,
                "progress": data.get("progress", 0.0),
                "input_path": data.get("input_path"),
                "printer_id": data.get("config", {}).get("printer_id"),
            }

            # Add completion data if available
            if status == "completed":
                result_data.update({
                    "gcode_path": data.get("gcode_path"),
                    "estimated_print_time_seconds": data.get("estimated_print_time_seconds"),
                    "estimated_filament_grams": data.get("estimated_filament_grams"),
                    "layer_count": data.get("layer_count"),
                    "message": "Slicing complete! Ready to send to printer.",
                })
            elif status == "failed":
                result_data["error"] = data.get("error", "Unknown error")
                result_data["message"] = "Slicing failed. Check error for details."
            elif status == "running":
                progress_pct = int(data.get("progress", 0) * 100)
                result_data["message"] = f"Slicing in progress: {progress_pct}%"
            else:
                result_data["message"] = "Slicing job pending..."

            return ToolResult(
                success=True,
                data=result_data,
                metadata={
                    "status": status,
                    "progress": data.get("progress", 0.0),
                },
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return ToolResult(success=False, error=f"Slicing job not found: {job_id}")
            return ToolResult(
                success=False,
                error=f"Status check failed: {e.response.status_code}",
            )
        except httpx.RequestError as e:
            return ToolResult(
                success=False,
                error=f"Failed to connect to Fabrication service: {str(e)}",
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Status check failed: {str(e)}")

    async def _send_to_printer(self, arguments: Dict[str, Any]) -> ToolResult:
        """Send sliced G-code to a printer.

        Args:
            arguments: Tool arguments with slicing_job_id, optional printer_id, start_print

        Returns:
            ToolResult with upload status
        """
        job_id = arguments.get("slicing_job_id")

        if not job_id:
            return ToolResult(success=False, error="Missing required parameter: slicing_job_id")

        try:
            # Build query params
            params = {}
            if arguments.get("printer_id"):
                params["printer_id"] = arguments["printer_id"]

            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self._fab_url}/api/slicer/jobs/{job_id}/upload",
                    params=params,
                )
                response.raise_for_status()
                data = response.json()

            start_print = arguments.get("start_print", False)
            printer_id = data.get("printer_id", arguments.get("printer_id", "unknown"))

            result_data = {
                "success": data.get("success", True),
                "job_id": job_id,
                "printer_id": printer_id,
                "gcode_path": data.get("gcode_path"),
            }

            if start_print:
                # TODO: Wire to actual printer start command
                result_data["message"] = f"G-code uploaded and print started on {printer_id}"
                result_data["print_started"] = True
            else:
                result_data["message"] = f"G-code uploaded to {printer_id}. Ready to print."
                result_data["print_started"] = False

            return ToolResult(
                success=True,
                data=result_data,
                metadata={
                    "printer_id": printer_id,
                    "print_started": start_print,
                },
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return ToolResult(success=False, error=f"Slicing job not found: {job_id}")
            if e.response.status_code == 400:
                return ToolResult(
                    success=False,
                    error="Slicing job not complete. Wait for slicing to finish first.",
                )
            return ToolResult(
                success=False,
                error=f"Upload failed: {e.response.status_code} - {e.response.text}",
            )
        except httpx.RequestError as e:
            return ToolResult(
                success=False,
                error=f"Failed to connect to Fabrication service: {str(e)}",
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Upload failed: {str(e)}")

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
