"""PyPI version update gateway - STUBBED for airgap compliance.

Kitty Code is designed for offline-first operation. This gateway is stubbed
to prevent any external network connections to PyPI.
"""

from __future__ import annotations

from kitty_code.cli.update_notifier.ports.version_update_gateway import (
    VersionUpdate,
    VersionUpdateGateway,
)


class PyPIVersionUpdateGateway(VersionUpdateGateway):
    """Stubbed PyPI gateway that never makes external connections."""

    def __init__(
        self,
        project_name: str,
        **kwargs,  # Accept and ignore all other arguments for compatibility
    ) -> None:
        # Store project_name for interface compatibility, but never use it
        self._project_name = project_name

    async def fetch_update(self) -> VersionUpdate | None:
        """Always returns None - no external connections allowed."""
        return None
