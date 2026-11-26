"""
staff_panel.py — the single /staff control panel.

A panel of buttons (persistent view) that exposes staff actions:
  • ⚠️ Warn        — pick a member, then a modal for the reason
  • 📋 View Warns   — pick a member, see their warning history
  • 🏓 Ping         — quick latency check

Warnings are stored on Discord through warns.py (table "warnings"), exactly
like levelling — keyed by the warned user's ID.

All views are persistent (timeout=None, fixed custom_ids) so the buttons keep
working after a bot restart. They're registered in main.py's setup_hook.
"""

import discord
from datetime import datetime, timedelta, timezone
import config
import levelling
import state
import warns

PANEL_COLOR = 0x5865f2
WARN_COLOR = 0xf1c40f


# ---------------------------------------------------------------------------
# Permission helper
# ---------------------------------------------------------------------------

def is_staff(interaction: discord.Interaction) -> bool:
    cfg = config.load()
    staff_role_ids = [str(x) for x in cfg.get("ticket_staff_roles", [])]
    member = interaction.user
    if getattr(member, "guild_permissions", None) and member.guild_permissions.administrator:
        return True
    return any(str(r.id) in staff_role_ids for r in getattr(member, "roles", []))


async def _guard(interaction: discord.Interaction) -> bool:
    """Block non-staff. Returns True if allowed."""
    if is_staff(interaction):
        return True
    await interaction.response.send_message(
        "❌ Only staff can use this.", ephemeral=True
    )
    return False


def is_admin(interaction: discord.Interaction) -> bool:
    member = interaction.user
    return bool(getattr(member, "guild_permissions", None) and member.guild_permissions.administrator)


async def _guard_admin(interaction: discord.Interaction) -> bool:
    """Block non-admins. Returns True if allowed."""
    if is_admin(interaction):
        return True
    await interaction.response.send_message(
        "❌ Only admins can use this.", ephemeral=True
    )
    return False


async def _audit(interaction: discord.Interaction, title: str, fields: list[tuple[str, str, bool]]):
    """Record a staff action in the audit log channel."""
    e = discord.Embed(title=title, color=PANEL_COLOR, timestamp=datetime.now(timezone.utc))
    e.add_field(name="Staff", value=f"{interaction.user.mention} ({interaction.user})", inline=True)
    for name, value, inline in fields:
        e.add_field(name=name, value=value[:1024], inline=inline)
    e.set_footer(text=f"Staff ID: {interaction.user.id}")
    log = getattr(interaction.client, "log", None)
    if log:
        await log(interaction.guild, e)
    state.add_log(f"Staff: {title} by {interaction.user}")


def panel_embed() -> discord.Embed:
    e = discord.Embed(
        title="🛠️ Staff Panel",
        description=(
            "Pick an action below.\n\n"
            "⚠️ **Warn** — warn a member (stored permanently)\n"
            "📋 **View Warnings** — see a member's warning history\n"
            "🗑️ **Purge** — delete messages from a given ID up to now\n"
            "📈 **Set Level** — set a member's level (admin only)\n"
            "🏓 **Ping** — check the bot's latency"
        ),
        color=PANEL_COLOR,
    )
    e.set_footer(text="Staff only • actions are logged")
    return e


# ---------------------------------------------------------------------------
# The panel itself
# ---------------------------------------------------------------------------

class StaffPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Warn", style=discord.ButtonStyle.danger, emoji="⚠️",
        custom_id="staff:warn",
    )
    async def warn_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await _guard(interaction):
            return
        await interaction.response.send_message(
            "Select the member to warn:",
            view=WarnMemberSelectView(),
            ephemeral=True,
        )

    @discord.ui.button(
        label="View Warnings", style=discord.ButtonStyle.secondary, emoji="📋",
        custom_id="staff:viewwarns",
    )
    async def view_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await _guard(interaction):
            return
        await interaction.response.send_message(
            "Select the member to look up:",
            view=ViewWarnsMemberSelectView(),
            ephemeral=True,
        )

    @discord.ui.button(
        label="Purge", style=discord.ButtonStyle.danger, emoji="🗑️",
        custom_id="staff:purge",
    )
    async def purge_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await _guard(interaction):
            return
        await interaction.response.send_modal(PurgeModal(interaction.channel))

    @discord.ui.button(
        label="Set Level", style=discord.ButtonStyle.secondary, emoji="📈",
        custom_id="staff:setlevel",
    )
    async def setlevel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await _guard_admin(interaction):
            return
        await interaction.response.send_message(
            "Select the member to update:",
            view=SetLevelMemberSelectView(),
            ephemeral=True,
        )

    @discord.ui.button(
        label="Ping", style=discord.ButtonStyle.secondary, emoji="🏓",
        custom_id="staff:ping",
    )
    async def ping_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await _guard(interaction):
            return
        latency = round(interaction.client.latency * 1000)
        await interaction.response.send_message(
            f"🏓 Pong! Latency is **{latency}ms**", ephemeral=True
        )


# ---------------------------------------------------------------------------
# Warn flow: member select  →  reason modal  →  store
# ---------------------------------------------------------------------------

class WarnMemberSelectView(discord.ui.View):
    """Ephemeral, short-lived select shown after pressing Warn."""

    def __init__(self):
        super().__init__(timeout=120)

    @discord.ui.select(
        cls=discord.ui.UserSelect,
        placeholder="Choose a member to warn…",
        min_values=1,
        max_values=1,
    )
    async def pick(self, interaction: discord.Interaction, select: discord.ui.UserSelect):
        if not await _guard(interaction):
            return
        member = select.values[0]
        if member.id == interaction.user.id:
            await interaction.response.send_message(
                "❌ You can't warn yourself.", ephemeral=True
            )
            return
        if member.bot:
            await interaction.response.send_message(
                "❌ You can't warn a bot.", ephemeral=True
            )
            return
        await interaction.response.send_modal(WarnReasonModal(member))


class WarnReasonModal(discord.ui.Modal, title="Warn Member"):
    reason = discord.ui.TextInput(
        label="Reason",
        placeholder="Why is this member being warned?",
        style=discord.TextStyle.paragraph,
        max_length=500,
    )

    def __init__(self, member: discord.Member):
        super().__init__()
        self.member = member

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        user_warnings = await warns.add_warning(
            interaction.guild,
            self.member.id,
            interaction.user.id,
            self.reason.value,
        )
        count = len(user_warnings)

        embed = discord.Embed(
            title="⚠️ Member Warned",
            description=f"{self.member.mention} has been warned.",
            color=WARN_COLOR,
        )
        embed.add_field(name="Reason", value=self.reason.value, inline=False)
        embed.add_field(name="Total Warnings", value=str(count), inline=True)
        embed.add_field(name="Moderator", value=interaction.user.mention, inline=True)
        embed.set_thumbnail(url=self.member.display_avatar.url)
        await interaction.followup.send(embed=embed, ephemeral=True)

        await _audit(interaction, "⚠️ Member Warned", [
            ("Member", f"{self.member.mention} ({self.member})", True),
            ("Total Warnings", str(count), True),
            ("Reason", self.reason.value, False),
        ])

        # Best-effort DM to the warned member.
        try:
            dm = discord.Embed(
                title=f"⚠️ You were warned in {interaction.guild.name}",
                description=self.reason.value,
                color=WARN_COLOR,
            )
            dm.set_footer(text=f"You now have {count} warning(s).")
            await self.member.send(embed=dm)
        except (discord.Forbidden, discord.HTTPException):
            pass


# ---------------------------------------------------------------------------
# View-warnings flow: member select  →  list
# ---------------------------------------------------------------------------

class ViewWarnsMemberSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)

    @discord.ui.select(
        cls=discord.ui.UserSelect,
        placeholder="Choose a member to look up…",
        min_values=1,
        max_values=1,
    )
    async def pick(self, interaction: discord.Interaction, select: discord.ui.UserSelect):
        if not await _guard(interaction):
            return
        member = select.values[0]
        user_warnings = warns.get_user_warnings(member.id)

        if not user_warnings:
            await interaction.response.send_message(
                f"✅ {member.mention} has no warnings.", ephemeral=True
            )
            return

        lines = []
        for i, w in enumerate(user_warnings, start=1):
            when = ""
            ts = w.get("timestamp", "")
            try:
                dt = datetime.fromisoformat(ts)
                when = f" · <t:{int(dt.timestamp())}:R>"
            except (ValueError, TypeError):
                pass
            mod_id = w.get("moderator_id")
            mod = f"<@{mod_id}>" if mod_id else "Unknown"
            lines.append(f"`#{i}` {w.get('reason', 'No reason')} — by {mod}{when}")

        # Embed descriptions cap at 4096 characters; keep the newest warnings.
        description = "\n".join(lines)
        while len(description) > 4000 and len(lines) > 1:
            lines.pop(0)
            description = "… older warnings hidden …\n" + "\n".join(lines)

        embed = discord.Embed(
            title=f"⚠️ Warnings for {member.display_name}",
            description=description,
            color=WARN_COLOR,
        )
        embed.set_footer(text=f"{len(user_warnings)} total")
        embed.set_thumbnail(url=member.display_avatar.url)
        await interaction.response.send_message(embed=embed, ephemeral=True)


# ---------------------------------------------------------------------------
# Purge flow: modal asks for a message ID, deletes from there up to now
# ---------------------------------------------------------------------------

class PurgeModal(discord.ui.Modal, title="Purge Messages"):
    message_id = discord.ui.TextInput(
        label="Oldest message ID to delete",
        placeholder="Right-click a message → Copy Message ID",
        max_length=30,
    )

    def __init__(self, channel: discord.TextChannel):
        super().__init__()
        self.channel = channel

    async def on_submit(self, interaction: discord.Interaction):
        if not await _guard(interaction):
            return

        try:
            after_id = int(self.message_id.value.strip())
        except ValueError:
            await interaction.response.send_message(
                "❌ That doesn't look like a valid message ID.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        try:
            anchor = await self.channel.fetch_message(after_id)
        except discord.NotFound:
            await interaction.followup.send(
                "❌ Couldn't find that message in this channel.", ephemeral=True
            )
            return
        except discord.HTTPException as e:
            await interaction.followup.send(f"❌ Couldn't fetch that message: {e}", ephemeral=True)
            return

        to_delete = [anchor]
        async for msg in self.channel.history(limit=None, after=anchor, oldest_first=True):
            to_delete.append(msg)

        # Keep the purge out of the per-message audit log; one summary entry
        # is posted below instead.
        bot = interaction.client
        if hasattr(bot, "suppress_delete_log"):
            for m in to_delete:
                bot.suppress_delete_log(m.id)

        cutoff = discord.utils.utcnow() - timedelta(days=14)
        bulk = [m for m in to_delete if m.created_at > cutoff]
        slow = [m for m in to_delete if m.created_at <= cutoff]
        deleted = 0
        error = None

        try:
            for i in range(0, len(bulk), 100):
                chunk = bulk[i:i + 100]
                if len(chunk) == 1:
                    await chunk[0].delete()
                else:
                    await self.channel.delete_messages(chunk)
                deleted += len(chunk)

            for msg in slow:
                try:
                    await msg.delete()
                    deleted += 1
                except discord.NotFound:
                    pass
        except discord.Forbidden:
            error = "I don't have permission to delete messages here."
        except discord.HTTPException as e:
            error = str(e)

        if deleted:
            await _audit(interaction, "🗑️ Messages Purged", [
                ("Channel", self.channel.mention, True),
                ("Deleted", str(deleted), True),
            ])

        if error:
            await interaction.followup.send(
                f"⚠️ Stopped after deleting **{deleted}** message(s): {error}", ephemeral=True
            )
            return

        await interaction.followup.send(
            f"🗑️ Deleted **{deleted}** message(s).", ephemeral=True
        )


# ---------------------------------------------------------------------------
# Set Level flow (admin only): member select  →  level modal  →  apply
# ---------------------------------------------------------------------------

class SetLevelMemberSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)

    @discord.ui.select(
        cls=discord.ui.UserSelect,
        placeholder="Choose a member to update…",
        min_values=1,
        max_values=1,
    )
    async def pick(self, interaction: discord.Interaction, select: discord.ui.UserSelect):
        if not await _guard_admin(interaction):
            return
        await interaction.response.send_modal(SetLevelModal(select.values[0]))


class SetLevelModal(discord.ui.Modal, title="Set Level"):
    level = discord.ui.TextInput(
        label="Level",
        placeholder="The level to set them to (e.g. 5)",
        max_length=4,
    )

    def __init__(self, member: discord.Member):
        super().__init__()
        self.member = member

    async def on_submit(self, interaction: discord.Interaction):
        if not await _guard_admin(interaction):
            return

        try:
            target_level = int(self.level.value.strip())
        except ValueError:
            await interaction.response.send_message(
                "❌ That doesn't look like a valid number.", ephemeral=True
            )
            return

        if target_level < 0:
            await interaction.response.send_message(
                "❌ Level can't be negative.", ephemeral=True
            )
            return

        # Set XP to the minimum required for the requested level (1 XP past the
        # threshold so level_for_xp lands exactly on `level`); level 0 -> 1 XP.
        new_xp = (levelling.xp_for_level(target_level) + 1) if target_level > 0 else 1

        await interaction.response.defer(ephemeral=True)

        cfg = config.load()
        old_level = levelling.level_for_xp(levelling.get_user_xp(self.member.id))
        await levelling._set_user_xp(interaction.guild, self.member.id, new_xp)

        # Keep the trust role in sync with the new value
        if levelling.level_for_xp(new_xp) >= levelling.TRUST_LEVEL:
            await levelling.apply_trust_role(self.member, cfg)
        else:
            await levelling.revoke_trust_role(self.member, cfg)

        lv, xp_into, xp_needed = levelling.xp_progress(new_xp)
        embed = discord.Embed(title=f"✅ Updated {self.member.display_name}", color=0x5865f2)
        embed.add_field(name="Level", value=str(lv), inline=True)
        embed.add_field(name="Total XP", value=str(new_xp), inline=True)
        embed.add_field(name="Progress", value=f"{xp_into}/{xp_needed} XP", inline=False)
        embed.set_thumbnail(url=self.member.display_avatar.url)
        await interaction.followup.send(embed=embed, ephemeral=True)

        await _audit(interaction, "📈 Level Set", [
            ("Member", f"{self.member.mention} ({self.member})", True),
            ("Level", f"{old_level} → {lv}", True),
        ])
