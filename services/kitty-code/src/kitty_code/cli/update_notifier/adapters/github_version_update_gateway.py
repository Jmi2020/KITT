"""GitHub version update gateway - STUBBED for airgap compliance.

Kitty Code is designed for offline-first operation. This gateway is stubbed
to prevent any external network connections to GitHub.
"""

from __future__ import annotations

from kitty_code.cli.update_notifier.ports.version_update_gateway import (
    VersionUpdate,
    VersionUpdateGateway,
)


class GitHubVersionUpdateGateway(VersionUpdateGateway):
    """Stubbed GitHub gateway that never makes external connections."""

    def __init__(
        self,
        owner: str,
        repository: str,
        **kwargs,  # Accept and ignore all other arguments for compatibility
    ) -> None:
        # Store for interface compatibility, but never use them
        self._owner = owner
        self._repository = repository

    async def fetch_update(self) -> VersionUpdate | None:
        """Always returns None - no external connections allowed."""
        return None
