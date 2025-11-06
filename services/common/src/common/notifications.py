"""Notification service for KITTY - supports SMS, push notifications, and more."""

from __future__ import annotations

import os
import subprocess
from typing import Optional

import httpx


class NotificationService:
    """Send notifications via multiple channels."""

    def __init__(
        self,
        twilio_account_sid: Optional[str] = None,
        twilio_auth_token: Optional[str] = None,
        twilio_from_number: Optional[str] = None,
        twilio_to_number: Optional[str] = None,
        enable_sms: bool = False,
        enable_macos: bool = True,
    ):
        """Initialize notification service.

        Args:
            twilio_account_sid: Twilio account SID
            twilio_auth_token: Twilio auth token
            twilio_from_number: Twilio phone number (from)
            twilio_to_number: Phone number to send SMS to
            enable_sms: Enable SMS notifications
            enable_macos: Enable macOS notifications
        """
        self.twilio_account_sid = twilio_account_sid or os.getenv("TWILIO_ACCOUNT_SID")
        self.twilio_auth_token = twilio_auth_token or os.getenv("TWILIO_AUTH_TOKEN")
        self.twilio_from = twilio_from_number or os.getenv("TWILIO_FROM_NUMBER")
        self.twilio_to = twilio_to_number or os.getenv("TWILIO_TO_NUMBER")
        self.enable_sms = enable_sms or os.getenv("NOTIFICATIONS_SMS_ENABLED", "").lower() == "true"
        self.enable_macos = (
            enable_macos or os.getenv("NOTIFICATIONS_MACOS_ENABLED", "true").lower() == "true"
        )
        self.enabled = os.getenv("NOTIFICATIONS_ENABLED", "true").lower() == "true"

    async def notify(
        self,
        title: str,
        message: str,
        sound: str = "default",
        sms: bool = True,
        macos: bool = True,
    ) -> dict[str, bool]:
        """Send notification via all enabled channels.

        Args:
            title: Notification title
            message: Notification message
            sound: Sound to play (macOS)
            sms: Send SMS if enabled
            macos: Send macOS notification if enabled

        Returns:
            Dict with success status for each channel
        """
        if not self.enabled:
            return {"sms": False, "macos": False}

        results = {}

        if sms and self.enable_sms:
            results["sms"] = await self._send_sms(f"{title}: {message}")
        else:
            results["sms"] = False

        if macos and self.enable_macos:
            results["macos"] = self._send_macos_notification(title, message, sound)
        else:
            results["macos"] = False

        return results

    async def _send_sms(self, message: str) -> bool:
        """Send SMS via Twilio.

        Args:
            message: Message to send

        Returns:
            True if successful
        """
        if not all(
            [self.twilio_account_sid, self.twilio_auth_token, self.twilio_from, self.twilio_to]
        ):
            return False

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"https://api.twilio.com/2010-04-01/Accounts/{self.twilio_account_sid}/Messages.json",
                    auth=(self.twilio_account_sid, self.twilio_auth_token),
                    data={
                        "From": self.twilio_from,
                        "To": self.twilio_to,
                        "Body": message,
                    },
                )
                return response.status_code == 201
        except Exception:
            return False

    def _send_macos_notification(self, title: str, message: str, sound: str = "default") -> bool:
        """Send macOS notification via osascript.

        Args:
            title: Notification title
            message: Notification message
            sound: Sound to play

        Returns:
            True if successful
        """
        try:
            script = f'display notification "{message}" with title "{title}" sound name "{sound}"'
            subprocess.run(
                ["osascript", "-e", script],
                check=True,
                capture_output=True,
                timeout=5,
            )
            return True
        except Exception:
            return False


# Singleton instance
_notification_service: Optional[NotificationService] = None


def get_notification_service() -> NotificationService:
    """Get or create singleton notification service instance."""
    global _notification_service
    if _notification_service is None:
        _notification_service = NotificationService()
    return _notification_service


async def notify(title: str, message: str, **kwargs) -> dict[str, bool]:
    """Convenience function to send notification.

    Args:
        title: Notification title
        message: Notification message
        **kwargs: Additional arguments passed to NotificationService.notify()

    Returns:
        Dict with success status for each channel
    """
    service = get_notification_service()
    return await service.notify(title, message, **kwargs)


__all__ = ["NotificationService", "get_notification_service", "notify"]
