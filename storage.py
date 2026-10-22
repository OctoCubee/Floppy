"""
storage.py — Discord-backed persistent storage for Floppy.

Primary:  #floppystorage        — one permanent message per table, edited in-place on every write.
                                  Never deleted, never duplicated.
Backup:   #floppystoragebackup  — append-only log, NEVER deleted, each message has a
                                  "↩ Restore" button that reinstates that snapshot as live data.
"""

import io
import json
from datetime import datetime, timezone
import discord
import state

STORAGE_CHANNEL_NAME = "floppystorage"
BACKUP_CHANNEL_NAME  = "floppystoragebackup"

# Tables that should always exist, even before any data is written.
KNOWN_TABLES = ["levelling", "warnings"]

# In-memory cache: { "levelling": { "user_id": xp, ... }, ... }
_cache: dict[str, dict] = {}

# Cached channel objects.
_channel: discord.TextChannel | None = None
_backup_channel: discord.TextChannel | None = None

# Live message reference per table — fetched once on startup, then edited forever.
_live_msgs: dict[str, discord.Message] = {}


# ---------------------------------------------------------------------------
# Backup restore button
# ---------------------------------------------------------------------------

class RestoreBackupButton(discord.ui.View):
    """
    Persistent button attached to every backup message.
    custom_id encodes the table name so it survives bot restarts.
    """

    def __init__(self, table: str):
        super().__init__(timeout=None)
        self.table = table

        button = discord.ui.Button(
            label="↩ Restore this backup",
            style=discord.ButtonStyle.danger,
            custom_id=f"floppy_restore:{table}",
        )
        button.callback = self.restore_callback
        self.add_item(button)

    async def restore_callback(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ Only admins can restore backups.", ephemeral=True
            )
            return

        msg = interaction.message
        if not msg.attachments:
            await interaction.response.send_message(
                "❌ No attachment found on this message.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        try:
            raw = await msg.attachments[0].read()
            data = json.loads(raw.decode("utf-8"))
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to read backup: {e}", ephemeral=True)
            return

        await write(interaction.guild, self.table, data)

        state.add_log(
            f"Storage: '{self.table}' restored from backup by {interaction.user} "
            f"(msg {msg.id})"
        )
        await interaction.followup.send(
            f"✅ `{self.table}` restored from backup ({len(data)} entries). "
            f"A new backup snapshot has been posted.",
            ephemeral=True,
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _get_or_create_channel(guild: discord.Guild, name: str) -> discord.TextChannel | None:
    """Find a private bot channel by name, creating it if missing."""
    channel = discord.utils.get(guild.text_channels, name=name)
    if channel:
        return channel
    try:
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            guild.me: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_messages=True,
            ),
        }
        channel = await guild.create_text_channel(
            name=name,
            overwrites=overwrites,
            reason="Floppy auto-created storage channel",
        )
        state.add_log(f"Storage: created #{name} automatically")
        return channel
    except Exception as e:
        state.add_log(f"Storage: failed to create #{name} — {e}")
        return None


async def _get_or_create_storage_channel(guild: discord.Guild) -> discord.TextChannel | None:
    global _channel
    if _channel and _channel.guild.id == guild.id:
        return _channel
    _channel = await _get_or_create_channel(guild, STORAGE_CHANNEL_NAME)
    return _channel


async def _get_or_create_backup_channel(guild: discord.Guild) -> discord.TextChannel | None:
    global _backup_channel
    if _backup_channel and _backup_channel.guild.id == guild.id:
        return _backup_channel
    _backup_channel = await _get_or_create_channel(guild, BACKUP_CHANNEL_NAME)
    return _backup_channel


async def _find_table_message(channel: discord.TextChannel, table: str) -> discord.Message | None:
    """Scan #floppystorage for the one permanent message belonging to this table."""
    try:
        async for msg in channel.history(limit=200):
            if (
                msg.author == channel.guild.me
                and msg.attachments
                and msg.attachments[0].filename == f"{table}.json"
            ):
                return msg
    except Exception as e:
        state.add_log(f"Storage: error scanning channel for '{table}' — {e}")
    return None


async def _ensure_pinned(msg: discord.Message):
    """Pin a table's live message so it's easy to find (needs Manage Messages)."""
    if msg.pinned:
        return
    try:
        await msg.pin(reason="Floppy live storage message")
    except discord.HTTPException as e:
        # Pin limit (50) reached or missing perms — not worth failing a write over.
        state.add_log(f"Storage: couldn't pin '{msg.id}' — {e}")


async def _post_backup(guild: discord.Guild, table: str, data: dict):
    """Append a snapshot to #floppystoragebackup. Never called if backup channel is unavailable."""
    backup_channel = await _get_or_create_backup_channel(guild)
    if not backup_channel:
        return
    try:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        raw = json.dumps(data, indent=2).encode("utf-8")
        file = discord.File(io.BytesIO(raw), filename=f"{table}.json")
        await backup_channel.send(
            content=f"📦 `{table}` backup — {len(data)} entries — {ts}",
            file=file,
            view=RestoreBackupButton(table),
        )
    except Exception as e:
        state.add_log(f"Storage: failed to post backup for '{table}' — {e}")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def read(guild: discord.Guild, table: str) -> dict:
    """Load a table from #floppystorage into the cache and return it."""
    channel = await _get_or_create_storage_channel(guild)
    if not channel:
        return _cache.get(table, {})

    msg = await _find_table_message(channel, table)
    if not msg:
        state.add_log(f"Storage: no existing message for '{table}', starting fresh")
        return _cache.get(table, {})

    # Hold a reference to this message — we'll edit it forever instead of replacing it.
    _live_msgs[table] = msg
    await _ensure_pinned(msg)

    try:
        raw = await msg.attachments[0].read()
        data = json.loads(raw.decode("utf-8"))
        _cache[table] = data
        state.add_log(f"Storage: loaded '{table}' ({len(data)} entries) from msg {msg.id}")
        return data
    except Exception as e:
        state.add_log(f"Storage: failed to read '{table}' — {e}")
        return _cache.get(table, {})


async def write(guild: discord.Guild, table: str, data: dict):
    """Persist a table to #floppystorage (edit-in-place) and snapshot to #floppystoragebackup.

    If a live message already exists for this table it is EDITED, never replaced.
    A new message is only posted the very first time (no existing message found).
    This prevents duplicate messages entirely.
    """
    _cache[table] = data

    channel = await _get_or_create_storage_channel(guild)
    if not channel:
        return

    live_msg = _live_msgs.get(table)

    # If we don't have a live message cached (e.g. cold write after a restart,
    # or load_all never adopted it), scan the channel for the existing one and
    # adopt it BEFORE ever creating a new message. This is what prevents a
    # second duplicate message from being posted.
    if not live_msg:
        live_msg = await _find_table_message(channel, table)
        if live_msg:
            _live_msgs[table] = live_msg
            state.add_log(f"Storage: adopted existing message for '{table}' (msg {live_msg.id})")

    # Merge into whatever is actually stored on the existing message rather than
    # blindly overwriting it. This way an incoming write only ever adds missing
    # keys or updates the ones it carries — it can never drop entries that were
    # already persisted (e.g. if the in-memory cache was stale/empty).
    if live_msg and live_msg.attachments:
        try:
            existing_raw = await live_msg.attachments[0].read()
            existing = json.loads(existing_raw.decode("utf-8"))
            if isinstance(existing, dict):
                merged = dict(existing)
                merged.update(data)
                data = merged
        except Exception as e:
            state.add_log(f"Storage: couldn't merge existing '{table}', writing as-is — {e}")

    # Cache + outgoing payload reflect the merged result.
    _cache[table] = data
    raw = json.dumps(data, indent=2).encode("utf-8")
    content_text = f"`{table}` — {len(data)} entries"

    if live_msg:
        # Edit the existing message in-place — zero chance of duplicates.
        try:
            file = discord.File(io.BytesIO(raw), filename=f"{table}.json")
            # edit() returns the updated message; the old object still points at the
            # replaced (now 404) attachment, so keep the fresh one for the next merge.
            live_msg = await live_msg.edit(content=content_text, attachments=[file])
            _live_msgs[table] = live_msg
            await _ensure_pinned(live_msg)
            state.add_log(f"Storage: edited '{table}' (msg {live_msg.id})")
        except discord.NotFound:
            # Message was manually deleted — fall through to re-create it.
            state.add_log(f"Storage: live message for '{table}' was deleted, re-creating")
            _live_msgs.pop(table, None)
            live_msg = None
        except Exception as e:
            state.add_log(f"Storage: failed to edit '{table}' — {e}")
            return

    if not live_msg:
        # First write ever (or message was manually deleted) — send a new one.
        try:
            file = discord.File(io.BytesIO(raw), filename=f"{table}.json")
            new_msg = await channel.send(content=content_text, file=file)
            _live_msgs[table] = new_msg
            await _ensure_pinned(new_msg)
            state.add_log(f"Storage: created live message for '{table}' (msg {new_msg.id})")
        except Exception as e:
            state.add_log(f"Storage: failed to create message for '{table}' — {e}")
            return

    # Always append a backup snapshot regardless of whether we edited or created.
    await _post_backup(guild, table, data)


def get_cached(table: str) -> dict:
    """Fast in-memory read — use this during normal operation."""
    return _cache.get(table, {})


def set_cached(table: str, data: dict):
    """Update only the in-memory cache (no Discord write)."""
    _cache[table] = data


# ---------------------------------------------------------------------------
# Startup loader — call once in on_ready
# ---------------------------------------------------------------------------

async def load_all(guild: discord.Guild):
    """Ensure both storage channels exist, then load all known tables."""
    channel = await _get_or_create_storage_channel(guild)
    if not channel:
        state.add_log("Storage: startup aborted — could not get/create storage channel")
        return

    await _get_or_create_backup_channel(guild)

    for table in KNOWN_TABLES:
        await read(guild, table)

    state.add_log(f"Storage: startup complete — {len(KNOWN_TABLES)} table(s) ready")
