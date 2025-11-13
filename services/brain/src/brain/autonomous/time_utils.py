"""Time window utilities for autonomous operations."""

from datetime import datetime, time
from typing import Tuple
import pytz


def is_within_autonomous_window(
    start_hour: int = 4,
    end_hour: int = 6,
    timezone_str: str = "America/Los_Angeles"
) -> Tuple[bool, str]:
    """Check if current time is within the autonomous execution window.

    Args:
        start_hour: Start hour in 24h format (default: 4 = 4am)
        end_hour: End hour in 24h format (default: 6 = 6am)
        timezone_str: Timezone string (default: America/Los_Angeles = PST/PDT)

    Returns:
        Tuple of (is_within_window, reason_message)

    Examples:
        >>> is_within_autonomous_window(4, 6)  # At 5:30am PST
        (True, "Within autonomous window: 5:30am PST (4am-6am)")

        >>> is_within_autonomous_window(4, 6)  # At 2:00pm PST
        (False, "Outside autonomous window: 2:00pm PST (only runs 4am-6am)")
    """
    try:
        # Get current time in specified timezone
        tz = pytz.timezone(timezone_str)
        now = datetime.now(tz)
        current_hour = now.hour
        current_time_str = now.strftime("%I:%M%p %Z")

        # Check if within window
        if start_hour <= current_hour < end_hour:
            return (
                True,
                f"Within autonomous window: {current_time_str} ({start_hour}am-{end_hour}am)"
            )
        else:
            return (
                False,
                f"Outside autonomous window: {current_time_str} (only runs {start_hour}am-{end_hour}am)"
            )

    except Exception as exc:
        # Fallback to UTC if timezone fails
        now = datetime.utcnow()
        current_hour = now.hour
        return (
            start_hour <= current_hour < end_hour,
            f"Timezone error, using UTC: {now.strftime('%H:%M UTC')}"
        )


__all__ = ["is_within_autonomous_window"]
