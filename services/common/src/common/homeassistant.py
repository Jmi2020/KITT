"""Home Assistant integration utilities."""

from __future__ import annotations

import logging
from typing import Optional

from pydantic import SecretStr

from .config import settings
from .credentials import HomeAssistantCredentials
from .discovery import discover_homeassistant
from .discovery.validator import HomeAssistantValidator

logger = logging.getLogger(__name__)


async def get_homeassistant_credentials(
    auto_discover: Optional[bool] = None,
    discovery_timeout: Optional[float] = None,
) -> Optional[HomeAssistantCredentials]:
    """Get Home Assistant credentials, with optional auto-discovery.

    Args:
        auto_discover: Enable auto-discovery (default: from settings)
        discovery_timeout: Discovery timeout in seconds (default: from settings)

    Returns:
        HomeAssistantCredentials or None if not configured/discovered
    """
    if auto_discover is None:
        auto_discover = settings.home_assistant_auto_discover

    if discovery_timeout is None:
        discovery_timeout = settings.home_assistant_discovery_timeout

    # Try auto-discovery if enabled
    if auto_discover:
        logger.info("Auto-discovering Home Assistant on local network...")
        try:
            instance = await discover_homeassistant(timeout=discovery_timeout)
            if instance:
                logger.info(
                    f"Discovered Home Assistant at {instance.base_url} "
                    f"(version: {instance.version or 'unknown'})"
                )

                # Use discovered URL, but token still needs to be configured
                base_url = instance.base_url
                token = settings.home_assistant_token

                if not token:
                    logger.warning(
                        "Home Assistant discovered but no token configured. "
                        "Set HOME_ASSISTANT_TOKEN in .env"
                    )
                    return None

                credentials = HomeAssistantCredentials(
                    base_url=base_url,
                    token=SecretStr(token),
                )

                # Validate the connection
                validator = HomeAssistantValidator()
                success, error = await validator.validate_connection(instance, token)
                if not success:
                    logger.error(f"Failed to validate Home Assistant connection: {error}")
                    return None

                logger.info("✓ Successfully connected to discovered Home Assistant instance")
                return credentials

            else:
                logger.warning(
                    f"No Home Assistant instance discovered within {discovery_timeout}s. "
                    "Falling back to configured URL."
                )

        except Exception as e:
            logger.error(f"Error during Home Assistant discovery: {e}")
            # Fall through to use configured URL

    # Use configured URL
    base_url = settings.home_assistant_base_url
    token = settings.home_assistant_token

    if not token:
        logger.warning("HOME_ASSISTANT_TOKEN not configured")
        return None

    credentials = HomeAssistantCredentials(
        base_url=base_url,
        token=SecretStr(token),
    )

    # Validate if we have credentials
    try:
        validator = HomeAssistantValidator()
        # Create a mock instance for validation
        # Parse URL to get host and port
        from urllib.parse import urlparse

        from .discovery.homeassistant import HomeAssistantInstance

        parsed = urlparse(base_url)
        host = parsed.hostname or "localhost"
        port = parsed.port or 8123

        instance = HomeAssistantInstance(
            host=host,
            port=port,
            name="configured",
            base_url=base_url,
        )

        success, error = await validator.validate_connection(instance, token)
        if not success:
            logger.error(f"Failed to validate Home Assistant connection: {error}")
            return None

        logger.info(f"✓ Connected to Home Assistant at {base_url}")
        return credentials

    except Exception as e:
        logger.error(f"Error validating Home Assistant connection: {e}")
        return None


__all__ = ["get_homeassistant_credentials"]
