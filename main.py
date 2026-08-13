import os
import asyncio
import discord
from discord import app_commands
from discord.ext import tasks
from itertools import cycle
from datetime import datetime, timezone
from dotenv import load_dotenv
import state
import config
import storage
import commands
import levelling
from tickets import OpenTicketView, TicketPanelView, handle_ticket_mention
from storage import RestoreBackupButton, KNOWN_TABLES

load_dotenv()

STATUSES = cycle([
    "🫧 floating around", "🐟 flopping about", "🗄️ peeking at the db",
    "🔌 poking the API", "🔍 searching messages", "📋 reading logs"
])

def make_embed(color, title, description=None, fields=None, footer=None, thumbnail=None):
    e = discord.Embed(title=title, description=description, color=color, timestamp=datetime.now(timezone.utc))
    if fields:
        for name, value, inline in fields:
            e.add_field(name=name, value=value, inline=inline)
    if thumbnail:
        e.set_thumbnail(url=thumbnail)
    if footer:
        e.set_footer(text=footer)
    return e

GREEN  = 0x43b581
RED    = 0xf04747
YELLOW = 0xfaa61a
BLUE   = 0x5865f2


class Floppy(discord.Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.invite_cache = {}
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        self.add_view(OpenTicketView())
        self.add_view(TicketPanelView())
        from staff_panel import StaffPanelView
        self.add_view(StaffPanelView())
        # Register one persistent RestoreBackupButton view per known table
        for table in KNOWN_TABLES:
            self.add_view(RestoreBackupButton(table))
        self.cycle_status.start()
        self.update_member_count_task.start()
        self.tenure_trust_task.start()

    async def update_member_count(self, guild):
        cfg = config.load()
        channel_id = cfg.get("member_count_channel")
        if not channel_id:
            state.add_log("Member count: no channel configured")
            return
        channel = guild.get_channel(int(channel_id)) or await guild.fetch_channel(int(channel_id))
        if not channel:
            state.add_log(f"Member count: channel {channel_id} not found")
            return
        label = cfg.get("member_count_label") or "👥 Members: {count}"
        name = label.replace("{count}", str(guild.member_count))
        try:
            if channel.name != name:
                await channel.edit(name=name, reason="Member count update")
                state.add_log(f"Member count: renamed to '{name}'")
            else:
                state.add_log(f"Member count: already up to date ('{name}')")
        except Exception as e:
            state.add_log(f"Member count: failed to rename — {e}")

    async def backfill_join_roles(self, guild):
        """Reconcile the join role across the whole guild on startup.

        Discord does NOT replay member-join events that happened while the bot
        was offline (a crash, a deploy, a host reboot). Those members never
        triggered on_member_join, so they silently never received the join role.
        This pass closes that gap: every non-bot human who has neither the join
        role nor the trust role gets the join role granted.

        Members at level 10+ correctly hold the trust role (not the join role) —
        backfill_trust_roles runs before this and handles them — so they are
        skipped here by the trust-role check.
        """
        cfg = config.load()
        join_role_id = cfg.get("join_role")
        if not join_role_id:
            state.add_log("Join backfill skipped — no join_role configured")
            return

        join_role = guild.get_role(int(join_role_id))
        if join_role is None:
            state.add_log("Join backfill skipped — join role not found in guild")
            return

        trust_role_id = cfg.get("trust_role")
        trust_role = guild.get_role(int(trust_role_id)) if trust_role_id else None

        # Collect who needs the role first, then assign in throttled batches so
        # a large guild on boot doesn't burst-edit roles and trip the 429 limiter.
        needs_role = []
        for member in guild.members:
            if member.bot:
                continue

            member_role_ids = {r.id for r in member.roles}

            # Already has the join role — nothing to do.
            if join_role.id in member_role_ids:
                continue

            # Holds the trust role (level 10+) — they've graduated past the join
            # role by design; don't re-add it.
            if trust_role and trust_role.id in member_role_ids:
                continue

            needs_role.append(member)

        granted = 0
        failed = 0
        stop = False
        for i in range(0, len(needs_role), levelling.ROLE_BATCH_SIZE):
            batch = needs_role[i:i + levelling.ROLE_BATCH_SIZE]
            for member in batch:
                try:
                    await member.add_roles(join_role, reason="Join-role backfill (missed while offline)")
                    granted += 1
                except discord.Forbidden:
                    state.add_log("Join backfill: missing permissions to add join role")
                    failed += 1
                    stop = True  # permission won't fix itself mid-loop; stop hammering the API
                    break
                except discord.HTTPException:
                    failed += 1
            if stop:
                break
            if i + levelling.ROLE_BATCH_SIZE < len(needs_role):
                await asyncio.sleep(levelling.ROLE_BATCH_PAUSE)

        state.add_log(
            f"Join backfill reconciled '{guild.name}' — granted {granted}, failed {failed}"
        )

    @tasks.loop(minutes=30)
    async def update_member_count_task(self):
        for guild in self.guilds:
            await self.update_member_count(guild)

    @update_member_count_task.before_loop
    async def before_member_count(self):
        await self.wait_until_ready()

    @tasks.loop(hours=6)
    async def tenure_trust_task(self):
        for guild in self.guilds:
            try:
                await levelling.grant_tenure_trust(guild)
            except Exception as e:
                state.add_log(f"Tenure trust task failed for {guild.name} (non-fatal): {e}")

    @tenure_trust_task.before_loop
    async def before_tenure_trust(self):
        await self.wait_until_ready()

    @tasks.loop(seconds=600)
    async def cycle_status(self):
        await self.change_presence(activity=discord.CustomActivity(name=next(STATUSES)))

    @cycle_status.before_loop
    async def before_cycle(self):
        await self.wait_until_ready()

    async def on_ready(self):
        state.bot = self
        state.add_log(f"Bot online as {self.user}")

        # Global sync is heavily rate-limited and only needs to run ONCE total,
        # not per-guild and not on every boot. Doing it per-guild every boot is a
        # 429 (rate-limit) crash vector. Guard it so it runs at most once per process.
        if not getattr(self, "_global_synced", False):
            try:
                self.tree.clear_commands(guild=None)
                await self.tree.sync()  # push empty global set, once
                self._global_synced = True
            except Exception as e:
                state.add_log(f"Global command sync failed (non-fatal): {e}")

        for guild in self.guilds:
            g = discord.Object(id=guild.id)
            # Clear and re-register guild commands fresh every boot to avoid duplicates.
            try:
                self.tree.clear_commands(guild=g)
                commands.register(self.tree, g)
                await self.tree.sync(guild=g)
                state.add_log(f"Commands synced to {guild.name}")
            except Exception as e:
                state.add_log(f"Command sync failed for {guild.name} (non-fatal): {e}")

            try:
                invites = await guild.fetch_invites()
                self.invite_cache[guild.id] = {inv.code: inv.uses for inv in invites}
            except Exception:
                pass

            try:
                await storage.load_all(guild)
                # Make sure the XP table covers the whole roster first (adds any
                # missing member at 0 XP) so later passes see everyone.
                await levelling.ensure_all_members_present(guild)
                await levelling.backfill_trust_roles(guild)
                # Top up anyone past the tenure threshold to the trust level BEFORE
                # the join-role backfill, so newly-trusted members correctly shed
                # the join role in the same pass as level-10 members.
                await levelling.grant_tenure_trust(guild)
                # Reconcile join roles AFTER trust roles: trust backfill strips the
                # join role from level-10+ members, so running join-backfill second
                # means it correctly skips them instead of re-adding a role they shed.
                await self.backfill_join_roles(guild)
            except Exception as e:
                state.add_log(f"Startup data load failed for {guild.name} (non-fatal): {e}")

        state.add_log("Ticket panel views registered (panel NOT re-sent on boot)")
        print(f"Online as {self.user}")

    async def on_disconnect(self):
        state.add_log("Bot disconnected")

    async def log(self, guild, emb):
        cfg = config.load()
        channel_id = cfg.get("audit_log_channel")
        if not channel_id:
            return
        channel = guild.get_channel(int(channel_id))
        if channel:
            try:
                await channel.send(embed=emb)
            except Exception:
                pass

    async def on_member_join(self, member):
        if member.bot:
            return
        cfg = config.load()

        # Log the join immediately, before any anti-raid action. This makes sure
        # accounts that are kicked/banned for being too new still appear as joins
        # in the audit log.
        await self.log(member.guild, make_embed(GREEN, "Member Joined", fields=[
            ("Member", f"{member.mention} ({member})", True),
            ("Account Age", f"<t:{int(member.created_at.timestamp())}:R>", True),
            ("Member #", str(member.guild.member_count), True),
        ], footer=f"ID: {member.id}"))
        state.add_log(f"Member joined: {member}")

        # Anti-raid protection: remove accounts that are too new immediately.
        # Discord exposes the account creation time through member.created_at.
        max_age_hours = cfg.get("new_account_max_age_hours", 24)
        action = str(cfg.get("new_account_action", "kick")).lower().strip()

        try:
            max_age_hours = float(max_age_hours)
        except (TypeError, ValueError):
            max_age_hours = 24

        if max_age_hours > 0:
            account_age = datetime.now(timezone.utc) - member.created_at
            if account_age.total_seconds() < max_age_hours * 3600:
                age_minutes = max(0, int(account_age.total_seconds() // 60))
                age_text = f"{age_minutes} minute(s)" if age_minutes < 120 else f"{age_minutes / 60:.1f} hour(s)"

                # Log the anti-raid action before removing the member.
                action_label = "Banned" if action == "ban" else "Kicked"
                state.add_log(
                    f"New-account protection: {action_label.lower()} {member} "
                    f"(account age {age_text}, threshold {max_age_hours:g}h)"
                )
                await self.log(member.guild, make_embed(
                    RED,
                    f"🛡️ New Account {action_label}",
                    fields=[
                        ("Member", f"{member.mention} ({member})", True),
                        ("Account Age", f"{age_text} (<t:{int(member.created_at.timestamp())}:R>)", True),
                        ("Threshold", f"{max_age_hours:g} hour(s)", True),
                        ("Action", action_label, True),
                    ],
                    footer=f"ID: {member.id}",
                ))

                try:
                    if action == "ban":
                        await member.ban(
                            reason=f"Automatic new-account protection: account younger than {max_age_hours:g} hours"
                        )
                    else:
                        await member.kick(
                            reason=f"Automatic new-account protection: account younger than {max_age_hours:g} hours"
                        )
                    await self.update_member_count(member.guild)
                except discord.Forbidden:
                    state.add_log(
                        f"New-account protection: failed to {action_label.lower()} {member} "
                        f"(missing permissions / role hierarchy)"
                    )
                except discord.HTTPException as e:
                    state.add_log(
                        f"New-account protection: Discord API failed to {action_label.lower()} "
                        f"{member}: {e}"
                    )

                # Do not give the account roles, welcome them, or add them to XP
                # after the anti-raid check, even if Discord rejected the removal.
                return

        try:
            new_invites = await member.guild.fetch_invites()
            new_map = {inv.code: inv.uses for inv in new_invites}
            old_map = self.invite_cache.get(member.guild.id, {})
            for code, uses in new_map.items():
                if uses > old_map.get(code, 0):
                    break
            self.invite_cache[member.guild.id] = new_map
        except Exception:
            pass

        role_id = cfg.get("join_role")
        if role_id:
            role = member.guild.get_role(int(role_id))
            if role:
                try:
                    await member.add_roles(role, reason="Auto join role")
                except Exception:
                    pass

        channel_id = cfg.get("welcome_channel")
        if channel_id:
            channel = member.guild.get_channel(int(channel_id))
            if channel:
                msg = cfg.get("welcome_message", "Welcome {mention} to {server}!")
                try:
                    text = msg.format(mention=member.mention, name=str(member), server=member.guild.name)
                    emb = make_embed(
                        GREEN,
                        "👋 Welcome!",
                        description=text,
                        fields=[("Account Age", f"<t:{int(member.created_at.timestamp())}:R>", True)],
                        footer=f"Member #{member.guild.member_count}",
                        thumbnail=member.display_avatar.url,
                    )
                    await channel.send(content=member.mention, embed=emb)
                except (KeyError, IndexError) as e:
                    # Bad custom template with an unknown {placeholder} — log, don't crash.
                    state.add_log(f"Welcome message template error: {e}")
                except discord.HTTPException:
                    state.add_log("Welcome message: failed to send (permissions/channel?)")

        await self.update_member_count(member.guild)
        # Make sure the new arrival exists in the XP table right away.
        try:
            await levelling.ensure_member_present(member.guild, member.id)
        except Exception as e:
            state.add_log(f"Levelling: failed to add joiner to XP table — {e}")


    async def on_member_remove(self, member):
        if member.bot:
            return
        cfg = config.load()
        channel_id = cfg.get("goodbye_channel")
        if channel_id:
            channel = member.guild.get_channel(int(channel_id))
            if channel:
                msg = cfg.get("goodbye_message", "Goodbye {mention}, we'll miss you!")
                try:
                    text = msg.format(mention=member.mention, name=str(member), server=member.guild.name)
                    emb = make_embed(
                        RED,
                        "👋 Goodbye",
                        description=text,
                        footer=f"Now {member.guild.member_count} members",
                        thumbnail=member.display_avatar.url,
                    )
                    await channel.send(embed=emb)
                except (KeyError, IndexError) as e:
                    state.add_log(f"Goodbye message template error: {e}")
                except discord.HTTPException:
                    state.add_log("Goodbye message: failed to send (permissions/channel?)")

        await self.update_member_count(member.guild)
        state.add_log(f"Member left: {member}")
        await self.log(member.guild, make_embed(RED, "Member Left", fields=[
            ("Member", f"{member} ({member.id})", False),
        ], footer=f"ID: {member.id}"))

    async def on_message_delete(self, message):
        if message.author.bot or not message.guild:
            return
        fields = [("Author", f"{message.author.mention} ({message.author})", True), ("Channel", message.channel.mention, True)]
        if message.content:
            fields.append(("Content", message.content[:1024], False))
        if message.attachments:
            fields.append(("Attachments", "\n".join(a.filename for a in message.attachments), False))
        await self.log(message.guild, make_embed(RED, "Message Deleted", fields=fields, footer=f"Author ID: {message.author.id}"))

    async def on_message_edit(self, before, after):
        if before.author.bot or not before.guild or before.content == after.content:
            return
        await self.log(before.guild, make_embed(YELLOW, "Message Edited", fields=[
            ("Author", f"{before.author.mention} ({before.author})", True),
            ("Channel", before.channel.mention, True),
            ("Jump", f"[Go to message]({after.jump_url})", True),
            ("Before", before.content[:1024] or "*empty*", False),
            ("After", after.content[:1024] or "*empty*", False),
        ], footer=f"Author ID: {before.author.id}"))

    async def on_member_update(self, before, after):
        if before.roles != after.roles:
            added = [r for r in after.roles if r not in before.roles]
            removed = [r for r in before.roles if r not in after.roles]
            fields = []
            if added:
                fields.append(("Roles Added", " ".join(r.mention for r in added), False))
            if removed:
                fields.append(("Roles Removed", " ".join(r.mention for r in removed), False))
            fields.append(("Member", f"{after.mention} ({after})", True))
            await self.log(after.guild, make_embed(BLUE, "Roles Updated", fields=fields, footer=f"ID: {after.id}"))
        if before.nick != after.nick:
            await self.log(after.guild, make_embed(YELLOW, "Nickname Changed", fields=[
                ("Member", f"{after.mention} ({after})", True),
                ("Before", before.nick or "*none*", True),
                ("After", after.nick or "*none*", True),
            ], footer=f"ID: {after.id}"))

    async def on_member_ban(self, guild, user):
        state.add_log(f"Member banned: {user}")
        await self.log(guild, make_embed(RED, "Member Banned", fields=[("User", f"{user.mention} ({user})", True)], footer=f"ID: {user.id}"))

    async def on_member_unban(self, guild, user):
        await self.log(guild, make_embed(GREEN, "Member Unbanned", fields=[("User", f"{user.mention} ({user})", True)], footer=f"ID: {user.id}"))

    async def on_guild_channel_create(self, channel):
        await self.log(channel.guild, make_embed(GREEN, "Channel Created", fields=[("Name", f"#{channel.name}", True), ("Type", str(channel.type), True)]))

    async def on_guild_channel_delete(self, channel):
        await self.log(channel.guild, make_embed(RED, "Channel Deleted", fields=[("Name", f"#{channel.name}", True), ("Type", str(channel.type), True)]))

    async def on_guild_channel_update(self, before, after):
        if before.name != after.name:
            await self.log(after.guild, make_embed(YELLOW, "Channel Renamed", fields=[("Before", f"#{before.name}", True), ("After", f"#{after.name}", True)]))

    async def on_guild_role_create(self, role):
        await self.log(role.guild, make_embed(GREEN, "Role Created", fields=[("Name", role.name, True)]))

    async def on_guild_role_delete(self, role):
        await self.log(role.guild, make_embed(RED, "Role Deleted", fields=[("Name", role.name, True)]))

    async def on_guild_role_update(self, before, after):
        if before.name != after.name:
            await self.log(after.guild, make_embed(YELLOW, "Role Renamed", fields=[("Before", before.name, True), ("After", after.name, True)]))

    async def on_invite_create(self, invite):
        if invite.guild:
            cache = self.invite_cache.get(invite.guild.id, {})
            cache[invite.code] = invite.uses or 0
            self.invite_cache[invite.guild.id] = cache
        await self.log(invite.guild, make_embed(GREEN, "Invite Created", fields=[
            ("Code", invite.code, True),
            ("Created By", str(invite.inviter), True),
            ("Max Uses", str(invite.max_uses) if invite.max_uses else "∞", True),
        ]))

    async def on_invite_delete(self, invite):
        if invite.guild:
            cache = self.invite_cache.get(invite.guild.id, {})
            cache.pop(invite.code, None)
            self.invite_cache[invite.guild.id] = cache
        await self.log(invite.guild, make_embed(RED, "Invite Deleted", fields=[("Code", invite.code, True)]))

    async def on_voice_state_update(self, member, before, after):
        if member.bot:
            return
        if before.channel is None and after.channel is not None:
            await self.log(member.guild, make_embed(GREEN, "Joined Voice", fields=[("Member", f"{member.mention} ({member})", True), ("Channel", after.channel.name, True)], footer=f"ID: {member.id}"))
        elif before.channel is not None and after.channel is None:
            await self.log(member.guild, make_embed(RED, "Left Voice", fields=[("Member", f"{member.mention} ({member})", True), ("Channel", before.channel.name, True)], footer=f"ID: {member.id}"))
        elif before.channel != after.channel:
            await self.log(member.guild, make_embed(YELLOW, "Switched Voice", fields=[("Member", f"{member.mention} ({member})", True), ("From", before.channel.name, True), ("To", after.channel.name, True)], footer=f"ID: {member.id}"))

    async def handle_verify_message(self, message: discord.Message, cfg: dict):
        """Instantly grant a role to anyone who sends a message in the verify channel."""
        channel_id = cfg.get("verify_channel")
        role_id = cfg.get("verify_role")
        if not channel_id or not role_id or message.channel.id != int(channel_id):
            return

        role = message.guild.get_role(int(role_id))
        if role is None:
            state.add_log("Verify: configured verify_role not found in guild")
            return

        if role in message.author.roles:
            return  # already has it, nothing to do

        try:
            await message.author.add_roles(role, reason="Sent a message in the verify channel")
            state.add_log(f"Verify: granted '{role.name}' to {message.author} via #{message.channel.name}")
        except discord.Forbidden:
            state.add_log("Verify: missing permissions to add verify role")
        except discord.HTTPException as e:
            state.add_log(f"Verify: failed to add role — {e}")

    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        cfg = config.load()

        # === HONEYPOT SYSTEM ===
        honeypot_ch_id = cfg.get("honeypot_channel")
        if honeypot_ch_id and message.channel.id == int(honeypot_ch_id):
            member = message.author
            guild = message.guild
            
            # 1. Isolate the user immediately by adding the honeypot role
            isolation_role_id = cfg.get("honeypot_role")
            role_added = False
            if isolation_role_id:
                isolation_role = guild.get_role(int(isolation_role_id))
                if isolation_role:
                    try:
                        await member.add_roles(isolation_role, reason="Honeypot triggered: Isolated.")
                        role_added = True
                        state.add_log(f"Honeypot: Isolated {member} ({member.id}) with role.")
                    except discord.Forbidden:
                        state.add_log(f"Honeypot: Missing permission to assign isolation role to {member}.")
            
            if not role_added:
                state.add_log(f"Honeypot: Triggered by {member}, but isolation role could not be applied.")

            # 2. Delete the trigger message itself
            try:
                await message.delete()
            except discord.Forbidden:
                pass

            # 3. Purge everything they posted in the LAST MINUTE across the server
            asyncio.create_task(self.purge_member_recent_messages(guild, member))

            # 4. Log the action to your audit channel
            emb = make_embed(
                RED,
                "🚨 Honeypot Isolated User!",
                description=f"{member.mention} was isolated and their messages from the last minute across all channels are being deleted.",
                fields=[
                    ("User", f"{member} ({member.id})", True),
                    ("Action taken", "Assigned isolation role & queued server-wide message purge (last 60s).", True),
                ]
            )
            await self.log(guild, emb)
            return  # Stop processing further for this message
        # =======================

        # Delete any plain message in the commands channel — slash commands never
        # trigger on_message, so every message here is a non-command and should go.
        commands_ch_id = commands.get_commands_channel_id(cfg)
        if commands_ch_id and message.channel.id == commands_ch_id:
            try:
                await message.delete()
            except discord.Forbidden:
                pass
            return

        await self.handle_verify_message(message, cfg)
        await handle_ticket_mention(message)
        await levelling.handle_message(message)

    async def purge_member_recent_messages(self, guild: discord.Guild, member: discord.Member):
        """Searches all text channels in the guild and deletes messages from this member sent in the last 60 seconds."""
        from datetime import timedelta
        # Calculate time cutoff (1 minute ago)
        one_minute_ago = datetime.now(timezone.utc) - timedelta(minutes=1)
        deleted_count = 0

        state.add_log(f"Honeypot: Starting 1-minute message purge for {member}...")

        for channel in guild.text_channels:
            # Check if the bot has permission to read history and manage messages in this channel
            perms = channel.permissions_for(guild.me)
            if not perms.read_messages or not perms.manage_messages:
                continue

            try:
                # Retrieve the channel's history starting from 1 minute ago
                # (We keep limit=150 in case they tried to mass spam a channel in that minute)
                async for msg in channel.history(limit=150, after=one_minute_ago):
                    if msg.author.id == member.id:
                        try:
                            await msg.delete()
                            deleted_count += 1
                        except discord.HTTPException:
                            pass
            except Exception as e:
                state.add_log(f"Honeypot purge: Error scanning #{channel.name} — {e}")

        state.add_log(f"Honeypot: Completed 1-minute purge for {member}. Deleted {deleted_count} messages.")


def get_bot():
    token = os.getenv("TOKEN")
    if not token:
        exit("Error: TOKEN missing from .env")
    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True
    intents.moderation = True
    intents.invites = True
    intents.voice_states = True
    return Floppy(intents=intents), token