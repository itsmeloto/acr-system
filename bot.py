import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import config
import sys
import asyncio
from collections import deque
from datetime import datetime, timedelta, timezone

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.presences = True # Required for checking member status

bot = commands.Bot(command_prefix=config.BOT_PREFIX, intents=intents)

# Professional Color Scheme
class ProfessionalColors:
    PRIMARY = 0xFFD700      # Gold/Yellow
    SECONDARY = 0x87CEEB    # Sky Blue
    ACCENT = 0xFFFFFF       # White
    SUCCESS = 0x00FF7F      # Spring Green
    WARNING = 0xFFA500      # Orange
    ERROR = 0xFF4444        # Red
    INFO = 0x4169E1         # Royal Blue
    NEUTRAL = 0x708090      # Slate Gray

# Professional Embed Templates
class EmbedTemplates:
    @staticmethod
    def success(title: str, description: str = "", **kwargs) -> discord.Embed:
        embed = discord.Embed(
            title=f"✅ {title}",
            description=description,
            color=ProfessionalColors.SUCCESS,
            **kwargs
        )
        return embed
    
    @staticmethod
    def error(title: str, description: str = "", **kwargs) -> discord.Embed:
        embed = discord.Embed(
            title=f"❌ {title}",
            description=description,
            color=ProfessionalColors.ERROR,
            **kwargs
        )
        return embed
    
    @staticmethod
    def warning(title: str, description: str = "", **kwargs) -> discord.Embed:
        embed = discord.Embed(
            title=f"⚠️ {title}",
            description=description,
            color=ProfessionalColors.WARNING,
            **kwargs
        )
        return embed
    
    @staticmethod
    def info(title: str, description: str = "", **kwargs) -> discord.Embed:
        embed = discord.Embed(
            title=f"ℹ️ {title}",
            description=description,
            color=ProfessionalColors.INFO,
            **kwargs
        )
        return embed
    
    @staticmethod
    def primary(title: str, description: str = "", **kwargs) -> discord.Embed:
        embed = discord.Embed(
            title=title,
            description=description,
            color=ProfessionalColors.PRIMARY,
            **kwargs
        )
        return embed
    
    @staticmethod
    def secondary(title: str, description: str = "", **kwargs) -> discord.Embed:
        embed = discord.Embed(
            title=title,
            description=description,
            color=ProfessionalColors.SECONDARY,
            **kwargs
        )
        return embed

# --- Profile Utilities ---
def get_member_access_level(member: discord.Member) -> int:
    """Return the highest configured access level the member currently has (0 if none)."""
    if not member or not getattr(member, "roles", None):
        return 0
    user_role_ids = {role.id for role in member.roles}
    highest = 0
    for level, role_ids in config.ACCESS_LEVELS.items():
        if any(rid in user_role_ids for rid in role_ids):
            highest = max(highest, level)
    return highest

def detect_member_rank(member: discord.Member):
    """Attempt to detect the member's configured staff rank.

    Returns a tuple: (rank_name, perm_role_obj, display_role_obj, team_role_obj)
    or (None, None, None, None) if not matched.
    """
    if not member:
        return (None, None, None, None)
    member_role_ids = {role.id for role in member.roles}
    best_match = None
    best_score = -1
    # Score by number of role matches among perm/display/team (prefer full triple)
    for rank_name, cfg in getattr(config, 'RANKS', {}).items():
        perm_id = cfg.get("perm_role")
        display_id = cfg.get("display_role")
        team_id = cfg.get("team_role")
        score = 0
        score += 1 if perm_id in member_role_ids else 0
        score += 1 if display_id in member_role_ids else 0
        score += 1 if team_id in member_role_ids else 0
        if score > best_score:
            best_score = score
            best_match = (rank_name, perm_id, display_id, team_id)
    if not best_match or best_score <= 0:
        return (None, None, None, None)
    rank_name, perm_id, display_id, team_id = best_match
    guild = member.guild
    return (
        rank_name,
        guild.get_role(perm_id) if perm_id else None,
        guild.get_role(display_id) if display_id else None,
        guild.get_role(team_id) if team_id else None,
    )

def detect_member_team_label(member: discord.Member) -> str | None:
    """Return the team name label based on TEAM_ROLE_IDS if the member has one."""
    if not member:
        return None
    member_role_ids = {role.id for role in member.roles}
    for team_name, team_id in getattr(config, 'TEAM_ROLE_IDS', {}).items():
        if team_id in member_role_ids:
            return team_name.replace("_", " ").title()
    return None

# --- Access Control Functions ---
def has_access_level(subject, required_level):
    """Return True if the invoker has at least the required access level.

    Supports both discord.ext.commands Context (message commands) and
    discord.Interaction (component interactions/buttons).
    """
    guild = None
    member = None

    # Message command context
    if hasattr(subject, "guild") and hasattr(subject, "author"):
        guild = subject.guild
        member = subject.author
    # Component interaction
    elif hasattr(subject, "guild") and hasattr(subject, "user"):
        guild = subject.guild
        member = subject.user

    if not guild or not member:
        return False

    user_roles = [role.id for role in getattr(member, "roles", [])]

    for level, role_ids_for_level in config.ACCESS_LEVELS.items():
        if level >= required_level:
            for role_id in role_ids_for_level:
                if role_id in user_roles:
                    return True
    return False

def access_level_required(level):
    async def predicate(ctx):
        if not has_access_level(ctx, level):
            embed = EmbedTemplates.error(
                "Access Denied",
                f"You need **Access Level {level}** or higher to use this command.\n\n"
                f"**Current Access Levels:**\n"
                f"• **Level 1:** Moderation Team\n"
                f"• **Level 2:** Admin Team\n"
                f"• **Level 3:** Head Team\n"
                f"• **Level 4:** Management & Development Team\n"
                f"• **Level 5:** Lead & Ownership Team"
            )
            embed.set_footer(text="Contact a staff member if you believe this is an error.")
            await ctx.send(embed=embed)
            return False
        return True
    return commands.check(predicate)

# --- Logging Function ---
async def log_action(ctx, action_description, color=ProfessionalColors.NEUTRAL):
    log_channel_id = config.CHANNEL_VARS.get("log-channel")
    if log_channel_id:
        log_channel = bot.get_channel(log_channel_id)
        if log_channel:
            embed = discord.Embed(
                title="📋 Bot Action Log",
                description=action_description,
                color=color,
                timestamp=ctx.message.created_at
            )
            embed.set_author(
                name=ctx.author.display_name, 
                icon_url=ctx.author.avatar.url if ctx.author.avatar else None
            )
            embed.set_footer(
                text=f"Command: {ctx.command.name} | Guild: {ctx.guild.name}",
                icon_url=ctx.guild.icon.url if ctx.guild.icon else None
            )
            try:
                await log_channel.send(embed=embed)
            except discord.Forbidden:
                print(f"Error: Bot does not have permissions to send messages in log channel {log_channel.name}")
        else:
            print(f"Warning: Log channel with ID {log_channel_id} not found.")
    else:
        print("Warning: 'log-channel' not configured in config.py.")

# Log helper for component interactions (buttons/selects)
async def log_action_interaction(interaction: discord.Interaction, action_description: str, color=ProfessionalColors.NEUTRAL):
    log_channel_id = config.CHANNEL_VARS.get("log-channel")
    if not log_channel_id:
        print("Warning: 'log-channel' not configured in config.py.")
        return
    log_channel = bot.get_channel(log_channel_id)
    if not log_channel:
        print(f"Warning: Log channel with ID {log_channel_id} not found.")
        return
    embed = discord.Embed(
        title="📋 Bot Action Log",
        description=action_description,
        color=color,
        timestamp=discord.utils.utcnow()
    )
    embed.set_author(
        name=interaction.user.display_name if interaction.user else "Unknown",
        icon_url=interaction.user.avatar.url if interaction.user and interaction.user.avatar else None
    )
    if interaction.guild:
        embed.set_footer(
            text=f"Panel Action | Guild: {interaction.guild.name}",
            icon_url=interaction.guild.icon.url if interaction.guild.icon else None
        )
    try:
        await log_channel.send(embed=embed)
    except discord.Forbidden:
        print(f"Error: Bot does not have permissions to send messages in log channel {getattr(log_channel, 'name', log_channel_id)}")

# --- Appeal System Classes and Views ---
class AppealButtonView(discord.ui.View):
    def __init__(self, banned_user_id: int):
        super().__init__(timeout=180) # Timeout after 3 minutes
        self.banned_user_id = banned_user_id

    @discord.ui.button(label="📝 Start Appeal", style=discord.ButtonStyle.primary, emoji="📝")
    async def start_appeal_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AppealModal(self.banned_user_id))

class AppealModal(discord.ui.Modal, title="📝 Ban Appeal Form"):
    def __init__(self, banned_user_id: int):
        super().__init__()
        self.banned_user_id = banned_user_id

    when_banned = discord.ui.TextInput(
        label="📅 When were you banned?",
        placeholder="e.g., Yesterday, 2 weeks ago, Oct 25th",
        max_length=100,
        required=True
    )
    reason_mentioned = discord.ui.TextInput(
        label="📋 What was the reason mentioned in the ban?",
        placeholder="e.g., 'Rule 3 violation', 'Spamming'",
        max_length=500,
        required=True
    )
    why_banned = discord.ui.TextInput(
        label="🤔 Why do you think you were really banned?",
        placeholder="Your perspective on the situation.",
        style=discord.TextStyle.paragraph,
        required=True
    )
    real_scenario = discord.ui.TextInput(
        label="📖 Real scenario of what happened (if you think it's wrong)",
        placeholder="Describe what truly happened from your point of view.",
        style=discord.TextStyle.paragraph,
        required=False
    )

    async def on_submit(self, interaction: discord.Interaction):
        appeal_embed = EmbedTemplates.info(
            title="📝 New Ban Appeal Received",
            description="A new ban appeal has been submitted and requires staff review."
        )
        appeal_embed.add_field(name="👤 Banned User ID", value=f"`{self.banned_user_id}`", inline=True)
        appeal_embed.add_field(name="📧 Appealer", value=interaction.user.mention, inline=True)
        appeal_embed.add_field(name="🕒 When Banned", value=self.when_banned.value, inline=False)
        appeal_embed.add_field(name="📋 Reason Mentioned", value=self.reason_mentioned.value, inline=False)
        appeal_embed.add_field(name="🤔 Their Perspective", value=self.why_banned.value, inline=False)
        if self.real_scenario.value:
            appeal_embed.add_field(name="📖 Real Scenario", value=self.real_scenario.value, inline=False)
        appeal_embed.set_footer(
            text=f"Appeal submitted by {interaction.user.display_name}", 
            icon_url=interaction.user.avatar.url if interaction.user.avatar else None
        )
        appeal_embed.timestamp = discord.utils.utcnow()

        appeal_log_channel = bot.get_channel(config.APPEAL_LOG_CHANNEL)
        if appeal_log_channel:
            await appeal_log_channel.send(embed=appeal_embed, view=AppealReviewView(self.banned_user_id, interaction.user.id))
            await interaction.response.send_message("Your appeal has been submitted for review! Staff will get back to you soon.", ephemeral=True)
        else:
            await interaction.response.send_message("Error: Appeal log channel not found. Please contact an administrator.", ephemeral=True)

class AppealReviewView(discord.ui.View):
    def __init__(self, banned_user_id: int, appealer_id: int):
        super().__init__(timeout=None)
        self.banned_user_id = banned_user_id
        self.appealer_id = appealer_id

    @discord.ui.button(label="✅ Approve", style=discord.ButtonStyle.green, custom_id="approve_appeal")
    async def approve_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        main_guild = bot.get_guild(interaction.guild_id) # Assuming appeal server is separate, need main guild ID
        if not main_guild:
            # Try to find the main guild from bot's guilds if interaction.guild_id is not the main one
            # This requires knowing the main guild ID, which is not currently in config.py
            # For now, assume interaction.guild_id is the main guild or handle this more robustly later
            await interaction.followup.send("Error: Main guild not found. Cannot unban. (Ensure bot is in main guild and main guild ID is configured if appeal server is different)", ephemeral=True)
            return

        try:
            banned_user = await bot.fetch_user(self.banned_user_id)
            await main_guild.unban(banned_user, reason=f"Appeal approved by {interaction.user.display_name}")

            # Notify appealer
            appealer = await bot.fetch_user(self.appealer_id)
            try:
                await appealer.send(f"Good news! Your ban appeal for **{main_guild.name}** has been **approved**! You have been unbanned.")
            except discord.Forbidden:
                pass # Cannot DM appealer

            await interaction.message.edit(content="Appeal Approved!", view=None)
            await interaction.followup.send(f"Successfully unbanned {banned_user.display_name} and notified them.", ephemeral=True)
            # Log action
            log_ctx = commands.Context(message=interaction.message, bot=bot, prefix=config.BOT_PREFIX, command=bot.get_command('approve_appeal'))
            await log_action(log_ctx, f"Appeal for {banned_user.display_name} (ID: {self.banned_user_id}) approved by {interaction.user.display_name}.", discord.Color.green())

        except discord.NotFound:
            await interaction.followup.send(f"Error: Banned user with ID {self.banned_user_id} not found or already unbanned.", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("Error: I don\'t have permissions to unban members in the main guild.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"An unexpected error occurred during approval: {e}", ephemeral=True)

    @discord.ui.button(label="❌ Decline", style=discord.ButtonStyle.red, custom_id="decline_appeal")
    async def decline_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        try:
            appealer = await bot.fetch_user(self.appealer_id)
            try:
                await appealer.send(f"Your ban appeal has been **declined**. You remain banned from the server.")
            except discord.Forbidden:
                pass # Cannot DM appealer

            await interaction.message.edit(content="Appeal Declined.", view=None)
            await interaction.followup.send(f"Appeal declined and {appealer.display_name} notified.", ephemeral=True)
            # Log action
            log_ctx = commands.Context(message=interaction.message, bot=bot, prefix=config.BOT_PREFIX, command=bot.get_command('decline_appeal'))
            await log_action(log_ctx, f"Appeal for user ID {self.banned_user_id} declined by {interaction.user.display_name}.", discord.Color.red())

        except discord.NotFound:
            await interaction.followup.send(f"Error: Appeller with ID {self.appealer_id} not found.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"An unexpected error occurred during decline: {e}", ephemeral=True)

    @discord.ui.button(label="🔍 Review", style=discord.ButtonStyle.blurple, custom_id="review_appeal")
    async def review_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        try:
            # Create a private channel for staff review
            guild = interaction.guild
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True)
            }
            # Add all roles from ACCESS_LEVELS 1-5 to have read/send permissions
            for level in range(1, 6):
                role_ids = config.ACCESS_LEVELS.get(level, [])
                for role_id in role_ids:
                    role = guild.get_role(role_id)
                    if role:
                        overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

            channel_name = f"appeal-{self.banned_user_id}"
            category = discord.utils.get(guild.categories, name="Appeal Discussions") # Or create a specific category ID in config
            if not category:
                category = await guild.create_category("Appeal Discussions", overwrites=overwrites)

            review_channel = await guild.create_text_channel(channel_name, category=category, overwrites=overwrites)

            # Send appeal details to the new channel
            original_embed = interaction.message.embeds[0]
            await review_channel.send(f"Appeal discussion for <@{self.banned_user_id}>. Reviewers: {interaction.user.mention}", embed=original_embed)
            await interaction.followup.send(f"Review channel created: {review_channel.mention}", ephemeral=True)
            # Log action
            log_ctx = commands.Context(message=interaction.message, bot=bot, prefix=config.BOT_PREFIX, command=bot.get_command('review_appeal'))
            await log_action(log_ctx, f"Review channel for user ID {self.banned_user_id} created by {interaction.user.display_name}.", discord.Color.blurple())

        except discord.Forbidden:
            await interaction.followup.send("Error: I don\'t have permissions to create channels or set overwrites.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"An unexpected error occurred during review channel creation: {e}", ephemeral=True)

# --- Custom Panel Classes and Views ---
class PanelView(discord.ui.View):
    def __init__(self, bot_instance):
        super().__init__(timeout=300) # 5 minutes timeout
        self.bot_instance = bot_instance

    @discord.ui.button(label="❌ Close Panel", style=discord.ButtonStyle.secondary, custom_id="close_panel")
    async def close_panel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not has_access_level(interaction, 4):
            embed = EmbedTemplates.error("Access Denied", "You need **Access Level 4** to close the panel.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        await interaction.response.defer()
        try:
            await interaction.message.delete()
        except discord.Forbidden:
            await interaction.followup.send("I don't have permission to delete this message.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Couldn't close panel: {e}", ephemeral=True)

    @discord.ui.button(label="🔄 Refresh Stats", style=discord.ButtonStyle.primary, custom_id="refresh_stats")
    async def refresh_stats_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.update_panel_message(interaction.message)
        embed = EmbedTemplates.success("Panel Refreshed", "Statistics have been successfully updated!")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(label="🔒 Lock Channel", style=discord.ButtonStyle.secondary, custom_id="lock_channel")
    async def lock_channel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not has_access_level(interaction, 2):
            await interaction.response.send_message(embed=EmbedTemplates.error("Access Denied", "Requires **Access Level 2**."), ephemeral=True)
            return
        # Build options now to avoid empty select error
        text_channels = interaction.guild.text_channels if interaction.guild else []
        if not text_channels:
            await interaction.response.send_message("No text channels found in this server.", ephemeral=True)
            return
        options = [discord.SelectOption(label=f"#{ch.name}", value=str(ch.id)) for ch in text_channels[:25]]
        view = ChannelLockUnlockSelectView(action="lock", options=options)
        await interaction.response.send_message("Select a channel to lock:", view=view, ephemeral=True)

    @discord.ui.button(label="🔓 Unlock Channel", style=discord.ButtonStyle.secondary, custom_id="unlock_channel")
    async def unlock_channel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not has_access_level(interaction, 2):
            await interaction.response.send_message(embed=EmbedTemplates.error("Access Denied", "Requires **Access Level 2**."), ephemeral=True)
            return
        text_channels = interaction.guild.text_channels if interaction.guild else []
        if not text_channels:
            await interaction.response.send_message("No text channels found in this server.", ephemeral=True)
            return
        options = [discord.SelectOption(label=f"#{ch.name}", value=str(ch.id)) for ch in text_channels[:25]]
        view = ChannelLockUnlockSelectView(action="unlock", options=options)
        await interaction.response.send_message("Select a channel to unlock:", view=view, ephemeral=True)

    @discord.ui.button(label="🔄 Restart Bot", style=discord.ButtonStyle.red, custom_id="restart_bot")
    async def restart_bot_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Check for highest access level (Level 5)
        if not has_access_level(interaction, 5):
            embed = EmbedTemplates.error("Access Denied", "You need **Access Level 5** (Lead/Ownership Team) to restart the bot.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        embed = EmbedTemplates.warning("Bot Restart", "Restarting bot... This may take a moment.")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        # Log the restart action
        await log_action_interaction(interaction, f"Bot restart initiated by {interaction.user.display_name}.", discord.Color.red())

        # Gracefully close the bot and restart the process using current interpreter and args
        await self.bot_instance.close()
        os.execv(sys.executable, [sys.executable] + sys.argv)

    @discord.ui.button(label="💾 Backup Channels", style=discord.ButtonStyle.blurple, custom_id="backup_channels")
    async def backup_channels_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Check for a high access level, e.g., Level 4
        if not has_access_level(interaction, 4):
            embed = EmbedTemplates.error("Access Denied", "You need **Access Level 4** (Management/Development Team) to perform a backup.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        backup_dir = "backups"
        os.makedirs(backup_dir, exist_ok=True)
        guild = interaction.guild
        backup_files = []

        for channel_var, channel_id in config.CHANNEL_VARS.items():
            if channel_id:
                channel = guild.get_channel(channel_id)
                if isinstance(channel, discord.TextChannel):
                    filename = f"{backup_dir}/{guild.name}_{channel.name}_{discord.utils.utcnow().strftime('%Y%m%d_%H%M%S')}.txt"
                    try:
                        with open(filename, "w", encoding="utf-8") as f:
                            async for message in channel.history(limit=None, oldest_first=True):
                                f.write(f"[{message.created_at.strftime('%Y-%m-%d %H:%M:%S')}] {message.author.display_name}: {message.clean_content}\n")
                        backup_files.append(discord.File(filename))
                    except discord.Forbidden:
                        await interaction.followup.send(f"Warning: I don\'t have permissions to read messages in {channel.mention}. Skipping backup for this channel.", ephemeral=True)
                    except Exception as e:
                        await interaction.followup.send(f"Error backing up {channel.mention}: {e}", ephemeral=True)

        if backup_files:
            await interaction.followup.send("Channel backups completed!", files=backup_files, ephemeral=True)
            await log_action_interaction(interaction, f"Channel backup initiated by {interaction.user.display_name}. {len(backup_files)} channels backed up.", discord.Color.blurple())
        else:
            await interaction.followup.send("No channels were backed up or an error occurred.", ephemeral=True)

    async def update_panel_message(self, message: discord.Message):
        guild = message.guild
        if not guild: return

        # Players Active (online/idle/dnd members)
        active_players = sum(1 for member in guild.members if member.status != discord.Status.offline)

        # Staff Active (members with configured staff roles who are online/idle/dnd)
        staff_roles_ids = set()
        for level_roles in config.ACCESS_LEVELS.values():
            staff_roles_ids.update(level_roles)

        active_staff = 0
        for member in guild.members:
            if member.status != discord.Status.offline:
                for role in member.roles:
                    if role.id in staff_roles_ids:
                        active_staff += 1
                        break # Count once per member

        # Server Status
        server_status_description = (
            f"Total Members: {guild.member_count}\n"
            f"Total Channels: {len(guild.channels)}\n"
            f"Total Roles: {len(guild.roles)}\n"
            f"Boost Level: {guild.premium_tier} (Boosts: {guild.premium_subscription_count})\n"
            f"Verification Level: {guild.verification_level.name.replace('_', ' ').title()}"
        )

        # Activity stats from recent events
        joins_24h, joins_7d = get_event_counts(JOIN_EVENTS, days_24h=1, days_7d=7)
        msgs_24h, msgs_7d = get_event_counts(MESSAGE_EVENTS, days_24h=1, days_7d=7)

        embed = EmbedTemplates.primary(
            title="📊 ACR - System Management Panel",
            description="Welcome to the ACR System Management Panel. Here you can view server statistics and perform administrative actions."
        )
        embed.add_field(name="👥 Online Players", value=f"`{active_players}`", inline=True)
        embed.add_field(name="👨‍💼 Active Staff", value=f"`{active_staff}`", inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=True) # Empty field for spacing
        embed.add_field(name="📈 Server Statistics", value=server_status_description, inline=False)
        embed.add_field(name="📊 Activity (24h / 7d)", value=f"Joins: `{joins_24h}` / `{joins_7d}`\nMessages: `{msgs_24h}` / `{msgs_7d}`", inline=False)

        # Modern visuals (optional banner/led gif)
        if getattr(config, 'PANEL_BANNER_URL', ''):
            embed.set_image(url=config.PANEL_BANNER_URL)
        if getattr(config, 'PANEL_LED_GIF_URL', ''):
            embed.set_thumbnail(url=config.PANEL_LED_GIF_URL)
        embed.set_footer(
            text=f"Last updated: {discord.utils.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}",
            icon_url=guild.icon.url if guild.icon else None
        )

        await message.edit(embed=embed, view=self)

class ChannelLockUnlockSelect(discord.ui.Select):
    def __init__(self, action: str, options: list[discord.SelectOption]):
        self.action = action  # "lock" or "unlock"
        super().__init__(placeholder="Choose a text channel...", min_values=1, max_values=1, options=options, custom_id=f"select_{action}")

    async def callback(self, interaction: discord.Interaction):
        # Defer immediately to keep interaction alive (ephemeral)
        try:
            await interaction.response.defer(ephemeral=True)
        except Exception:
            pass
        # Ensure an option exists; if not, repopulate
        channel_id = int(self.values[0]) if self.values else None
        if not channel_id:
            await interaction.followup.send("No channel selected.", ephemeral=True)
            return
        channel = interaction.guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            await interaction.followup.send("Please select a text channel.", ephemeral=True)
            return

        # Trigger Sapphire bot by sending its command into the selected channel
        try:
            cmd = "s!lock" if self.action == "lock" else "s!unlock"
            # Mention Sapphire if configured (some bots only react to human/mentions)
            if getattr(config, 'SAPPHIRE_BOT_ID', 0):
                try:
                    await channel.send(f"<@{int(config.SAPPHIRE_BOT_ID)}> {cmd}")
                except Exception:
                    await channel.send(cmd)
            else:
                await channel.send(cmd)
            # Apply native permission change as a reliable fallback
            try:
                everyone = interaction.guild.default_role
                if self.action == "lock":
                    # Disallow @everyone sending; allow staff roles to keep speaking
                    await channel.set_permissions(everyone, send_messages=False)
                    for level_roles in config.ACCESS_LEVELS.values():
                        for rid in level_roles:
                            role = interaction.guild.get_role(rid)
                            if role:
                                await channel.set_permissions(role, send_messages=True)
                else:
                    # Restore @everyone to default (unset)
                    await channel.set_permissions(everyone, send_messages=None)
                # Post a lightweight confirmation in the target channel
                if self.action == "lock":
                    await channel.send(embed=EmbedTemplates.warning("Channel Locked", "Channel has been locked via panel."))
                else:
                    await channel.send(embed=EmbedTemplates.success("Channel Unlocked", "Channel has been unlocked via panel."))
                confirmation = EmbedTemplates.success("Channel Updated", f"Applied `{cmd}` effect to {channel.mention}.")
            except discord.Forbidden:
                confirmation = EmbedTemplates.warning(
                    "Partial Success",
                    f"Sent `{cmd}` to {channel.mention}, but I lack permissions to change channel overrides."
                )
            await interaction.followup.send(embed=confirmation, ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send(
                embed=EmbedTemplates.error(
                    "Permission Denied",
                    "I can't send messages in the selected channel."
                ),
                ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(
                embed=EmbedTemplates.error("Unexpected Error", str(e)),
                ephemeral=True
            )

class ChannelLockUnlockSelectView(discord.ui.View):
    def __init__(self, action: str, options: list[discord.SelectOption]):
        super().__init__(timeout=120)
        self.action = action
        self.select = ChannelLockUnlockSelect(action, options)
        self.add_item(self.select)

# --- Bot Events and Commands ---
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name} ({bot.user.id})')
    print('------')
    # Set professional presence
    await bot.change_presence(
        activity=discord.Activity(type=discord.ActivityType.watching, name="Server Operations"),
        status=discord.Status.online
    )
    # Optionally, load persistent views here if needed for AppealReviewView

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        embed = EmbedTemplates.error(
            "Missing Required Argument",
            f"You're missing the required argument: `{error.param.name}`\n\n"
            f"**Usage:** `{ctx.prefix}{ctx.command.name} {ctx.command.signature}`\n"
            f"**Example:** Use `{ctx.prefix}help {ctx.command.name}` for detailed usage information."
        )
        await ctx.send(embed=embed)
        return
    if isinstance(error, commands.BadArgument):
        embed = EmbedTemplates.error(
            "Invalid Argument Format",
            "One or more arguments have an incorrect format.\n\n"
            f"**Usage:** `{ctx.prefix}{ctx.command.name} {ctx.command.signature}`\n"
            f"**Example:** Use `{ctx.prefix}help {ctx.command.name}` for detailed usage information."
        )
        await ctx.send(embed=embed)
        return
    if isinstance(error, commands.MissingPermissions):
        embed = EmbedTemplates.error(
            "Missing Permissions",
            "You don't have the required Discord permissions to run this command."
        )
        await ctx.send(embed=embed)
        return
    if isinstance(error, commands.CheckFailure):
        # This will be handled by the access_level_required decorator
        return
    if isinstance(error, commands.CommandNotFound):
        return
    try:
        embed = EmbedTemplates.error(
            "Unexpected Error",
            "An unexpected error occurred while running this command. Please try again later."
        )
        await ctx.send(embed=embed)
    except Exception:
        pass
    print(f"Unhandled command error: {error}")

# --- Lightweight Stats Tracking ---
# In-memory rolling event stores for joins and message activity
JOIN_EVENTS = deque(maxlen=20000)
MESSAGE_EVENTS = deque(maxlen=50000)

def _prune_old_events(store: deque, max_age_days: int = 14):
    if not store:
        return
    threshold = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    while store and store[0] < threshold:
        store.popleft()

def get_event_counts(store: deque, days_24h: int = 1, days_7d: int = 7):
    """Return counts within last 24h and last 7d for a given store of datetimes (UTC)."""
    now = datetime.now(timezone.utc)
    t24 = now - timedelta(days=days_24h)
    t7 = now - timedelta(days=days_7d)
    _prune_old_events(store, max_age_days=max(days_7d, days_24h, 14))
    c24 = 0
    c7 = 0
    for ts in store:
        if ts >= t7:
            c7 += 1
            if ts >= t24:
                c24 += 1
    return c24, c7

@bot.event
async def on_member_join(member: discord.Member):
    JOIN_EVENTS.append(datetime.now(timezone.utc))

@bot.event
async def on_message(message: discord.Message):
    if message.guild and not message.author.bot:
        MESSAGE_EVENTS.append(datetime.now(timezone.utc))
    await bot.process_commands(message)

@bot.command()
@access_level_required(1)
async def ping(ctx):
    """Check the bot's latency and response time."""
    embed = EmbedTemplates.success(
        "🏓 Pong!",
        f"**Latency:** `{round(bot.latency * 1000)}ms`\n"
        f"**Status:** Online and Ready"
    )
    embed.set_footer(text=f"Requested by {ctx.author.display_name}")
    await ctx.send(embed=embed)
    await log_action(ctx, f"User {ctx.author.display_name} used the `ping` command.", ProfessionalColors.SUCCESS)

@bot.command()
@access_level_required(2)
async def test_access(ctx):
    """Test your current access level."""
    embed = EmbedTemplates.success(
        f"Hello {ctx.author.display_name}!",
        "You have at least **Access Level 2** permissions.\n\n"
        "✅ **Access Level 2:** Admin Team\n"
        "🔧 You can use admin commands and announcements."
    )
    await ctx.send(embed=embed)
    await log_action(ctx, f"User {ctx.author.display_name} used the `test_access` command.", ProfessionalColors.SUCCESS)

@bot.command(name='commands')
@access_level_required(1)
async def commands_list(ctx, *, command_name: str = None):
    """Display available commands with interactive help system."""
    
    if command_name:
        # Show help for specific command
        command = bot.get_command(command_name)
        if not command:
            embed = EmbedTemplates.error("Command Not Found", f"No command named `{command_name}` was found.")
            await ctx.send(embed=embed)
            return
        
        embed = EmbedTemplates.info(
            f"📖 {command.name}",
            command.help or "No description available."
        )
        
        # Add usage information
        usage = f"`{ctx.prefix}{command.name}"
        if command.signature:
            usage += f" {command.signature}"
        usage += "`"
        
        embed.add_field(name="Usage", value=usage, inline=False)
        
        # Add simple examples for key commands
        examples = {
            'promote': f"`{ctx.prefix}promote @user Moderator`",
            'demote': f"`{ctx.prefix}demote @user Moderator`",
            'ban': f"`{ctx.prefix}ban @user Breaking rules`",
            'kick': f"`{ctx.prefix}kick @user Spamming`",
            'warn': f"`{ctx.prefix}warn @user Bad language`",
            'announcement': f"`{ctx.prefix}announcement ann-main Message`",
            'appeal': f"`{ctx.prefix}appeal 123456789`",
            'panel': f"`{ctx.prefix}panel`"
        }
        
        if command.name in examples:
            embed.add_field(name="Example", value=examples[command.name], inline=False)
        
        await ctx.send(embed=embed)
        return
    
    # Show interactive help system
    help_view = HelpMainView()
    main_embed = help_view.create_main_embed()
    await ctx.send(embed=main_embed, view=help_view)

@bot.command(name='announcement')
@access_level_required(2)
async def announcement(ctx, channel_var: str, *, message: str):
    """Send an announcement to a specified channel.
    
    Usage: :announcement <channel_var> <message>
    Example: :announcement ann-main Server maintenance scheduled
    
    Available channel variables:
    • ann-main, ann-sub, ann-staff, ann-tester, ann-trello
    • updates, sneak-peaks
    """
    if channel_var not in config.CHANNEL_VARS:
        embed = EmbedTemplates.error(
            "Invalid Channel Variable",
            f"The channel variable `{channel_var}` was not found.\n\n"
            "**Available channel variables:**\n"
            "• `ann-main` - Main Announcement channel\n"
            "• `ann-sub` - Secondary Announcement channel\n"
            "• `ann-staff` - Staff Announcement channel\n"
            "• `ann-tester` - Testers Announcement channel\n"
            "• `ann-trello` - Trello Announcement channel\n"
            "• `updates` - Updates Channel\n"
            "• `sneak-peaks` - Sneak Peaks channel"
        )
        await ctx.send(embed=embed)
        await log_action(ctx, f"Failed announcement: Channel variable '{channel_var}' not found.", ProfessionalColors.ERROR)
        return

    channel_id = config.CHANNEL_VARS[channel_var]
    target_channel = bot.get_channel(channel_id)

    if not target_channel:
        embed = EmbedTemplates.error(
            "Channel Not Found",
            f"Could not find channel with ID `{channel_id}` for variable `{channel_var}`"
        )
        await ctx.send(embed=embed)
        await log_action(ctx, f"Failed announcement: Target channel with ID {channel_id} not found.", ProfessionalColors.ERROR)
        return

    embed = EmbedTemplates.info(
        title="📢 Announcement!",
        description=message
    )
    embed.set_footer(
        text=f"Announced by {ctx.author.display_name}", 
        icon_url=ctx.author.avatar.url if ctx.author.avatar else None
    )
    embed.set_thumbnail(url=config.BOT_PFP_URL if config.BOT_PFP_URL else None)

    try:
        await target_channel.send(embed=embed)
        success_embed = EmbedTemplates.success(
            "Announcement Sent",
            f"Successfully sent announcement to {target_channel.mention}!"
        )
        await ctx.send(embed=success_embed)
        await log_action(ctx, f"Announcement sent to {target_channel.mention} by {ctx.author.display_name}.", ProfessionalColors.INFO)
    except discord.Forbidden:
        embed = EmbedTemplates.error(
            "Permission Denied",
            f"I don't have permissions to send messages in {target_channel.mention}."
        )
        await ctx.send(embed=embed)
        await log_action(ctx, f"Failed announcement: Bot lacks permissions in {target_channel.mention}.", ProfessionalColors.ERROR)
    except Exception as e:
        embed = EmbedTemplates.error(
            "Unexpected Error",
            f"An unexpected error occurred: {e}"
        )
        await ctx.send(embed=embed)
        await log_action(ctx, f"Failed announcement due to unexpected error: {e}", ProfessionalColors.ERROR)

@bot.command(name='promote')
@access_level_required(3)
async def promote(ctx, member: discord.Member, *, rank_name: str):
    """Promote a staff member to a new rank/position.
    
    Usage: :promote <@user> <rank_name>
    Example: :promote @John Moderator
    
    Adds all 3 roles (permission, display, team), sends announcement, DMs user, and logs action.
    """
    # Check if the rank exists in our configuration
    if rank_name not in config.RANKS:
        available_ranks = ", ".join([f"`{rank}`" for rank in config.RANKS.keys()])
        embed = EmbedTemplates.error(
            "Rank Not Found",
            f"The rank `{rank_name}` was not found.\n\n"
            "**Available ranks:**\n"
            f"{available_ranks}\n\n"
            "**Please provide an exact rank name.**\n"
            "• Rank names are case-sensitive\n"
            "• Example: `Moderator`, `Senior Administrator`, `Head Moderator`"
        )
        await ctx.send(embed=embed)
        await log_action(ctx, f"Failed promotion: Rank '{rank_name}' not found.", ProfessionalColors.ERROR)
        return

    # Get the role IDs for this rank
    rank_config = config.RANKS[rank_name]
    perm_role_id = rank_config["perm_role"]
    display_role_id = rank_config["display_role"]
    team_role_id = rank_config["team_role"]

    # Get the actual role objects
    perm_role = ctx.guild.get_role(perm_role_id)
    display_role = ctx.guild.get_role(display_role_id)
    team_role = ctx.guild.get_role(team_role_id)

    # Check if all roles exist
    missing_roles = []
    if not perm_role:
        missing_roles.append(f"Permission Role (ID: {perm_role_id})")
    if not display_role:
        missing_roles.append(f"Display Role (ID: {display_role_id})")
    if not team_role:
        missing_roles.append(f"Team Role (ID: {team_role_id})")

    if missing_roles:
        embed = EmbedTemplates.error(
            "Roles Not Found",
            f"The following roles for rank `{rank_name}` were not found:\n"
            f"• {chr(10).join(missing_roles)}\n\n"
            "Please contact an administrator to fix the role configuration."
        )
        await ctx.send(embed=embed)
        await log_action(ctx, f"Failed promotion: Missing roles for rank '{rank_name}'.", ProfessionalColors.ERROR)
        return

    # Promotion permission rules based on invoker's Team Role
    invoker_team_role_ids = [role.id for role in ctx.author.roles if role.id in config.TEAM_ROLE_IDS.values()]

    # Block Developers from using promote
    if config.TEAM_ROLE_IDS["development"] in invoker_team_role_ids:
        embed = EmbedTemplates.warning(
            "Not Allowed",
            "Developers are not allowed to use promote/demote commands."
        )
        await ctx.send(embed=embed)
        await log_action(ctx, f"Promotion blocked: Developer {ctx.author.display_name} tried to promote {member.display_name} to {rank_name}.", ProfessionalColors.WARNING)
        return

    # Ownership can promote anyone, including Lead
    is_ownership = config.TEAM_ROLE_IDS["ownership"] in invoker_team_role_ids

    # Determine target team role category of the rank being assigned
    target_team_role_id = team_role_id

    # Lead cannot promote Lead
    if not is_ownership and target_team_role_id == config.TEAM_ROLE_IDS["lead"] and config.TEAM_ROLE_IDS["lead"] in invoker_team_role_ids:
        embed = EmbedTemplates.warning(
            "Not Allowed",
            "Lead team members cannot promote another Lead."
        )
        await ctx.send(embed=embed)
        await log_action(ctx, f"Promotion blocked: Lead {ctx.author.display_name} tried to promote {member.display_name} to a Lead role.", ProfessionalColors.WARNING)
        return

    # If not ownership, enforce PROMOTION_RULES mapping
    if not is_ownership:
        # Find the highest-privileged applicable invoker team role for rule check
        # Priority order: lead > management > head > admin > moderation
        priority = [
            config.TEAM_ROLE_IDS["lead"],
            config.TEAM_ROLE_IDS["management"],
            config.TEAM_ROLE_IDS["head"],
            config.TEAM_ROLE_IDS["admin"],
            config.TEAM_ROLE_IDS["moderation"]
        ]
        invoker_applicable_role = next((rid for rid in priority if rid in invoker_team_role_ids), None)

        allowed_targets = set()
        if invoker_applicable_role and invoker_applicable_role in getattr(config, 'PROMOTION_RULES', {}):
            allowed_targets = config.PROMOTION_RULES[invoker_applicable_role]

        # Lead has a special rule: can promote any except Lead itself
        if invoker_applicable_role == config.TEAM_ROLE_IDS["lead"]:
            if target_team_role_id == config.TEAM_ROLE_IDS["lead"]:
                allowed = False
            else:
                allowed = True
        else:
            allowed = target_team_role_id in allowed_targets

        if not allowed:
            # Build a friendly message explaining limit
            role_name_map = {
                config.TEAM_ROLE_IDS["moderation"]: "Moderation positions",
                config.TEAM_ROLE_IDS["admin"]: "Admin positions",
                config.TEAM_ROLE_IDS["head"]: "Head positions",
                config.TEAM_ROLE_IDS["management"]: "Management positions",
                config.TEAM_ROLE_IDS["development"]: "Developer positions",
                config.TEAM_ROLE_IDS["lead"]: "Lead positions"
            }
            target_label = role_name_map.get(target_team_role_id, "this position")
            embed = EmbedTemplates.warning(
                "Promotion Not Allowed",
                f"You are not allowed to promote to {target_label}."
            )
            await ctx.send(embed=embed)
            await log_action(ctx, f"Promotion blocked: {ctx.author.display_name} tried to promote {member.display_name} to {rank_name} (not permitted).", ProfessionalColors.WARNING)
            return

    # Check bot permissions
    if not ctx.guild.me.guild_permissions.manage_roles:
        embed = EmbedTemplates.error(
            "Missing Permissions",
            "I don't have the **Manage Roles** permission required to promote users."
        )
        await ctx.send(embed=embed)
        await log_action(ctx, f"Failed promotion: Bot lacks 'Manage Roles' permission.", ProfessionalColors.ERROR)
        return
    
    # Check if any role is too high for the bot
    bot_top_role = ctx.guild.me.top_role
    high_roles = []
    if perm_role >= bot_top_role:
        high_roles.append(f"Permission Role ({perm_role.name})")
    if display_role >= bot_top_role:
        high_roles.append(f"Display Role ({display_role.name})")
    if team_role >= bot_top_role:
        high_roles.append(f"Team Role ({team_role.name})")

    if high_roles:
        embed = EmbedTemplates.error(
            "Role Too High",
            f"I cannot assign the following roles for rank `{rank_name}` as they are equal to or higher than my highest role:\n"
            f"• {chr(10).join(high_roles)}"
        )
        await ctx.send(embed=embed)
        await log_action(ctx, f"Failed promotion: Cannot assign roles for rank '{rank_name}' (too high).", ProfessionalColors.ERROR)
        return

    try:
        # Add all three roles
        roles_to_add = [perm_role, display_role, team_role]
        await member.add_roles(*roles_to_add)

        # Send promotion announcement
        promotion_channel_id = config.CHANNEL_VARS.get("promotion-channel")
        if promotion_channel_id:
            promo_channel = bot.get_channel(promotion_channel_id)
            if promo_channel:
                embed = EmbedTemplates.primary(
                    title="🎉 Staff Promotion! 🎉",
                    description=f"Congratulations to {member.mention} on their promotion to **{rank_name}**!\n\nLet's all wish them the best in their new role!"
                )
                embed.set_thumbnail(url=member.avatar.url if member.avatar else None)
                embed.set_footer(
                    text=f"Promoted by {ctx.author.display_name}", 
                    icon_url=ctx.author.avatar.url if ctx.author.avatar else None
                )
                await promo_channel.send(embed=embed)
            else:
                embed = EmbedTemplates.warning(
                    "Promotion Channel Not Found",
                    f"Promotion channel with ID {promotion_channel_id} not found."
                )
                await ctx.send(embed=embed)
                await log_action(ctx, f"Promotion warning: Promotion channel with ID {promotion_channel_id} not found.", ProfessionalColors.WARNING)
        else:
            embed = EmbedTemplates.warning(
                "Configuration Missing",
                "Promotion channel not configured in config.py."
            )
            await ctx.send(embed=embed)
            await log_action(ctx, "Promotion warning: 'promotion-channel' not configured.", ProfessionalColors.WARNING)

        # Send DM to the promoted user
        try:
            dm_embed = EmbedTemplates.success(
                title="🎉 Congratulations on Your Promotion!",
                description=f"Dear {member.display_name},\n\nWe are thrilled to inform you that you have been promoted to **{rank_name}** in {ctx.guild.name}!\n\nWe appreciate your hard work and dedication. We look forward to your continued contributions.\n\nBest regards,\nThe Management Team"
            )
            await member.send(embed=dm_embed)
        except discord.Forbidden:
            embed = EmbedTemplates.warning(
                "Could Not Send DM",
                f"Could not DM {member.display_name}. They might have DMs disabled."
            )
            await ctx.send(embed=embed)
            await log_action(ctx, f"Promotion warning: Could not DM {member.display_name}.", ProfessionalColors.WARNING)

        # Send success message
        success_embed = EmbedTemplates.success(
            "Promotion Successful",
            f"Successfully promoted {member.display_name} to **{rank_name}**!\n\n"
            f"**Roles assigned:**\n"
            f"• {perm_role.name} (Permission)\n"
            f"• {display_role.name} (Display)\n"
            f"• {team_role.name} (Team)"
        )
        await ctx.send(embed=success_embed)
        await log_action(ctx, f"User {ctx.author.display_name} promoted {member.display_name} to {rank_name}.", ProfessionalColors.PRIMARY)

    except discord.Forbidden:
        embed = EmbedTemplates.error(
            "Permission Denied",
            f"I don't have permissions to assign the roles for rank '{rank_name}' to {member.display_name}."
        )
        await ctx.send(embed=embed)
        await log_action(ctx, f"Failed promotion: Bot lacks permissions to assign roles for rank '{rank_name}'", ProfessionalColors.ERROR)
    except Exception as e:
        embed = EmbedTemplates.error(
            "Unexpected Error",
            f"An unexpected error occurred: {e}"
        )
        await ctx.send(embed=embed)
        await log_action(ctx, f"Failed promotion due to unexpected error: {e}", ProfessionalColors.ERROR)

@bot.command(name='demote')
@access_level_required(3)
async def demote(ctx, member: discord.Member, *, rank_name: str):
    """Demote a staff member by removing all roles for a specified rank/position.
    
    Usage: :demote <@user> <rank_name>
    Example: :demote @John Moderator
    
    Removes all 3 roles (permission, display, team), sends announcement, DMs user, and logs action.
    """
    # Check if the rank exists in our configuration
    if rank_name not in config.RANKS:
        available_ranks = ", ".join([f"`{rank}`" for rank in config.RANKS.keys()])
        embed = EmbedTemplates.error(
            "Rank Not Found",
            f"The rank `{rank_name}` was not found.\n\n"
            "**Available ranks:**\n"
            f"{available_ranks}\n\n"
            "**Please provide an exact rank name.**\n"
            "• Rank names are case-sensitive\n"
            "• Example: `Moderator`, `Senior Administrator`, `Head Moderator`"
        )
        await ctx.send(embed=embed)
        await log_action(ctx, f"Failed demotion: Rank '{rank_name}' not found.", ProfessionalColors.ERROR)
        return

    # Get the role IDs for this rank
    rank_config = config.RANKS[rank_name]
    perm_role_id = rank_config["perm_role"]
    display_role_id = rank_config["display_role"]
    team_role_id = rank_config["team_role"]
    # Demotion permission rules based on invoker's Team Role
    invoker_team_role_ids = [role.id for role in ctx.author.roles if role.id in config.TEAM_ROLE_IDS.values()]

    # Block Developers from using demote
    if config.TEAM_ROLE_IDS["development"] in invoker_team_role_ids:
        embed = EmbedTemplates.warning(
            "Not Allowed",
            "Developers are not allowed to use promote/demote commands."
        )
        await ctx.send(embed=embed)
        await log_action(ctx, f"Demotion blocked: Developer {ctx.author.display_name} tried to demote {member.display_name} from {rank_name}.", ProfessionalColors.WARNING)
        return

    # Ownership can demote anyone, including Lead
    is_ownership = config.TEAM_ROLE_IDS["ownership"] in invoker_team_role_ids
    target_team_role_id = team_role_id

    # Lead cannot demote Lead (symmetry with promotion restriction)
    if not is_ownership and target_team_role_id == config.TEAM_ROLE_IDS["lead"] and config.TEAM_ROLE_IDS["lead"] in invoker_team_role_ids:
        embed = EmbedTemplates.warning(
            "Not Allowed",
            "Lead team members cannot demote another Lead."
        )
        await ctx.send(embed=embed)
        await log_action(ctx, f"Demotion blocked: Lead {ctx.author.display_name} tried to demote a Lead role from {member.display_name}.", ProfessionalColors.WARNING)
        return

    if not is_ownership:
        priority = [
            config.TEAM_ROLE_IDS["lead"],
            config.TEAM_ROLE_IDS["management"],
            config.TEAM_ROLE_IDS["head"],
            config.TEAM_ROLE_IDS["admin"],
            config.TEAM_ROLE_IDS["moderation"]
        ]
        invoker_applicable_role = next((rid for rid in priority if rid in invoker_team_role_ids), None)

        allowed_targets = set()
        if invoker_applicable_role and invoker_applicable_role in getattr(config, 'PROMOTION_RULES', {}):
            allowed_targets = config.PROMOTION_RULES[invoker_applicable_role]

        if invoker_applicable_role == config.TEAM_ROLE_IDS["lead"]:
            if target_team_role_id == config.TEAM_ROLE_IDS["lead"]:
                allowed = False
            else:
                allowed = True
        else:
            allowed = target_team_role_id in allowed_targets

        if not allowed:
            role_name_map = {
                config.TEAM_ROLE_IDS["moderation"]: "Moderation positions",
                config.TEAM_ROLE_IDS["admin"]: "Admin positions",
                config.TEAM_ROLE_IDS["head"]: "Head positions",
                config.TEAM_ROLE_IDS["management"]: "Management positions",
                config.TEAM_ROLE_IDS["development"]: "Developer positions",
                config.TEAM_ROLE_IDS["lead"]: "Lead positions"
            }
            target_label = role_name_map.get(target_team_role_id, "this position")
            embed = EmbedTemplates.warning(
                "Demotion Not Allowed",
                f"You are not allowed to demote from {target_label}."
            )
            await ctx.send(embed=embed)
            await log_action(ctx, f"Demotion blocked: {ctx.author.display_name} tried to demote {member.display_name} from {rank_name} (not permitted).", ProfessionalColors.WARNING)
            return


    # Get the actual role objects
    perm_role = ctx.guild.get_role(perm_role_id)
    display_role = ctx.guild.get_role(display_role_id)
    team_role = ctx.guild.get_role(team_role_id)

    # Check if all roles exist
    missing_roles = []
    if not perm_role:
        missing_roles.append(f"Permission Role (ID: {perm_role_id})")
    if not display_role:
        missing_roles.append(f"Display Role (ID: {display_role_id})")
    if not team_role:
        missing_roles.append(f"Team Role (ID: {team_role_id})")

    if missing_roles:
        embed = EmbedTemplates.error(
            "Roles Not Found",
            f"The following roles for rank `{rank_name}` were not found:\n"
            f"• {chr(10).join(missing_roles)}\n\n"
            "Please contact an administrator to fix the role configuration."
        )
        await ctx.send(embed=embed)
        await log_action(ctx, f"Failed demotion: Missing roles for rank '{rank_name}'.", ProfessionalColors.ERROR)
        return

    # Check which roles the member actually has
    roles_to_remove = []
    roles_member_has = []
    
    if perm_role in member.roles:
        roles_to_remove.append(perm_role)
        roles_member_has.append(f"{perm_role.name} (Permission)")
    if display_role in member.roles:
        roles_to_remove.append(display_role)
        roles_member_has.append(f"{display_role.name} (Display)")
    if team_role in member.roles:
        roles_to_remove.append(team_role)
        roles_member_has.append(f"{team_role.name} (Team)")

    if not roles_to_remove:
        embed = EmbedTemplates.error(
            "User Doesn't Have Rank",
            f"{member.display_name} does not have any roles for the rank `{rank_name}`."
        )
        await ctx.send(embed=embed)
        await log_action(ctx, f"Failed demotion: {member.display_name} does not have rank '{rank_name}'", ProfessionalColors.ERROR)
        return

    # Check bot permissions
    if not ctx.guild.me.guild_permissions.manage_roles:
        embed = EmbedTemplates.error(
            "Missing Permissions",
            "I don't have the **Manage Roles** permission required to demote users."
        )
        await ctx.send(embed=embed)
        await log_action(ctx, f"Failed demotion: Bot lacks 'Manage Roles' permission.", ProfessionalColors.ERROR)
        return
    
    # Check if any role is too high for the bot
    bot_top_role = ctx.guild.me.top_role
    high_roles = []
    for role in roles_to_remove:
        if role >= bot_top_role:
            high_roles.append(f"{role.name}")

    if high_roles:
        embed = EmbedTemplates.error(
            "Role Too High",
            f"I cannot remove the following roles for rank `{rank_name}` as they are equal to or higher than my highest role:\n"
            f"• {chr(10).join(high_roles)}"
        )
        await ctx.send(embed=embed)
        await log_action(ctx, f"Failed demotion: Cannot remove roles for rank '{rank_name}' (too high).", ProfessionalColors.ERROR)
        return

    try:
        # Remove all roles the member has for this rank
        await member.remove_roles(*roles_to_remove)

        # Send demotion announcement
        promotion_channel_id = config.CHANNEL_VARS.get("promotion-channel")
        if promotion_channel_id:
            promo_channel = bot.get_channel(promotion_channel_id)
            if promo_channel:
                embed = discord.Embed(
                    title="⬇️ Staff Demotion ⬇️",
                    description=f"It has been decided that {member.mention} will no longer hold the position of **{rank_name}**.",
                    color=discord.Color.red()
                )
                embed.set_thumbnail(url=member.avatar.url if member.avatar else None)
                embed.set_footer(text=f"Demoted by {ctx.author.display_name}", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
                await promo_channel.send(embed=embed)
            else:
                await ctx.send(f"Warning: Promotion channel with ID {promotion_channel_id} not found.")
                await log_action(ctx, f"Demotion warning: Promotion channel with ID {promotion_channel_id} not found.", discord.Color.orange())
        else:
            await ctx.send("Warning: 'promotion-channel' not configured in config.py.")
            await log_action(ctx, "Demotion warning: 'promotion-channel' not configured.", discord.Color.orange())

        # Send DM to the demoted user
        try:
            dm_embed = discord.Embed(
                title="Regarding Your Position Change",
                description=f"Dear {member.display_name},\n\nThis message is to inform you that your position as **{rank_name}** in {ctx.guild.name} has been removed.\n\nWe appreciate your past contributions.\n\nBest regards,\nThe Management Team",
                color=discord.Color.orange()
            )
            await member.send(embed=dm_embed)
        except discord.Forbidden:
            await ctx.send(f"Warning: Could not DM {member.display_name}. They might have DMs disabled.")
            await log_action(ctx, f"Demotion warning: Could not DM {member.display_name}.", discord.Color.orange())

        # Send success message
        success_embed = EmbedTemplates.success(
            "Demotion Successful",
            f"Successfully demoted {member.display_name} from **{rank_name}**!\n\n"
            f"**Roles removed:**\n"
            f"• {chr(10).join(roles_member_has)}"
        )
        await ctx.send(embed=success_embed)
        await log_action(ctx, f"User {ctx.author.display_name} demoted {member.display_name} from {rank_name}.", discord.Color.red())

    except discord.Forbidden:
        embed = EmbedTemplates.error(
            "Permission Denied",
            f"I don't have permissions to remove the roles for rank '{rank_name}' from {member.display_name}."
        )
        await ctx.send(embed=embed)
        await log_action(ctx, f"Failed demotion: Bot lacks permissions to remove roles for rank '{rank_name}'", discord.Color.red())
    except Exception as e:
        embed = EmbedTemplates.error(
            "Unexpected Error",
            f"An unexpected error occurred: {e}"
        )
        await ctx.send(embed=embed)
        await log_action(ctx, f"Failed demotion due to unexpected error: {e}", discord.Color.red())


@bot.command(name='kick')
@access_level_required(1)
async def kick(ctx, member: discord.Member, *, reason: str = "No reason provided."):
    """Kick a member from the server.
    
    Usage: :kick <@user> [reason]
    Example: :kick @John Spamming in general chat
    
    Removes member, DMs user, and logs action.
    """
    if not ctx.guild.me.guild_permissions.kick_members:
        embed = EmbedTemplates.error(
            "Missing Permissions",
            "I don't have the **Kick Members** permission required to kick users."
        )
        await ctx.send(embed=embed)
        await log_action(ctx, f"Failed kick: Bot lacks 'Kick Members' permission.", ProfessionalColors.ERROR)
        return
    
    if member.top_role >= ctx.author.top_role and ctx.author.id != ctx.guild.owner_id:
        embed = EmbedTemplates.error(
            "Cannot Kick User",
            "You cannot kick someone with an equal or higher role than yourself."
        )
        await ctx.send(embed=embed)
        await log_action(ctx, f"Failed kick: {ctx.author.display_name} tried to kick {member.display_name} with equal/higher role.", ProfessionalColors.ERROR)
        return
    
    if member.top_role >= ctx.guild.me.top_role:
        embed = EmbedTemplates.error(
            "Cannot Kick User",
            "I cannot kick someone with an equal or higher role than myself."
        )
        await ctx.send(embed=embed)
        await log_action(ctx, f"Failed kick: Bot tried to kick {member.display_name} with equal/higher role.", ProfessionalColors.ERROR)
        return

    try:
        dm_embed = EmbedTemplates.warning(
            title="⚠️ You have been Kicked!",
            description=f"You have been kicked from **{ctx.guild.name}**.\n\n**Reason:** {reason}\n\nIf you believe this was a mistake, please contact a staff member."
        )
        dm_embed.set_footer(text=f"Kicked by {ctx.author.display_name}")
        await member.send(embed=dm_embed)
    except discord.Forbidden:
        embed = EmbedTemplates.warning(
            "Could Not Send DM",
            f"Could not DM {member.display_name} about the kick."
        )
        await ctx.send(embed=embed)
        await log_action(ctx, f"Kick warning: Could not DM {member.display_name}.", ProfessionalColors.WARNING)

    try:
        await member.kick(reason=reason)
        embed = EmbedTemplates.error(
            title="Member Kicked",
            description=f"**{member.display_name}** has been kicked from the server."
        )
        embed.add_field(name="📋 Reason", value=reason, inline=False)
        embed.add_field(name="👮 Moderator", value=ctx.author.mention, inline=False)
        embed.set_thumbnail(url=member.avatar.url if member.avatar else None)
        await ctx.send(embed=embed)
        await log_action(ctx, f"User {ctx.author.display_name} kicked {member.display_name} for: {reason}.", ProfessionalColors.ERROR)
    except discord.Forbidden:
        embed = EmbedTemplates.error(
            "Permission Denied",
            f"I don't have permissions to kick {member.display_name}."
        )
        await ctx.send(embed=embed)
        await log_action(ctx, f"Failed kick: Bot lacks permissions to kick {member.display_name}.", ProfessionalColors.ERROR)
    except Exception as e:
        embed = EmbedTemplates.error(
            "Unexpected Error",
            f"An unexpected error occurred: {e}"
        )
        await ctx.send(embed=embed)
        await log_action(ctx, f"Failed kick due to unexpected error: {e}", ProfessionalColors.ERROR)

@bot.command(name='ban')
@access_level_required(1)
async def ban(ctx, member: discord.Member, *, reason: str = "No reason provided."):
    """Ban a member from the server and provide an appeal link.
    
    Usage: :ban <@user> [reason]
    Example: :ban @John Breaking server rules repeatedly
    
    Permanently bans member, DMs with appeal link, and logs action.
    """
    if not ctx.guild.me.guild_permissions.ban_members:
        embed = EmbedTemplates.error(
            "Missing Permissions",
            "I don't have the **Ban Members** permission required to ban users."
        )
        await ctx.send(embed=embed)
        await log_action(ctx, f"Failed ban: Bot lacks 'Ban Members' permission.", ProfessionalColors.ERROR)
        return
    
    if member.top_role >= ctx.author.top_role and ctx.author.id != ctx.guild.owner_id:
        embed = EmbedTemplates.error(
            "Cannot Ban User",
            "You cannot ban someone with an equal or higher role than yourself."
        )
        await ctx.send(embed=embed)
        await log_action(ctx, f"Failed ban: {ctx.author.display_name} tried to ban {member.display_name} with equal/higher role.", ProfessionalColors.ERROR)
        return
    
    if member.top_role >= ctx.guild.me.top_role:
        embed = EmbedTemplates.error(
            "Cannot Ban User",
            "I cannot ban someone with an equal or higher role than myself."
        )
        await ctx.send(embed=embed)
        await log_action(ctx, f"Failed ban: Bot tried to ban {member.display_name} with equal/higher role.", ProfessionalColors.ERROR)
        return

    try:
        dm_embed = EmbedTemplates.primary(
            title="Ban Form",
            description=(
                "You got banned from Anime Card Realms\n"
                f"Reason : {reason}\n"
                f"Author : {ctx.author.display_name}\n\n"
                "You can appeal your ban here - \n"
                f"{config.APPEAL_SERVER_INVITE_LINK}\n"
                "use *:appeal* to start it"
            )
        )
        await member.send(embed=dm_embed)
    except discord.Forbidden:
        embed = EmbedTemplates.warning(
            "Could Not Send DM",
            f"Could not DM {member.display_name} about the ban and appeal link."
        )
        await ctx.send(embed=embed)
        await log_action(ctx, f"Ban warning: Could not DM {member.display_name}.", ProfessionalColors.WARNING)

    try:
        await member.ban(reason=reason)
        embed = EmbedTemplates.error(
            title="Member Banned",
            description=f"**{member.display_name}** has been banned from the server."
        )
        embed.add_field(name="📋 Reason", value=reason, inline=False)
        embed.add_field(name="👮 Moderator", value=ctx.author.mention, inline=False)
        embed.set_thumbnail(url=member.avatar.url if member.avatar else None)
        await ctx.send(embed=embed)
        await log_action(ctx, f"User {ctx.author.display_name} banned {member.display_name} (ID: {member.id}) for: {reason}. Appeal link sent.", ProfessionalColors.ERROR)
    except discord.Forbidden:
        embed = EmbedTemplates.error(
            "Permission Denied",
            f"I don't have permissions to ban {member.display_name}."
        )
        await ctx.send(embed=embed)
        await log_action(ctx, f"Failed ban: Bot lacks permissions to ban {member.display_name}.", ProfessionalColors.ERROR)
    except Exception as e:
        embed = EmbedTemplates.error(
            "Unexpected Error",
            f"An unexpected error occurred: {e}"
        )
        await ctx.send(embed=embed)
        await log_action(ctx, f"Failed ban due to unexpected error: {e}", ProfessionalColors.ERROR)

@bot.command(name='warn')
@access_level_required(1)
async def warn(ctx, member: discord.Member, *, reason: str = "No reason provided."):
    """Warn a member about their behavior.
    
    Usage: :warn <@user> [reason]
    Example: :warn @John Using inappropriate language
    
    Sends warning DM, logs action, or sends to channel if DM fails.
    """
    embed = EmbedTemplates.warning(
        title="⚠️ Member Warning",
        description=f"**{member.display_name}** has been warned."
    )
    embed.add_field(name="📋 Reason", value=reason, inline=False)
    embed.add_field(name="👮 Moderator", value=ctx.author.mention, inline=False)
    embed.set_thumbnail(url=member.avatar.url if member.avatar else None)

    try:
        await member.send(embed=embed)
        success_embed = EmbedTemplates.success(
            "Warning Sent",
            f"Successfully warned {member.display_name} via DM."
        )
        await ctx.send(embed=success_embed)
        await log_action(ctx, f"User {ctx.author.display_name} warned {member.display_name} for: {reason}.", ProfessionalColors.WARNING)
    except discord.Forbidden:
        embed_warning = EmbedTemplates.warning(
            "Could Not Send DM",
            f"Could not DM {member.display_name} about the warning. Sending warning to current channel instead."
        )
        await ctx.send(embed=embed_warning)
        await ctx.send(embed=embed)
        await log_action(ctx, f"Warning sent to channel for {member.display_name} (DM failed) by {ctx.author.display_name} for: {reason}.", ProfessionalColors.WARNING)
    except Exception as e:
        embed = EmbedTemplates.error(
            "Unexpected Error",
            f"An unexpected error occurred: {e}"
        )
        await ctx.send(embed=embed)
        await log_action(ctx, f"Failed warn due to unexpected error: {e}", ProfessionalColors.ERROR)

# --- New Appeal Flow (Appeal Server only) ---
APPEAL_SESSIONS = {}

class AppealStartView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)

    @discord.ui.button(label="Start", style=discord.ButtonStyle.primary, custom_id="appeal_start")
    async def start(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AppealStep1Modal())

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger, custom_id="appeal_close")
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.message.delete()
        except Exception:
            pass
        await interaction.response.send_message("Closed.", ephemeral=True)

class ContinueView(discord.ui.View):
    def __init__(self, next_step: int):
        super().__init__(timeout=180)
        self.next_step = next_step

    @discord.ui.button(label="Continue", style=discord.ButtonStyle.primary, custom_id="appeal_continue")
    async def continue_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.next_step == 2:
            await interaction.response.send_modal(AppealStep2Modal())
        elif self.next_step == 3:
            await interaction.response.send_modal(AppealStep3Modal())
        elif self.next_step == 4:
            await interaction.response.send_modal(AppealStep4Modal())
        elif self.next_step == 5:
            await interaction.response.send_modal(AppealStep5Modal())

class FinishView(discord.ui.View):
    def __init__(self, session_user_id: int):
        super().__init__(timeout=180)
        self.session_user_id = session_user_id

    @discord.ui.button(label="Finish", style=discord.ButtonStyle.success, custom_id="appeal_finish")
    async def finish_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = APPEAL_SESSIONS.get(self.session_user_id)
        if not data:
            await interaction.response.send_message("Session not found or timed out. Please run :appeal again.", ephemeral=True)
            return

        # Build final embed for staff
        final_embed = EmbedTemplates.info(
            title="📝 Ban Appeal Submitted",
            description="A new ban appeal has been submitted and requires staff review."
        )
        final_embed.add_field(name="👤 Discord Username", value=data.get("username", "-"), inline=False)
        final_embed.add_field(name="🕒 When Banned", value=data.get("time", "-"), inline=False)
        final_embed.add_field(name="📋 Reason Mentioned", value=data.get("reason", "-"), inline=False)
        final_embed.add_field(name="📖 Their Perspective", value=data.get("why", "-"), inline=False)
        final_embed.add_field(name="✅ Acknowledgement", value=data.get("ack", "-"), inline=False)
        final_embed.set_footer(text=f"Appeal submitted by {interaction.user.display_name} (ID: {interaction.user.id})", icon_url=interaction.user.avatar.url if interaction.user.avatar else None)
        final_embed.timestamp = discord.utils.utcnow()

        appeal_log_channel = bot.get_channel(config.APPEAL_LOG_CHANNEL)
        if not appeal_log_channel:
            await interaction.response.send_message("Appeal log channel not found. Please contact an administrator.", ephemeral=True)
            return

        await appeal_log_channel.send(embed=final_embed, view=AppealStaffReviewView(appealer_id=interaction.user.id, username=data.get("username", "unknown")))
        # Clean up session
        APPEAL_SESSIONS.pop(self.session_user_id, None)
        await interaction.response.send_message("Your appeal has been submitted. Staff will review it soon.", ephemeral=True)

class AppealStep1Modal(discord.ui.Modal, title="Appeal - Step 1/5"):
    username = discord.ui.TextInput(label="Discord Username", placeholder="e.g., itsmelotex", max_length=100, required=True)

    async def on_submit(self, interaction: discord.Interaction):
        APPEAL_SESSIONS.setdefault(interaction.user.id, {})
        APPEAL_SESSIONS[interaction.user.id]["username"] = self.username.value
        embed = EmbedTemplates.info(
            title="Step 1 Saved",
            description="Please enter the time of the ban in the next step."
        )
        await interaction.response.send_message(embed=embed, view=ContinueView(next_step=2), ephemeral=True)

class AppealStep2Modal(discord.ui.Modal, title="Appeal - Step 2/5"):
    time_when = discord.ui.TextInput(label="When were you banned?", placeholder="day:month:year | HH:MM (24h) e.g., 01:10:2025 | 12:44", max_length=100, required=True)

    async def on_submit(self, interaction: discord.Interaction):
        APPEAL_SESSIONS.setdefault(interaction.user.id, {})
        APPEAL_SESSIONS[interaction.user.id]["time"] = self.time_when.value
        embed = EmbedTemplates.info(
            title="Step 2 Saved",
            description="Next, please enter the reason mentioned in the ban."
        )
        await interaction.response.send_message(embed=embed, view=ContinueView(next_step=3), ephemeral=True)

class AppealStep3Modal(discord.ui.Modal, title="Appeal - Step 3/5"):
    ban_reason = discord.ui.TextInput(label="Reason Mentioned in Ban", placeholder="e.g., Rule 3 violation, Spamming", max_length=500, required=True)

    async def on_submit(self, interaction: discord.Interaction):
        APPEAL_SESSIONS.setdefault(interaction.user.id, {})
        APPEAL_SESSIONS[interaction.user.id]["reason"] = self.ban_reason.value
        embed = EmbedTemplates.info(
            title="Step 3 Saved",
            description="Now, please explain why you think you were banned, and what really happened."
        )
        await interaction.response.send_message(embed=embed, view=ContinueView(next_step=4), ephemeral=True)

class AppealStep4Modal(discord.ui.Modal, title="Appeal - Step 4/5"):
    explanation = discord.ui.TextInput(label="Your Perspective / Real Scenario", style=discord.TextStyle.paragraph, placeholder="Describe what truly happened from your point of view.", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        APPEAL_SESSIONS.setdefault(interaction.user.id, {})
        APPEAL_SESSIONS[interaction.user.id]["why"] = self.explanation.value
        embed = EmbedTemplates.info(
            title="Step 4 Saved",
            description="Finally, please acknowledge the issue and confirm it won't happen again."
        )
        await interaction.response.send_message(embed=embed, view=ContinueView(next_step=5), ephemeral=True)

class AppealStep5Modal(discord.ui.Modal, title="Appeal - Step 5/5"):
    acknowledgement = discord.ui.TextInput(label="Acknowledgement", style=discord.TextStyle.paragraph, placeholder="State your understanding and commitment.", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        APPEAL_SESSIONS.setdefault(interaction.user.id, {})
        APPEAL_SESSIONS[interaction.user.id]["ack"] = self.acknowledgement.value
        embed = EmbedTemplates.success(
            title="Form Complete",
            description=(
                "Thank you for submitting your answers.\n"
                "Click Finish to send your appeal to our staff for review."
            )
        )
        await interaction.response.send_message(embed=embed, view=FinishView(session_user_id=interaction.user.id), ephemeral=True)

class AppealStaffReviewView(discord.ui.View):
    def __init__(self, appealer_id: int, username: str):
        super().__init__(timeout=None)
        self.appealer_id = appealer_id
        self.username = username

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.green, custom_id="appeal_staff_approve")
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        if not getattr(config, 'MAIN_GUILD_ID', 0):
            await interaction.followup.send("MAIN_GUILD_ID is not configured. Cannot unban.", ephemeral=True)
            return
        main_guild = bot.get_guild(config.MAIN_GUILD_ID)
        if not main_guild:
            await interaction.followup.send("Main guild not found. Ensure the bot is in the main server.", ephemeral=True)
            return
        try:
            banned_user = await bot.fetch_user(self.appealer_id)
            await main_guild.unban(banned_user, reason=f"Appeal approved by {interaction.user.display_name}")
            try:
                await banned_user.send(f"Your ban appeal for {main_guild.name} has been approved. You have been unbanned. Welcome Back To: {config.MAIN_SERVER_INVITE_LINK}")
            except discord.Forbidden:
                pass
            await interaction.message.edit(content=f"Appeal Approved for {self.username}.", view=None)
            await interaction.followup.send("Unbanned and notified.", ephemeral=True)
        except discord.NotFound:
            await interaction.followup.send("User not found or already unbanned.", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("I don't have permissions to unban in the main guild.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Unexpected error during approval: {e}", ephemeral=True)

    @discord.ui.button(label="Reject", style=discord.ButtonStyle.red, custom_id="appeal_staff_reject")
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        try:
            user = await bot.fetch_user(self.appealer_id)
            try:
                await user.send("Unfortunately, your ban appeal has been rejected. You remain banned from the server.")
            except discord.Forbidden:
                pass
            await interaction.message.edit(content=f"Appeal Rejected for {self.username}.", view=None)
            await interaction.followup.send("Appeal rejected and user notified.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Unexpected error during rejection: {e}", ephemeral=True)

    @discord.ui.button(label="Review", style=discord.ButtonStyle.blurple, custom_id="appeal_staff_review")
    async def review(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        try:
            guild = interaction.guild
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True)
            }
            for level in range(1, 6):
                role_ids = config.ACCESS_LEVELS.get(level, [])
                for role_id in role_ids:
                    role = guild.get_role(role_id)
                    if role:
                        overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

            channel_name = f"appeal-{self.username}".replace(" ", "-").lower()
            category = discord.utils.get(guild.categories, name="Appeal Discussions")
            if not category:
                category = await guild.create_category("Appeal Discussions", overwrites=overwrites)
            review_channel = await guild.create_text_channel(channel_name, category=category, overwrites=overwrites)
            original_embed = interaction.message.embeds[0] if interaction.message.embeds else None
            await review_channel.send(f"Appeal discussion for <@{self.appealer_id}> (username: {self.username}).", embed=original_embed)
            await interaction.followup.send(f"Review channel created: {review_channel.mention}", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("I don't have permissions to create channels or set overwrites.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Unexpected error during review channel creation: {e}", ephemeral=True)

@bot.command(name='appeal')
async def appeal(ctx):
    """Start the ban appeal process. Only usable in the configured Appeal channel."""
    # Restrict to specific channel (Appeal Server)
    if ctx.channel.id != getattr(config, 'APPEAL_CHANNEL_ID', 0):
        embed = EmbedTemplates.error("Wrong Channel", "Please use this command in the designated Appeal channel.")
        await ctx.send(embed=embed)
        return

    greeting = EmbedTemplates.primary(
        title="📝 Ban Appeal - Anime Card Realms",
        description=(
            "Welcome! This is the official form to appeal your ban from Anime Card Realms.\n\n"
            "Please follow the structure of the form. Click Start to begin or Close to cancel."
        )
    )
    greeting.set_footer(text="Appeals are reviewed by staff members. Please be honest and respectful.")
    await ctx.send(embed=greeting, view=AppealStartView())
    await log_action(ctx, f"User {ctx.author.display_name} opened the appeal form.", ProfessionalColors.INFO)

@bot.command(name='panel')
@access_level_required(4) # Level 4 and 5 can access panel
async def panel(ctx):
    """Open the ACR System management panel with statistics and actions.
    
    Usage: :panel
    
    Displays server stats, active staff, and admin action buttons.
    """
    panel_view = PanelView(bot)
    # Send an initial message and then update it with stats
    loading_embed = EmbedTemplates.info(
        title="📊 Loading ACR System Panel...",
        description="Please wait while we gather the latest server statistics."
    )
    initial_message = await ctx.send(embed=loading_embed, view=panel_view)
    await panel_view.update_panel_message(initial_message)
    await log_action(ctx, f"User {ctx.author.display_name} opened the management panel.", ProfessionalColors.INFO)


# --- Profile Command ---
@bot.command(name='profile')
@access_level_required(1)
async def profile(ctx, member: discord.Member = None):
    """Show a modern staff profile card. Usage: :profile [@member]"""
    target = member or ctx.author

    access_level = get_member_access_level(target)
    rank_name, perm_role, display_role, team_role = detect_member_rank(target)
    team_label = detect_member_team_label(target)

    # Compute presence online time estimation (based on join date for now)
    joined_at = target.joined_at
    created_at = target.created_at

    # Time in server (humanized)
    time_in_server = "-"
    if joined_at:
        delta = datetime.now(timezone.utc) - joined_at
        if delta.days >= 1:
            time_in_server = f"{delta.days} days"
        else:
            hours = delta.seconds // 3600
            minutes = (delta.seconds % 3600) // 60
            if hours > 0:
                time_in_server = f"{hours}h {minutes}m"
            else:
                time_in_server = f"{minutes}m"

    # Build modern, clean embed
    title_username = f"{target.display_name}"
    title_position = f" • {rank_name}" if rank_name else ""
    header = f"👤 {title_username}{title_position}"

    # Build badges to add uniqueness
    badges = []
    # Tenure badge
    if joined_at:
        tenure_days = (datetime.now(timezone.utc) - joined_at).days
        if tenure_days >= 365:
            badges.append("🏆 1+ Year Staff")
        elif tenure_days >= 180:
            badges.append("🎖️ 6+ Months Staff")
        elif tenure_days >= 90:
            badges.append("⭐ 90+ Days Staff")
    # Account age badge
    if created_at:
        account_years = (datetime.now(timezone.utc) - created_at).days // 365
        if account_years >= 5:
            badges.append("🛡️ Veteran (5y+)")
        elif account_years >= 2:
            badges.append("🧭 Established (2y+)")
    # Access level badge
    if access_level >= 5:
        badges.append("👑 Ownership/Lead")
    elif access_level == 4:
        badges.append("💼 Management/Dev")
    elif access_level == 3:
        badges.append("🎯 Head Team")
    elif access_level == 2:
        badges.append("👨‍💼 Admin Team")
    elif access_level == 1:
        badges.append("🔧 Moderation Team")

    badges_line = " \u2022 ".join(badges) if badges else ""

    embed = EmbedTemplates.primary(
        title=header,
        description=(
            "A concise overview of this staff member's standing and activity.\n"
            "\n"
            f"{(' '.join(['`Badges:`', badges_line]) if badges_line else '')}\n"
            f"Access Level: **{access_level or 0}**\n"
            f"Permission Role: {perm_role.mention if perm_role else '`Not detected`'}\n"
            f"Display Role: {display_role.mention if display_role else '`Not detected`'}\n"
            f"Team Role: {team_role.mention if team_role else '`Not detected`'}"
        )
    )

    # Visual hierarchy: big avatar, subtle accent thumbnail
    embed.set_thumbnail(url=target.avatar.url if target.avatar else None)

    # Highlight core identity
    embed.add_field(
        name="Identity",
        value=(
            f"Username: `{target}`\n"
            f"User ID: `{target.id}`\n"
            f"Team: `{team_label or 'N/A'}`"
        ),
        inline=True
    )

    # Live presence/activity
    presence_desc = []
    try:
        presence_desc.append(f"Status: `{str(target.status).title()}`")
        if target.activity and getattr(target.activity, 'name', None):
            presence_desc.append(f"Activity: `{target.activity.name}`")
    except Exception:
        pass
    presence_desc.append(f"Time in Server: `{time_in_server}`")
    presence_desc.append(f"Joined: `{joined_at.strftime('%Y-%m-%d %H:%M UTC') if joined_at else 'Unknown'}`")

    embed.add_field(name="Presence", value="\n".join(presence_desc), inline=True)

    # Account info, slightly de-emphasized
    embed.add_field(
        name="Account",
        value=(
            f"Created: `{created_at.strftime('%Y-%m-%d %H:%M UTC') if created_at else 'Unknown'}`\n"
            f"Bot: `{'Yes' if target.bot else 'No'}`\n"
            f"Top Role: `{target.top_role.name}`"
        ),
        inline=False
    )

    # Footer and accent
    embed.set_footer(
        text=f"Requested by {ctx.author.display_name} • {ctx.guild.name}",
        icon_url=ctx.guild.icon.url if ctx.guild.icon else None
    )

    # Accent banner if configured
    if getattr(config, 'PANEL_BANNER_URL', ''):
        embed.set_image(url=config.PANEL_BANNER_URL)

    await ctx.send(embed=embed)
    await log_action(ctx, f"Displayed staff profile for {target.display_name} (ID: {target.id}).", ProfessionalColors.INFO)

# --- Help System Classes and Views ---
class HelpMainView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300) # 5 minutes timeout

    @discord.ui.button(label="📚 Commands", style=discord.ButtonStyle.primary, custom_id="help_commands")
    async def commands_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        commands_view = HelpCommandsView()
        commands_embed = commands_view.create_commands_embed()
        await interaction.edit_original_response(embed=commands_embed, view=commands_view)

    @discord.ui.button(label="🔐 Access Levels", style=discord.ButtonStyle.secondary, custom_id="help_access_levels")
    async def access_levels_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        access_view = HelpAccessLevelsView()
        access_embed = access_view.create_access_levels_embed()
        await interaction.edit_original_response(embed=access_embed, view=access_view)

    @discord.ui.button(label="📖 Usage Guide", style=discord.ButtonStyle.secondary, custom_id="help_usage_guide")
    async def usage_guide_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        usage_view = HelpUsageGuideView()
        usage_embed = usage_view.create_usage_guide_embed()
        await interaction.edit_original_response(embed=usage_embed, view=usage_view)

    @discord.ui.button(label="❌ Close", style=discord.ButtonStyle.danger, custom_id="help_close")
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await interaction.delete_original_response()

class HelpCommandsView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)

    def create_commands_embed(self):
        embed = EmbedTemplates.primary(
            title="📚 ACR - System Bot Commands",
            description="Here are all the available commands organized by access level."
        )
        
        # Level 1 - Moderation Team
        embed.add_field(
            name="🔧 Level 1 - Moderation Team",
            value="`ping` - Check bot latency\n`commands` - Show this help menu\n`help` - Interactive help system\n`kick` - Kick a member from server\n`warn` - Warn a member about behavior\n`ban` - Ban a member from server\n`profile [@user]` - Show staff profile",
            inline=False
        )
        
        # Level 2 - Admin Team
        embed.add_field(
            name="👨‍💼 Level 2 - Admin Team",
            value="`test_access` - Test your access level\n`announcement` - Send announcements to channels",
            inline=False
        )
        
        # Level 3 - Head Team
        embed.add_field(
            name="🎯 Level 3 - Head Team",
            value="`promote` - Promote a staff member\n`demote` - Demote a staff member",
            inline=False
        )
        
        # Level 4-5 - Management & Ownership Team
        embed.add_field(
            name="👑 Level 4-5 - Management & Ownership Team",
            value="`panel` - Open system management panel\n*Plus all panel features: Bot restart, Channel backup*",
            inline=False
        )
        
        # Appeal system
        embed.add_field(
            name="📝 Appeal System",
            value="`appeal` - Start ban appeal process",
            inline=False
        )
        
        embed.set_footer(text="Use the buttons below to navigate or close this help menu.")
        return embed

    @discord.ui.button(label="⬅️ Back", style=discord.ButtonStyle.secondary, custom_id="commands_back")
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        main_view = HelpMainView()
        main_embed = main_view.create_main_embed()
        await interaction.edit_original_response(embed=main_embed, view=main_view)

    @discord.ui.button(label="❌ Close", style=discord.ButtonStyle.danger, custom_id="commands_close")
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await interaction.delete_original_response()

class HelpAccessLevelsView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)

    def create_access_levels_embed(self):
        embed = EmbedTemplates.secondary(
            title="🔐 ACR - Access Levels System",
            description="Here are all the access levels and their assigned commands."
        )
        
        # Level 5 - Ownership Team
        embed.add_field(
            name="👑 Access Level 5",
            value="**Assigned Rank:** Lead & Ownership Team\n**Assigned Commands:** All commands + Bot restart + Channel backup",
            inline=False
        )
        
        # Level 4 - Management & Development Team
        embed.add_field(
            name="💼 Access Level 4",
            value="**Assigned Rank:** Management & Development Team\n**Assigned Commands:** All Level 1-3 commands + Panel + Channel backup",
            inline=False
        )
        
        # Level 3 - Head Team
        embed.add_field(
            name="🎯 Access Level 3",
            value="**Assigned Rank:** Head Team\n**Assigned Commands:** All Level 1-2 commands + Promote, Demote",
            inline=False
        )
        
        # Level 2 - Admin Team
        embed.add_field(
            name="👨‍💼 Access Level 2",
            value="**Assigned Rank:** Admin Team\n**Assigned Commands:** All Level 1 commands + Test Access, Announcements",
            inline=False
        )
        
        # Level 1 - Moderation Team
        embed.add_field(
            name="🔧 Access Level 1",
            value="**Assigned Rank:** Moderation Team\n**Assigned Commands:** Ping, Commands, Help, Kick, Warn, Ban",
            inline=False
        )
        
        embed.set_footer(text="Higher levels inherit all commands from lower levels.")
        return embed

    @discord.ui.button(label="⬅️ Back", style=discord.ButtonStyle.secondary, custom_id="access_back")
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        main_view = HelpMainView()
        main_embed = main_view.create_main_embed()
        await interaction.edit_original_response(embed=main_embed, view=main_view)

    @discord.ui.button(label="❌ Close", style=discord.ButtonStyle.danger, custom_id="access_close")
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await interaction.delete_original_response()

class HelpUsageGuideView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)

    def create_usage_guide_embed(self):
        embed = EmbedTemplates.info(
            title="📖 ACR - Command Usage Guide",
            description="Here are examples of how to use commands with proper arguments."
        )
        
        # Level 1 - Moderation commands
        embed.add_field(
            name="🔧 Level 1 - Moderation Commands",
            value="`kick @user [reason]`\n`kick @itsmelotex Spamming in general chat`\n\n`warn @user [reason]`\n`warn @itsmelotex Using inappropriate language`\n\n`ban @user [reason]`\n`ban @itsmelotex Breaking server rules repeatedly`",
            inline=False
        )
        
        # Level 2 - Admin commands
        embed.add_field(
            name="👨‍💼 Level 2 - Admin Commands",
            value="`test_access`\n*No arguments required*\n\n`announcement [channel_var] [message]`\n`announcement ann-main Server maintenance scheduled`\n\n**Available channels:** ann-main, ann-sub, ann-staff, ann-tester, ann-trello, updates, sneak-peaks",
            inline=False
        )
        
        # Level 3 - Head commands
        embed.add_field(
            name="🎯 Level 3 - Head Commands",
            value="`promote @user [rank]`\n`promote @itsmelotex Moderator`\n\n`demote @user [rank]`\n`demote @itsmelotex Moderator`\n\n**Available ranks:** Moderator, Senior Moderator, Administrator, Senior Administrator, Junior Administrator, Head Administrator, Head Moderator, Head Helper, Staff Supervisor, Developer, Senior Developer, Server Manager, Community Manager, Project Lead, Server Lead, Team Lead",
            inline=False
        )
        
        # Level 4-5 - Management commands
        embed.add_field(
            name="👑 Level 4-5 - Management Commands",
            value="`panel`\n*No arguments required - Opens system management panel*",
            inline=False
        )
        
        # Appeal command
        embed.add_field(
            name="📝 Appeal Command",
            value="`appeal [user_id]`\n`appeal 123456789012345678`",
            inline=False
        )
        
        embed.set_footer(text="Replace @itsmelotex with actual user mentions and adjust examples as needed.")
        return embed

    @discord.ui.button(label="⬅️ Back", style=discord.ButtonStyle.secondary, custom_id="usage_back")
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        main_view = HelpMainView()
        main_embed = main_view.create_main_embed()
        await interaction.edit_original_response(embed=main_embed, view=main_view)

    @discord.ui.button(label="❌ Close", style=discord.ButtonStyle.danger, custom_id="usage_close")
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await interaction.delete_original_response()

# Add create_main_embed method to HelpMainView
def create_main_embed(self):
    embed = EmbedTemplates.primary(
        title="🎉 Welcome to ACR - System Bot Help!",
        description="Welcome to the ACR System Bot help center! Here you can find all the information you need about commands, access levels, and usage guides."
    )
    
    embed.add_field(
        name="⚠️ Important Notice",
        value="**Please use the Bot and commands in Commands Related Channels only!**\n\nThis helps keep the server organized and ensures proper moderation.",
        inline=False
    )
    
    embed.add_field(
        name="📋 Choose a Category",
        value="Select one of the options below to proceed:",
        inline=False
    )
    
    embed.set_footer(text="Use the buttons below to navigate through the help system.")
    return embed

# Add the method to HelpMainView class
HelpMainView.create_main_embed = create_main_embed

# Custom help command to override the default one
class CustomHelpCommand(commands.HelpCommand):
    def __init__(self):
        super().__init__()
    
    async def send_bot_help(self, mapping):
        # Check if user has at least level 1 access
        if not has_access_level(self.context, 1):
            embed = EmbedTemplates.error(
                "Access Denied",
                f"You need **Access Level 1** or higher to use the help command.\n\n"
                f"**Current Access Levels:**\n"
                f"• **Level 1:** Moderation Team\n"
                f"• **Level 2:** Admin Team\n"
                f"• **Level 3:** Head Team\n"
                f"• **Level 4:** Management & Development Team\n"
                f"• **Level 5:** Lead & Ownership Team"
            )
            embed.set_footer(text="Contact a staff member if you believe this is an error.")
            await self.get_destination().send(embed=embed)
            return
        
        # Send interactive help
        help_view = HelpMainView()
        main_embed = help_view.create_main_embed()
        await self.get_destination().send(embed=main_embed, view=help_view)
    
    async def send_command_help(self, command):
        embed = EmbedTemplates.info(
            f"📖 {command.name}",
            command.help or "No description available."
        )
        
        # Add usage information
        usage = f"`{self.context.prefix}{command.name}"
        if command.signature:
            usage += f" {command.signature}"
        usage += "`"
        
        embed.add_field(name="Usage", value=usage, inline=False)
        
        # Add simple examples for key commands
        examples = {
            'promote': f"`{self.context.prefix}promote @user Moderator`",
            'demote': f"`{self.context.prefix}demote @user Moderator`",
            'ban': f"`{self.context.prefix}ban @user Breaking rules`",
            'kick': f"`{self.context.prefix}kick @user Spamming`",
            'warn': f"`{self.context.prefix}warn @user Bad language`",
            'announcement': f"`{self.context.prefix}announcement ann-main Message`",
            'appeal': f"`{self.context.prefix}appeal 123456789`",
            'panel': f"`{self.context.prefix}panel`",
            'profile': f"`{self.context.prefix}profile @user`"
        }
        
        if command.name in examples:
            embed.add_field(name="Example", value=examples[command.name], inline=False)
        
        await self.get_destination().send(embed=embed)

# Set the custom help command
bot.help_command = CustomHelpCommand()

# Ensure the bot starts and runs
if __name__ == "__main__":
    bot.run(os.getenv('DISCORD_TOKEN'))

