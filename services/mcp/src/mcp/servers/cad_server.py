# noqa: D401
"""CAD MCP server providing 3D model generation tools."""

from __future__ import annotations

import os
from typing import Any, Dict
from uuid import uuid4

import httpx

from ..server import MCPServer, ResourceDefinition, ToolDefinition, ToolResult


class CADMCPServer(MCPServer):
    """MCP server for CAD generation via Zoo/Tripo/local providers."""

    def __init__(self, cad_service_url: str | None = None) -> None:
        """Initialize CAD MCP server.

        Args:
            cad_service_url: Base URL for CAD service (default from env or http://localhost:8000)
        """
        super().__init__(
            name="cad",
            description="Generate 3D CAD models from text descriptions using Zoo API, Tripo, or local inference",
        )

        self._cad_url = cad_service_url or os.getenv(
            "CAD_SERVICE_URL", "http://cad:8000"
        )

        # Register generate_cad_model tool
        self.register_tool(
            ToolDefinition(
                name="generate_cad_model",
                description="Generate a 3D CAD model from a text description. Returns URLs to generated artifacts in various formats (GLTF, GLB, STEP).",
                parameters={
                    "type": "object",
                    "properties": {
                        "prompt": {
                            "type": "string",
                            "description": "Natural language description of the 3D model to generate",
                        },
                        "references": {
                            "type": "object",
                            "description": "Optional reference data (image_url, image_path, etc.)",
                            "properties": {
                                "image_url": {
                                    "type": "string",
                                    "description": "URL to reference image for mesh generation",
                                },
                                "image_path": {
                                    "type": "string",
                                    "description": "Local path to reference image",
                                },
                            },
                            "additionalProperties": True,
                        },
                        "imageRefs": {
                            "type": "array",
                            "description": "Optional list of stored image references (downloadUrl + storageUri) to forward directly to the CAD service.",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "downloadUrl": {"type": "string"},
                                    "storageUri": {"type": "string"},
                                    "sourceUrl": {"type": "string"},
                                    "title": {"type": "string"},
                                    "source": {"type": "string"},
                                    "caption": {"type": "string"},
                                    "friendlyName": {"type": "string"},
                                },
                                "additionalProperties": True,
                            },
                        },
                        "mode": {
                            "type": "string",
                            "description": "Optional generation mode hint (auto, organic, parametric). Use 'organic' when relying on reference images for Tripo.",
                            "enum": ["auto", "organic", "parametric"],
                        },
                    },
                    "required": ["prompt"],
                },
            )
        )

        # Register CAD resources
        self.register_resource(
            ResourceDefinition(
                uri="cad://recent",
                name="recent_models",
                description="Recently generated CAD models",
                mime_type="application/json",
            )
        )

    async def execute_tool(
        self, tool_name: str, arguments: Dict[str, Any]
    ) -> ToolResult:
        """Execute CAD tool.

        Args:
            tool_name: Name of the tool to execute
            arguments: Tool arguments

        Returns:
            ToolResult with success status and data/error
        """
        if tool_name == "generate_cad_model":
            return await self._generate_cad_model(arguments)

        return ToolResult(success=False, error=f"Unknown tool: {tool_name}")

    async def _generate_cad_model(self, arguments: Dict[str, Any]) -> ToolResult:
        """Generate CAD model using the CAD service API.

        Args:
            arguments: Tool arguments with prompt and optional references

        Returns:
            ToolResult with artifact URLs and metadata
        """
        prompt = arguments.get("prompt")
        references = arguments.get("references", {})
        image_refs = arguments.get("imageRefs") or arguments.get("image_refs")
        mode = arguments.get("mode")

        if not prompt:
            return ToolResult(success=False, error="Missing required parameter: prompt")

        try:
            # Generate unique conversation ID for tracking
            conversation_id = str(uuid4())

            # Call CAD service API
            payload = {
                "conversationId": conversation_id,
                "prompt": prompt,
                "references": references,
            }
            if image_refs:
                payload["imageRefs"] = image_refs
            if mode:
                payload["mode"] = mode

            # Tripo generation can take up to 5 minutes, so use 360s timeout
            async with httpx.AsyncClient(timeout=360.0) as client:
                response = await client.post(
                    f"{self._cad_url}/api/cad/generate",
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()

            artifacts = data.get("artifacts", [])

            if not artifacts:
                return ToolResult(
                    success=False, error="CAD generation produced no artifacts"
                )

            # Transform to tool result format
            result_data = {
                "conversation_id": data.get("conversationId"),
                "artifacts": [
                    {
                        "provider": art.get("provider"),
                        "format": art.get("artifactType"),
                        "url": art.get("location"),
                        "metadata": art.get("metadata", {}),
                    }
                    for art in artifacts
                ],
            }

            return ToolResult(
                success=True,
                data=result_data,
                metadata={
                    "num_artifacts": len(artifacts),
                    "providers": list({art.get("provider") for art in artifacts}),
                },
            )

        except httpx.HTTPStatusError as e:
            return ToolResult(
                success=False,
                error=f"CAD service returned error: {e.response.status_code} - {e.response.text}",
            )
        except httpx.RequestError as e:
            return ToolResult(
                success=False, error=f"Failed to connect to CAD service: {str(e)}"
            )
        except Exception as e:
            return ToolResult(success=False, error=f"CAD generation failed: {str(e)}")

    async def fetch_resource(self, uri: str) -> Dict[str, Any]:
        """Fetch a CAD resource by URI.

        Args:
            uri: Resource URI (e.g., "cad://recent")

        Returns:
            Resource data as dictionary
        """
        if uri == "cad://recent":
            # TODO: Implement fetching recent models from storage
            return {
                "models": [],
                "message": "Recent models resource not yet implemented",
            }

        raise ValueError(f"Unknown resource URI: {uri}")


__all__ = ["CADMCPServer"]
