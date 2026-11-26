import copy
import json
import logging
import os
import tempfile

log = logging.getLogger("floppy.config")

CONFIG_FILE = os.path.join(os.environ.get("DATA_DIR", "."), "config.json")

DEFAULTS = {
    "welcome_channel": None,
    "welcome_message": "Welcome {mention} to {server}! 🎉",
    "goodbye_channel": None,
    "goodbye_message": "Goodbye {mention}, we'll miss you! 👋",
    # Accounts newer than this are automatically removed when they join.
    "new_account_max_age_hours": 24,
    # Supported values: "kick" or "ban".
    "new_account_action": "kick",
    "join_role": None,
    "trust_role": None,
    "audit_log_channel": None,
    "ticket_channel": None,
    "ticket_category": None,
    "ticket_closed_category": None,
    "ticket_staff_roles": [],
    "ticket_panel_message_id": None,
    "member_count_channel": None,
    "member_count_label": "👥 Members: {count}",
    "level_channel": None,
    "commands_channel": None,
    "honeypot_channel": None,
    "honeypot_role": None,
    # Delete all messages the triggered member sent during this window.
    "honeypot_purge_hours": 1,
    "honeypot_attachment_thread": None,
    # Only images/videos allowed here (text with them is fine). Text-only posts and GIFs are deleted.
    "media_channels": [],
    # NOTE: XP data is stored in Discord (#floppystorage), not here.
}

# Config is read on nearly every event, so keep a parsed copy and only re-read
# the file when it changes on disk.
_cache: dict | None = None
_cache_mtime: float | None = None


def _normalise(data: dict) -> dict:
    for k, v in DEFAULTS.items():
        if k not in data:
            data[k] = copy.deepcopy(v)
    # Migrate the old single media_channel setting to the media_channels list.
    legacy = data.pop("media_channel", None)
    if legacy and not data["media_channels"]:
        data["media_channels"] = [legacy]
    return data


def load() -> dict:
    """Return a fresh copy of the config; callers may mutate it freely."""
    global _cache, _cache_mtime
    if not os.path.exists(CONFIG_FILE):
        save(copy.deepcopy(DEFAULTS))
    mtime = os.path.getmtime(CONFIG_FILE)
    if _cache is None or mtime != _cache_mtime:
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            log.error("config.json could not be read (%s); using last good config", e)
            data = _cache if _cache is not None else copy.deepcopy(DEFAULTS)
        _cache = _normalise(data)
        _cache_mtime = mtime
    return copy.deepcopy(_cache)


def save(data: dict):
    """Write atomically so a crash mid-save can't leave a half-written file."""
    global _cache, _cache_mtime
    directory = os.path.dirname(CONFIG_FILE) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".config-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, CONFIG_FILE)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    _cache = None
    _cache_mtime = None
