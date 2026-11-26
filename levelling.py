import random
import asyncio
from datetime import datetime, timezone, timedelta
import discord
import storage
import state
import config

TRUST_TENURE = timedelta(days=7)

# ---------------------------------------------------------------------------
# XP formula: 5n² + 50n + 100
# ---------------------------------------------------------------------------

XP_PER_MESSAGE_MIN = 15
XP_PER_MESSAGE_MAX = 25
XP_COOLDOWN_SECONDS = 60
REPLY_BONUS_MULTIPLIER = 1.15
ENGAGEMENT_XP = 8
TRUST_LEVEL = 5
TABLE = "levelling"
ROLE_BATCH_SIZE = 25
ROLE_BATCH_PAUSE = 0.75


async def _apply_in_batches(items, action):
    """Run an async `action(item)` over `items`, chunked and throttled.

    Returns the number of items processed. Use for any per-member Discord call
    over a large set so we never burst past the rate limit.
    """
    done = 0
    for i in range(0, len(items), ROLE_BATCH_SIZE):
        chunk = items[i:i + ROLE_BATCH_SIZE]
        for item in chunk:
            await action(item)
            done += 1
        if i + ROLE_BATCH_SIZE < len(items):
            await asyncio.sleep(ROLE_BATCH_PAUSE)
    return done

_cooldowns: dict[int, float] = {}

def xp_for_level(level: int) -> int:
    """Total XP required to reach this level from 0."""
    return 5 * level * level + 50 * level + 100


def level_for_xp(total_xp: int) -> int:
    level = 0
    while total_xp >= xp_for_level(level + 1):
        level += 1
    return level


def xp_progress(total_xp: int) -> tuple[int, int, int]:
    """Returns (current_level, xp_into_level, xp_needed_for_next_level)."""
    level = level_for_xp(total_xp)
    xp_start = xp_for_level(level) if level > 0 else 0
    xp_end = xp_for_level(level + 1)
    return level, total_xp - xp_start, xp_end - xp_start

def get_user_xp(user_id: int) -> int:
    return storage.get_cached(TABLE).get(str(user_id), 0)


async def _set_user_xp(guild: discord.Guild, user_id: int, xp: int):
    data = dict(storage.get_cached(TABLE))
    data[str(user_id)] = xp
    storage.set_cached(TABLE, data)
    await storage.write(guild, TABLE, data)


async def wipe_user(guild: discord.Guild, user_id: int):
    """Remove a user's XP entry entirely — called on member leave."""
    data = dict(storage.get_cached(TABLE))
    if str(user_id) not in data:
        return
    del data[str(user_id)]
    storage.set_cached(TABLE, data)
    await storage.write(guild, TABLE, data)
    state.add_log(f"Levelling: wiped XP for user {user_id} (left server)")

async def handle_message(message: discord.Message):
    import time

    cfg = config.load()
    level_channel_id = cfg.get("level_channel")

    author = message.author
    now = time.monotonic()

    replied_to = None
    ref = message.reference
    if ref is not None:
        resolved = ref.resolved if isinstance(ref.resolved, discord.Message) else None
        if resolved is None and ref.message_id:
            try:
                resolved = await message.channel.fetch_message(ref.message_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                resolved = None
        if resolved and not resolved.author.bot and resolved.author.id != author.id:
            replied_to = resolved.author

    is_reply = replied_to is not None
    if now - _cooldowns.get(author.id, 0) >= XP_COOLDOWN_SECONDS:
        _cooldowns[author.id] = now

        gained = random.randint(XP_PER_MESSAGE_MIN, XP_PER_MESSAGE_MAX)
        if is_reply:
            gained = int(gained * REPLY_BONUS_MULTIPLIER)

        await _grant_xp(message.guild, author, gained, cfg, message, level_channel_id)
    if replied_to is not None:
        if now - _cooldowns.get(replied_to.id, 0) >= XP_COOLDOWN_SECONDS:
            _cooldowns[replied_to.id] = now
            await _grant_xp(
                message.guild, replied_to, ENGAGEMENT_XP, cfg, message, level_channel_id
            )


async def _grant_xp(guild, member, amount: int, cfg: dict, message, level_channel_id):
    """Add `amount` XP to `member`, handling level-up announcement and the
    level-10 trust-role swap. Shared by both the message author and the
    replied-to user so the logic lives in exactly one place."""
    if amount <= 0:
        return

    user_id = member.id
    old_xp = get_user_xp(user_id)
    new_xp = old_xp + amount

    old_level = level_for_xp(old_xp)
    new_level = level_for_xp(new_xp)

    await _set_user_xp(guild, user_id, new_xp)

    if new_level > old_level:
        state.add_log(f"Levelling: {member} reached level {new_level}")
        await _announce_level_up(message, new_level, new_xp, level_channel_id, member)

    if old_level < TRUST_LEVEL <= new_level and isinstance(member, discord.Member):
        await apply_trust_role(member, cfg)


async def apply_trust_role(member: discord.Member, cfg: dict | None = None):
    """Remove the join role and add the level-10 role. Safe to call repeatedly."""
    if cfg is None:
        cfg = config.load()

    join_role_id = cfg.get("join_role")
    trust_role_id = cfg.get("trust_role")
    if not trust_role_id:
        return

    trust_role = member.guild.get_role(int(trust_role_id))
    if trust_role is None:
        return

    member_role_ids = {r.id for r in member.roles}

    try:
        if trust_role.id not in member_role_ids:
            await member.add_roles(trust_role, reason=f"Reached level {TRUST_LEVEL}")
        if join_role_id:
            join_role = member.guild.get_role(int(join_role_id))
            if join_role and join_role.id in member_role_ids:
                await member.remove_roles(join_role, reason=f"Reached level {TRUST_LEVEL} — removing join role")
    except discord.Forbidden:
        state.add_log("Levelling: missing permissions to swap level-10 role")
    except discord.HTTPException:
        state.add_log(f"Levelling: failed to swap level-10 role for {member}")


async def revoke_trust_role(member: discord.Member, cfg: dict | None = None):
    """Inverse of apply_trust_role: remove the level-10 role when a member is
    set below level 10. Safe to call repeatedly. Does NOT re-add the join role,
    since that role is meant for brand-new arrivals, not demotions."""
    if cfg is None:
        cfg = config.load()

    trust_role_id = cfg.get("trust_role")
    if not trust_role_id:
        return

    trust_role = member.guild.get_role(int(trust_role_id))
    if trust_role is None:
        return

    if trust_role.id not in {r.id for r in member.roles}:
        return  # nothing to do

    try:
        await member.remove_roles(trust_role, reason=f"Set below level {TRUST_LEVEL}")
    except discord.Forbidden:
        state.add_log("Levelling: missing permissions to remove level-10 role")
    except discord.HTTPException:
        state.add_log(f"Levelling: failed to remove level-10 role for {member}")


async def backfill_trust_roles(guild: discord.Guild):
    """Reconcile the level-10 role for the whole guild on startup.

    Adds the role to anyone at level 10+ who lacks it, and removes it from
    anyone below level 10 who still has it (e.g. demoted while the bot was
    offline, or whose XP was manually lowered). Members with no XP entry count
    as level 0.
    """
    cfg = config.load()
    trust_role_id = cfg.get("trust_role")
    if not trust_role_id:
        return

    trust_role = guild.get_role(int(trust_role_id))
    if trust_role is None:
        state.add_log("Levelling: backfill skipped — trust role not found in guild")
        return

    xp_data = storage.get_cached(TABLE)

    # Collect the role changes first, then apply them in throttled batches so a
    # large guild on boot doesn't burst-edit roles and hit the rate limiter.
    to_add = []
    to_remove = []
    for member in guild.members:
        if member.bot:
            continue

        xp = xp_data.get(str(member.id), 0)
        qualifies = level_for_xp(xp) >= TRUST_LEVEL
        has_role = trust_role.id in {r.id for r in member.roles}

        if qualifies and not has_role:
            to_add.append(member)
        elif not qualifies and has_role:
            to_remove.append(member)

    added = await _apply_in_batches(to_add, lambda m: apply_trust_role(m, cfg))
    removed = await _apply_in_batches(to_remove, lambda m: revoke_trust_role(m, cfg))

    state.add_log(
        f"Levelling: backfill reconciled trust role — added {added}, removed {removed}"
    )


async def ensure_member_present(guild: discord.Guild, member_id: int):
    """Ensure a single member has an XP entry (at 0 if absent). Used on join so
    the table stays in sync without waiting for a reboot. No-op if they exist."""
    data = storage.get_cached(TABLE)
    if str(member_id) in data:
        return
    data = dict(data)
    data[str(member_id)] = 0
    storage.set_cached(TABLE, data)
    await storage.write(guild, TABLE, data)


async def ensure_all_members_present(guild: discord.Guild):
    """Make sure every (non-bot) member has an XP entry in the table.

    Members who joined but never sent a message — or who arrived while the bot
    was offline — won't exist in the JSON yet. This adds any missing member at
    0 XP so the table always covers the full roster. Existing entries are left
    completely untouched (no XP is changed). One bulk write, no role logic, no
    date gating.
    """
    data = dict(storage.get_cached(TABLE))
    added = 0
    for member in guild.members:
        if member.bot:
            continue
        if str(member.id) not in data:
            data[str(member.id)] = 0
            added += 1

    if not added:
        return

    storage.set_cached(TABLE, data)
    await storage.write(guild, TABLE, data)
    state.add_log(f"Levelling: added {added} missing member(s) to XP table at 0 XP")


async def grant_tenure_trust(guild: discord.Guild):
    """Auto-trust members who've been in the server at least TRUST_TENURE.

    Rather than tracking trust separately, this simply tops a qualifying member
    up to the trust level's XP threshold (if they're below it), which makes them
    qualify under all the existing level-based trust logic. We never lower
    anyone's XP here — high earners keep their real XP untouched — and we never
    remove the role: revocation stays governed purely by the XP rules elsewhere,
    so a member dropping below the threshold is still handled as before.
    """
    cfg = config.load()
    trust_role_id = cfg.get("trust_role")
    if not trust_role_id:
        return

    trust_role = guild.get_role(int(trust_role_id))
    if trust_role is None:
        state.add_log("Levelling: tenure trust skipped — trust role not found in guild")
        return

    threshold_xp = xp_for_level(TRUST_LEVEL)
    now = datetime.now(timezone.utc)

    # --- Pass 1: collect everyone who qualifies, no Discord writes yet --------
    # Doing a write per member hammers the storage channel (one message edit
    # each) and the role API, which trips Discord's 429 rate
    # limiter. So we gather first, then persist in one shot and assign in
    # throttled batches.
    qualifying = []
    for member in guild.members:
        if member.bot:
            continue
        joined = member.joined_at
        if joined is None:
            continue  # join time unknown — skip rather than guess
        if now - joined < TRUST_TENURE:
            continue
        if get_user_xp(member.id) >= threshold_xp:
            continue  # already at/above trust level — nothing to top up
        qualifying.append(member)

    if not qualifying:
        return

    # --- Pass 2: one bulk XP write for the whole batch ------------------------
    # Mutate the cache for every qualifying member, then flush ONCE. This turns
    # N storage writes into a single message edit.
    data = dict(storage.get_cached(TABLE))
    for member in qualifying:
        data[str(member.id)] = threshold_xp
    storage.set_cached(TABLE, data)
    await storage.write(guild, TABLE, data)

    # --- Pass 3: assign roles in throttled batches ---------------------------
    # Role edits are unavoidable per-member Discord calls, so chunk them with a
    # pause between chunks to stay comfortably under the rate limit.
    granted = await _apply_in_batches(qualifying, lambda m: apply_trust_role(m, cfg))

    state.add_log(f"Levelling: tenure trust granted to {granted} member(s)")


async def _announce_level_up(message: discord.Message, new_level: int, total_xp: int, level_channel_id, member=None):
    # The member leveling up may be the replier OR the person who was replied to,
    # so default to the message author only when no explicit member is passed.
    if member is None:
        member = message.author

    _, xp_into, xp_needed = xp_progress(total_xp)

    embed = discord.Embed(
        title="⬆️ Level Up!",
        description=f"{member.mention} just reached **Level {new_level}**! 🎉",
        color=0x5865f2,
    )
    embed.add_field(name="Progress", value=f"{xp_into} / {xp_needed} XP to next level", inline=False)
    embed.set_thumbnail(url=member.display_avatar.url)

    channel = None
    if level_channel_id:
        channel = message.guild.get_channel(int(level_channel_id))
    if channel is None:
        channel = message.channel

    try:
        await channel.send(embed=embed)
    except discord.Forbidden:
        state.add_log("Levelling: no permission to post in level channel")
