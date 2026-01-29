"""Adelaide timezone utilities for SAGRN."""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

ADELAIDE_TZ = ZoneInfo("Australia/Adelaide")


def get_adelaide_midnight_utc() -> datetime:
    """
    Get UTC datetime for most recent midnight in Adelaide timezone.

    Returns:
        datetime: Naive datetime in UTC representing midnight Adelaide time
    """
    adelaide_now = datetime.now(ADELAIDE_TZ)
    adelaide_midnight = datetime.combine(
        adelaide_now.date(),
        time.min,
        tzinfo=ADELAIDE_TZ
    )

    # Convert to UTC and return as naive datetime
    return adelaide_midnight.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)


def get_hours_ago_adelaide(hours: int) -> datetime:
    """
    Get UTC datetime for N hours ago in Adelaide time.

    Args:
        hours: Number of hours in the past to go

    Returns:
        datetime: Naive datetime in UTC
    """
    adelaide_now = datetime.now(ADELAIDE_TZ)
    adelaide_past = adelaide_now - timedelta(hours=hours)

    # Convert to UTC and return as naive datetime
    return adelaide_past.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
