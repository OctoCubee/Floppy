"""
warns.py — warning records for Floppy, persisted to Discord via storage.py.

Mirrors levelling.py's storage pattern: a single `warnings` table lives as one
permanent message in #floppystorage (edited in-place). The shape is
keyed by the warned user's ID:

    {
        "123456789": [
            {
                "reason": "spam",
                "moderator_id": "987654321",
                "timestamp": "2026-06-22T12:00:00+00:00"
            },
            ...
        ],
        ...
    }
"""

from datetime import datetime, timezone
import discord
import storage

TABLE = "warnings"


def get_user_warnings(user_id: int) -> list[dict]:
    """All warnings for a user, newest last. Fast in-memory read."""
    return storage.get_cached(TABLE).get(str(user_id), [])


def warning_count(user_id: int) -> int:
    return len(get_user_warnings(user_id))


async def add_warning(
    guild: discord.Guild,
    user_id: int,
    moderator_id: int,
    reason: str,
) -> list[dict]:
    """Append a warning for a user and persist to Discord. Returns the updated list."""
    data = dict(storage.get_cached(TABLE))  # copy
    key = str(user_id)
    user_warnings = list(data.get(key, []))
    user_warnings.append({
        "reason": reason,
        "moderator_id": str(moderator_id),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    data[key] = user_warnings
    storage.set_cached(TABLE, data)
    # Warnings are rare and important, so skip the batching delay.
    await storage.write(guild, TABLE, data, immediate=True)
    return user_warnings
