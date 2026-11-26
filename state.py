import logging
from collections import deque
from datetime import datetime, timezone

bot: object = None
logs: deque = deque(maxlen=100)

_log = logging.getLogger("floppy")


def add_log(message: str):
    """Record an event for the dashboard's live log and the container's stdout."""
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    logs.appendleft(f"[{ts}] {message}")
    _log.info(message)
