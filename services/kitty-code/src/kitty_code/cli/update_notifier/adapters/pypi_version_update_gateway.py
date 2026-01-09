"""PyPI version update gateway - STUBBED for airgap operation.

This module is stubbed to disable network calls for airgapped operation.
The original implementation made HTTP requests to pypi.org.
"""
from __future__ import annotations

from kitty_code.cli.update_notifier.ports.version_update_gateway import (
    VersionUpdate,
    VersionUpdateGateway,
)


class PyPIVersionUpdateGateway(VersionUpdateGateway):
    """Stubbed PyPI version update gateway for airgap operation.

    Always returns None (no update available) without making network calls.
    """

    def __init__(
        self,
        project_name: str,
        *,
        client: object | None = None,  # Was httpx.AsyncClient
        timeout: float = 5.0,
        base_url: str = "https://pypi.org",
    ) -> None:
        # Keep constructor signature for compatibility, but don't use values
        pass

    async def fetch_update(self) -> VersionUpdate | None:
        """Return None immediately - no network calls in airgap mode."""
        return None
