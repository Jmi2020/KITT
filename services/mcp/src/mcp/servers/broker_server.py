# noqa: D401
"""Command Broker MCP server for secure command execution."""

from __future__ import annotations

import os
from typing import Any, Dict

import httpx

from ..server import MCPServer, ResourceDefinition, ToolDefinition, ToolResult


class BrokerMCPServer(MCPServer):
    """MCP server for executing system commands through secure broker."""

    def __init__(self, broker_url: str | None = None) -> None:
        """Initialize Broker MCP server.

        Args:
            broker_url: Base URL for broker service (default from env or http://broker:8777)
        """
        super().__init__(
            name="broker",
            description="Execute system commands through secure command broker with allow-list validation",
        )

        self._broker_url = broker_url or os.getenv("BROKER_URL", "http://broker:8777")
        self._fabrication_url = os.getenv("FABRICATION_BASE", "http://fabrication:8300")

        # Register execute_command tool
        self.register_tool(
            ToolDefinition(
                name="execute_command",
                description="Execute a system command through the secure command broker. All commands are validated against an allow-list and executed with privilege dropping.",
                parameters={
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "Name of the command from the allow-list (e.g., 'get_system_info', 'list_directory', 'git_status')",
                        },
                        "args": {
                            "type": "object",
                            "description": "Command arguments as key-value pairs (validated against JSON Schema)",
                            "additionalProperties": True,
                        },
                        "user_id": {
                            "type": "string",
                            "description": "User ID for audit logging (optional)",
                        },
                        "conversation_id": {
                            "type": "string",
                            "description": "Conversation ID for traceability (optional)",
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "Override timeout in seconds (optional)",
                            "minimum": 1,
                            "maximum": 600,
                        },
                    },
                    "required": ["command"],
                },
            )
        )

        # Register list_commands tool
        self.register_tool(
            ToolDefinition(
                name="list_commands",
                description="List all available commands from the broker allow-list",
                parameters={"type": "object", "properties": {}},
            )
        )

        # Register get_command_schema tool
        self.register_tool(
            ToolDefinition(
                name="get_command_schema",
                description="Get the JSON Schema for a specific command's arguments",
                parameters={
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "Name of the command",
                        }
                    },
                    "required": ["command"],
                },
            )
        )

        # Register fabrication tools
        self.register_tool(
            ToolDefinition(
                name="fabrication.open_in_slicer",
                description="Open STL model in appropriate slicer app based on size and printer availability (MANUAL WORKFLOW - DEFAULT)",
                parameters={
                    "type": "object",
                    "properties": {
                        "stl_path": {
                            "type": "string",
                            "description": "Path to STL/CAM file",
                        },
                        "print_mode": {
                            "type": "string",
                            "description": "Print mode: 3d_print (default), cnc, or laser",
                            "enum": ["3d_print", "cnc", "laser"],
                            "default": "3d_print",
                        },
                        "force_printer": {
                            "type": "string",
                            "description": "Override printer selection (bamboo_h2d, elegoo_giga, snapmaker_artisan)",
                            "enum": ["bamboo_h2d", "elegoo_giga", "snapmaker_artisan"],
                        },
                    },
                    "required": ["stl_path"],
                },
            )
        )

        self.register_tool(
            ToolDefinition(
                name="fabrication.analyze_model",
                description="Analyze STL dimensions and recommend printer without opening slicer",
                parameters={
                    "type": "object",
                    "properties": {
                        "stl_path": {
                            "type": "string",
                            "description": "Path to STL file",
                        },
                        "print_mode": {
                            "type": "string",
                            "description": "Print mode for printer selection preview",
                            "enum": ["3d_print", "cnc", "laser"],
                            "default": "3d_print",
                        },
                    },
                    "required": ["stl_path"],
                },
            )
        )

        self.register_tool(
            ToolDefinition(
                name="fabrication.printer_status",
                description="Check status of all printers (idle, printing, offline)",
                parameters={"type": "object", "properties": {}},
            )
        )

        # Register broker://commands resource
        self.register_resource(
            ResourceDefinition(
                uri="broker://commands",
                name="Available Commands",
                description="List of all commands available in the broker allow-list",
                mime_type="application/json",
            )
        )

    async def execute_tool(
        self, tool_name: str, arguments: Dict[str, Any]
    ) -> ToolResult:
        """Execute a broker tool.

        Args:
            tool_name: Name of the tool to execute
            arguments: Tool arguments

        Returns:
            ToolResult with command output or error
        """
        if tool_name == "execute_command":
            return await self._execute_command(arguments)
        elif tool_name == "list_commands":
            return await self._list_commands()
        elif tool_name == "get_command_schema":
            return await self._get_command_schema(arguments)
        elif tool_name == "fabrication.open_in_slicer":
            return await self._open_in_slicer(arguments)
        elif tool_name == "fabrication.analyze_model":
            return await self._analyze_model(arguments)
        elif tool_name == "fabrication.printer_status":
            return await self._printer_status()
        else:
            return ToolResult(
                success=False,
                output="",
                error=f"Unknown tool: {tool_name}",
            )

    async def _execute_command(self, arguments: Dict[str, Any]) -> ToolResult:
        """Execute command through broker.

        Args:
            arguments: Command execution arguments

        Returns:
            ToolResult with stdout/stderr
        """
        command = arguments.get("command")
        args = arguments.get("args", {})
        user_id = arguments.get("user_id")
        conversation_id = arguments.get("conversation_id")
        timeout = arguments.get("timeout")

        if not command:
            return ToolResult(
                success=False,
                output="",
                error="Missing required argument: command",
            )

        try:
            async with httpx.AsyncClient(timeout=timeout or 60.0) as client:
                payload = {
                    "command": command,
                    "args": args,
                }
                if user_id:
                    payload["user_id"] = user_id
                if conversation_id:
                    payload["conversation_id"] = conversation_id
                if timeout:
                    payload["timeout"] = timeout

                response = await client.post(
                    f"{self._broker_url}/exec",
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()

                success = data.get("success", False)
                stdout = data.get("stdout", "")
                stderr = data.get("stderr", "")
                exit_code = data.get("exit_code", -1)
                timeout_exceeded = data.get("timeout_exceeded", False)
                error = data.get("error")

                # Format output
                output_parts = []
                if stdout:
                    output_parts.append(f"STDOUT:\n{stdout}")
                if stderr:
                    output_parts.append(f"STDERR:\n{stderr}")
                if timeout_exceeded:
                    output_parts.append(f"Command timed out after {timeout}s")
                output_parts.append(f"Exit code: {exit_code}")

                output = "\n\n".join(output_parts)

                return ToolResult(
                    success=success,
                    output=output,
                    error=error,
                    metadata={
                        "command": command,
                        "exit_code": exit_code,
                        "timeout_exceeded": timeout_exceeded,
                    },
                )

        except httpx.HTTPStatusError as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Broker API error: {e.response.status_code} - {e.response.text}",
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to execute command: {e}",
            )

    async def _list_commands(self) -> ToolResult:
        """List available commands from broker.

        Returns:
            ToolResult with command list
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self._broker_url}/commands")
                response.raise_for_status()
                data = response.json()

                commands = data.get("commands", [])
                output_lines = ["Available commands:"]
                for cmd in commands:
                    name = cmd.get("name")
                    desc = cmd.get("description", "")
                    launch_type = cmd.get("launch_type", "")
                    timeout = cmd.get("timeout", 0)
                    output_lines.append(
                        f"  - {name}: {desc} (type={launch_type}, timeout={timeout}s)"
                    )

                return ToolResult(
                    success=True,
                    output="\n".join(output_lines),
                    metadata={"commands": commands},
                )

        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to list commands: {e}",
            )

    async def _get_command_schema(self, arguments: Dict[str, Any]) -> ToolResult:
        """Get JSON Schema for command arguments.

        Args:
            arguments: Tool arguments with command name

        Returns:
            ToolResult with JSON Schema
        """
        command = arguments.get("command")
        if not command:
            return ToolResult(
                success=False,
                output="",
                error="Missing required argument: command",
            )

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self._broker_url}/commands/{command}/schema"
                )
                response.raise_for_status()
                data = response.json()

                import json

                output = json.dumps(data, indent=2)

                return ToolResult(
                    success=True,
                    output=output,
                    metadata=data,
                )

        except httpx.HTTPStatusError:
            return ToolResult(
                success=False,
                output="",
                error=f"Command not found: {command}",
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to get command schema: {e}",
            )

    async def fetch_resource(self, uri: str) -> Dict[str, Any]:
        """Fetch a broker resource by URI.

        Args:
            uri: Resource URI (e.g., "broker://commands")

        Returns:
            Resource data as dict

        Raises:
            ValueError: If URI is invalid
        """
        if uri == "broker://commands":
            # Return list of available commands
            result = await self._list_commands()
            if result.success:
                return {
                    "uri": uri,
                    "content": result.output,
                    "metadata": result.metadata,
                }
            else:
                raise ValueError(f"Failed to fetch commands: {result.error}")
        else:
            raise ValueError(f"Unknown resource URI: {uri}")

    async def read_resource(self, uri: str) -> str:
        """Read broker resource.

        Args:
            uri: Resource URI

        Returns:
            Resource content as string
        """
        if uri == "broker://commands":
            # Return list of available commands
            result = await self._list_commands()
            if result.success:
                return result.output
            else:
                return f"Error: {result.error}"
        else:
            return f"Unknown resource: {uri}"

    async def _open_in_slicer(self, arguments: Dict[str, Any]) -> ToolResult:
        """Open STL in appropriate slicer app.

        Args:
            arguments: Tool arguments with stl_path, print_mode, force_printer

        Returns:
            ToolResult with printer selection and app launch status
        """
        stl_path = arguments.get("stl_path")
        print_mode = arguments.get("print_mode", "3d_print")
        force_printer = arguments.get("force_printer")

        if not stl_path:
            return ToolResult(
                success=False,
                output="",
                error="Missing required argument: stl_path",
            )

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                payload = {
                    "stl_path": stl_path,
                    "print_mode": print_mode,
                }
                if force_printer:
                    payload["force_printer"] = force_printer

                response = await client.post(
                    f"{self._fabrication_url}/api/fabrication/open_in_slicer",
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()

                # Format output message
                printer_id = data.get("printer_id", "unknown")
                slicer_app = data.get("slicer_app", "unknown")
                reasoning = data.get("reasoning", "")
                dimensions = data.get("model_dimensions", {})
                max_dim = dimensions.get("max_dimension", 0)

                output = (
                    f"✓ Opened {stl_path} in {slicer_app}\n\n"
                    f"Printer: {printer_id}\n"
                    f"Model size: {max_dim:.1f}mm (max dimension)\n"
                    f"Reasoning: {reasoning}\n\n"
                    f"Please complete slicing and printing in the {slicer_app} application."
                )

                return ToolResult(
                    success=True,
                    output=output,
                    metadata=data,
                )

        except httpx.HTTPStatusError as e:
            error_detail = e.response.text
            return ToolResult(
                success=False,
                output="",
                error=f"Fabrication service error ({e.response.status_code}): {error_detail}",
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to open slicer: {e}",
            )

    async def _analyze_model(self, arguments: Dict[str, Any]) -> ToolResult:
        """Analyze STL dimensions without opening slicer.

        Args:
            arguments: Tool arguments with stl_path, print_mode

        Returns:
            ToolResult with model dimensions and printer recommendation
        """
        stl_path = arguments.get("stl_path")
        print_mode = arguments.get("print_mode", "3d_print")

        if not stl_path:
            return ToolResult(
                success=False,
                output="",
                error="Missing required argument: stl_path",
            )

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self._fabrication_url}/api/fabrication/analyze_model",
                    json={"stl_path": stl_path, "print_mode": print_mode},
                )
                response.raise_for_status()
                data = response.json()

                dimensions = data.get("dimensions", {})
                recommended_printer = data.get("recommended_printer", "unknown")
                slicer_app = data.get("slicer_app", "unknown")
                reasoning = data.get("reasoning", "")
                printer_available = data.get("printer_available", False)

                # Format dimensions
                width = dimensions.get("width", 0)
                depth = dimensions.get("depth", 0)
                height = dimensions.get("height", 0)
                max_dim = dimensions.get("max_dimension", 0)
                volume = dimensions.get("volume", 0)

                availability = "✓ Available" if printer_available else "✗ Busy/Offline"

                output = (
                    f"Model Analysis: {stl_path}\n\n"
                    f"Dimensions:\n"
                    f"  Width:  {width:.1f}mm\n"
                    f"  Depth:  {depth:.1f}mm\n"
                    f"  Height: {height:.1f}mm\n"
                    f"  Max:    {max_dim:.1f}mm\n"
                    f"  Volume: {volume:.0f}mm³\n\n"
                    f"Recommended Printer: {recommended_printer} ({slicer_app})\n"
                    f"Status: {availability}\n"
                    f"Reasoning: {reasoning}"
                )

                return ToolResult(
                    success=True,
                    output=output,
                    metadata=data,
                )

        except httpx.HTTPStatusError as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Fabrication service error ({e.response.status_code}): {e.response.text}",
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to analyze model: {e}",
            )

    async def _printer_status(self) -> ToolResult:
        """Get status of all printers.

        Returns:
            ToolResult with printer statuses
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self._fabrication_url}/api/fabrication/printer_status"
                )
                response.raise_for_status()
                data = response.json()

                printers = data.get("printers", {})

                # Format output
                output_lines = ["Printer Status:\n"]
                for printer_id, status in printers.items():
                    is_online = status.get("is_online", False)
                    is_printing = status.get("is_printing", False)
                    printer_status = status.get("status", "unknown")
                    current_job = status.get("current_job")

                    status_icon = "✓" if is_online else "✗"
                    state_icon = "🔨" if is_printing else "💤"

                    output_lines.append(
                        f"  {status_icon} {printer_id}: {printer_status} {state_icon}"
                    )
                    if current_job:
                        output_lines.append(f"      Job: {current_job}")
                        progress = status.get("progress_percent")
                        if progress is not None:
                            output_lines.append(f"      Progress: {progress}%")

                return ToolResult(
                    success=True,
                    output="\n".join(output_lines),
                    metadata=data,
                )

        except httpx.HTTPStatusError as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Fabrication service error ({e.response.status_code}): {e.response.text}",
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to get printer status: {e}",
            )


__all__ = ["BrokerMCPServer"]
