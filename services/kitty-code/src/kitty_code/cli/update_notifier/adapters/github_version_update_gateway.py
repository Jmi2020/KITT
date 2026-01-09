"""GitHub version update gateway - STUBBED for airgap operation.

This module is stubbed to disable network calls for airgapped operation.
The original implementation made HTTP requests to api.github.com.
"""
from __future__ import annotations

from kitty_code.cli.update_notifier.ports.version_update_gateway import (
    VersionUpdate,
    VersionUpdateGateway,
)


class GitHubVersionUpdateGateway(VersionUpdateGateway):
    """Stubbed GitHub version update gateway for airgap operation.

    Always returns None (no update available) without making network calls.
    """

    def __init__(
        self,
        owner: str,
        repository: str,
        *,
        token: str | None = None,
        client: object | None = None,  # Was httpx.AsyncClient
        timeout: float = 5.0,
        base_url: str = "https://api.github.com",
    ) -> None:
        # Keep constructor signature for compatibility, but don't use values
        pass

    async def fetch_update(self) -> VersionUpdate | None:
        """Return None immediately - no network calls in airgap mode."""
        return None
