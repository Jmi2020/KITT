"""FastAPI application for Command Broker service."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .audit import AuditLogger
from .config import CommandRegistry, load_settings
from .executor import CommandExecutor, ExecutionResult

# Load settings
settings = load_settings()

# Initialize FastAPI app
app = FastAPI(
    title="KITTY Command Broker",
    description="Secure command execution broker with allow-list and privilege dropping",
    version="0.1.0",
)

# Initialize components
try:
    registry = CommandRegistry(settings.allow_list_path)
    executor = CommandExecutor(
        service_user=settings.service_user,
        enable_privilege_drop=settings.enable_privilege_drop,
    )
    audit_logger = AuditLogger(settings.audit_log_path)
except Exception as e:
    # Fail fast if initialization fails
    raise RuntimeError(f"Failed to initialize broker: {e}") from e


class ExecuteRequest(BaseModel):
    """Request to execute a command."""

    command: str = Field(..., description="Command name from allow-list")
    args: Dict[str, Any] = Field(default_factory=dict, description="Command arguments")
    user_id: Optional[str] = Field(default=None, description="User ID for audit")
    conversation_id: Optional[str] = Field(
        default=None, description="Conversation ID for traceability"
    )
    timeout: Optional[int] = Field(
        default=None, description="Override timeout in seconds"
    )


class ExecuteResponse(BaseModel):
    """Response from command execution."""

    success: bool
    command: str
    stdout: str = ""
    stderr: str = ""
    exit_code: int
    timeout_exceeded: bool = False
    error: Optional[str] = None


class CommandInfo(BaseModel):
    """Information about an available command."""

    name: str
    description: str
    launch_type: str
    timeout: int


class CommandListResponse(BaseModel):
    """List of available commands."""

    commands: List[CommandInfo]


@app.get("/healthz")
async def healthz() -> Dict[str, str]:
    """Health check endpoint.

    Returns:
        Status message
    """
    return {"status": "healthy", "service": "command-broker"}


@app.get("/commands", response_model=CommandListResponse)
async def list_commands() -> CommandListResponse:
    """List all available commands from allow-list.

    Returns:
        List of command metadata
    """
    commands = registry.list_commands()
    return CommandListResponse(commands=[CommandInfo(**cmd) for cmd in commands])


@app.get("/commands/{command_name}/schema")
async def get_command_schema(command_name: str) -> Dict[str, Any]:
    """Get JSON Schema for command arguments.

    Args:
        command_name: Name of command

    Returns:
        JSON Schema for command arguments

    Raises:
        HTTPException: If command not found
    """
    cmd_def = registry.get_command(command_name)
    if not cmd_def:
        raise HTTPException(
            status_code=404, detail=f"Command '{command_name}' not found"
        )

    return {
        "command": command_name,
        "description": cmd_def.description,
        "args_schema": cmd_def.args_schema,
        "launch_type": cmd_def.launch_type,
        "timeout": cmd_def.timeout,
    }


@app.post("/exec", response_model=ExecuteResponse)
async def execute_command(request: ExecuteRequest) -> ExecuteResponse:
    """Execute a command from the allow-list.

    Args:
        request: Execution request with command name and arguments

    Returns:
        Execution result with stdout, stderr, and exit code

    Raises:
        HTTPException: If command not found or execution fails
    """
    # Get command definition
    cmd_def = registry.get_command(request.command)
    if not cmd_def:
        raise HTTPException(
            status_code=404,
            detail=f"Command '{request.command}' not found in allow-list",
        )

    # Execute command
    result: ExecutionResult = await executor.execute(
        command_def=cmd_def,
        args=request.args,
        timeout=request.timeout,
    )

    # Log to audit log
    audit_logger.log_execution(
        command_name=request.command,
        args=request.args,
        result={
            "success": result.success,
            "exit_code": result.exit_code,
            "timeout_exceeded": result.timeout_exceeded,
            "error": result.error,
        },
        user_id=request.user_id,
        conversation_id=request.conversation_id,
    )

    # Return response
    return ExecuteResponse(
        success=result.success,
        command=result.command,
        stdout=result.stdout,
        stderr=result.stderr,
        exit_code=result.exit_code,
        timeout_exceeded=result.timeout_exceeded,
        error=result.error,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=settings.host, port=settings.port)
