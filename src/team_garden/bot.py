"""The Discord client: slash commands and the daily reminder loop."""

import os
from datetime import date, datetime, timedelta

import discord
from discord import app_commands
from discord.ext import tasks
from dotenv import load_dotenv

from .garden import add_hour, parse_reminder
from .render import garden_embed, help_embed, myflower_embed, needs_embed
from .store import Garden, Store
from .views import PROMPT, CheckinButton, CheckinView, MemberPicker, reminder_view


class GardenBot(discord.Client):
    def __init__(self, store: Store, guild_id: int | None = None) -> None:
        # Default intents only: no privileged intents are needed.
        super().__init__(intents=discord.Intents.default())
        self.store = store
        self.guild_id = guild_id
        self.tree = app_commands.CommandTree(self)
        self.posted: set[tuple[int, str, date]] = set()
        register_commands(self)

    async def setup_hook(self) -> None:
        self.add_dynamic_items(CheckinButton)
        if self.guild_id:
            # Syncing to one server is instant, which is handy while testing.
            guild = discord.Object(id=self.guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()
        self.daily_loop.start()

    async def on_ready(self) -> None:
        print(f"team-garden is online as {self.user}")

    @tasks.loop(seconds=30)
    async def daily_loop(self) -> None:
        """Post the reminder at each garden's time and the summary an hour later."""
        now = datetime.now()
        hhmm, today = now.strftime("%H:%M"), now.date()
        for garden in self.store.all_gardens():
            if hhmm == garden.reminder:
                await self._post_once(garden, "reminder", today)
            elif hhmm == add_hour(garden.reminder):
                # A summary just after midnight still belongs to yesterday.
                day = today if hhmm > garden.reminder else today - timedelta(days=1)
                await self._post_once(garden, "summary", day)

    @daily_loop.before_loop
    async def _wait_until_ready(self) -> None:
        await self.wait_until_ready()

    async def _post_once(self, garden: Garden, kind: str, day: date) -> None:
        key = (garden.channel_id, kind, day)
        if key in self.posted:
            return
        self.posted.add(key)
        channel = self.get_channel(garden.channel_id)
        if not isinstance(channel, discord.abc.Messageable):
            return
        try:
            if kind == "reminder":
                await self._send_reminders(garden, channel)
            else:
                latest = self.store.latest_checkins(garden.channel_id)
                members = self.store.members(garden.channel_id)
                await channel.send(
                    embed=garden_embed(garden, latest, day, members),
                    allowed_mentions=discord.AllowedMentions.none(),
                )
        except discord.HTTPException as error:
            print(f"Could not post {kind} to {garden.channel_id}: {error}")

    async def _send_reminders(
        self, garden: Garden, channel: discord.abc.Messageable
    ) -> None:
        """DM every team member a private "Check in" button."""
        members = self.store.members(garden.channel_id)
        if not members:
            await channel.send(
                "🌙 End-of-day check-in: run `/checkin` here. "
                "(Run `/garden members` to pick the team and I'll DM them instead.)"
            )
            return
        missed = []
        for user_id in members:
            try:
                user = self.get_user(user_id) or await self.fetch_user(user_id)
                await user.send(
                    f"🌙 End of day for **{garden.project}**. How did the work "
                    "go, and what do you need to keep shipping? Your check-in "
                    "stays private between you, the bot, and your lead.",
                    view=reminder_view(garden.channel_id),
                )
            except discord.HTTPException:
                missed.append(user_id)
        if missed:
            # Ping only the people the bot could not reach, so they know why.
            await channel.send(
                "🌙 I couldn't DM "
                + " ".join(f"<@{user_id}>" for user_id in missed)
                + ". Turn on **Allow DMs from server members** for this server, "
                "or run `/checkin` here.",
                allowed_mentions=discord.AllowedMentions(users=True),
            )


async def _garden_here(interaction: discord.Interaction, store: Store) -> Garden | None:
    """Find the garden for this channel, or tell the user there isn't one."""
    garden = store.get_garden(interaction.channel_id or 0)
    if garden is None:
        await interaction.response.send_message(
            "This channel has no garden yet. Someone with **Manage Server** "
            "can run `/garden setup` here.",
            ephemeral=True,
        )
    return garden


def register_commands(bot: GardenBot) -> None:
    store, tree = bot.store, bot.tree
    garden_group = app_commands.Group(
        name="garden", description="Your team's garden", guild_only=True
    )

    @garden_group.command(name="setup", description="Plant a garden in this channel")
    @app_commands.describe(
        project="Project name shown on the garden",
        lead="The team lead, who sees needs and blockers with /needs",
        reminder="Daily reminder time, 24-hour HH:MM in the bot host's time zone",
        stale_days="Days without a check-in before a flower is unwatered",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setup(
        interaction: discord.Interaction,
        project: str,
        lead: discord.Member,
        reminder: str = "17:00",
        stale_days: app_commands.Range[int, 1, 30] = 2,
    ) -> None:
        try:
            reminder = parse_reminder(reminder)
        except ValueError as error:
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        store.save_garden(
            Garden(
                channel_id=interaction.channel_id or 0,
                guild_id=interaction.guild_id or 0,
                project=project,
                lead_id=lead.id,
                reminder=reminder,
                stale_days=stale_days,
            )
        )
        await interaction.response.send_message(
            f"🪴 Planted the **{project}** garden in this channel.\n"
            f"Team lead: {lead.mention} · reminder at **{reminder}** "
            f"(summary at {add_hour(reminder)}) · unwatered after "
            f"**{stale_days}** day(s).\n"
            "Make this channel private to your team so only they see the garden.",
            allowed_mentions=discord.AllowedMentions.none(),
        )
        await interaction.followup.send(
            "👥 Now pick the team. I'll DM each of them for their check-in.",
            view=MemberPicker(store, interaction.channel_id or 0, interaction.user.id),
            ephemeral=True,
        )

    @garden_group.command(name="members", description="Choose who gets check-in DMs")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def members(interaction: discord.Interaction) -> None:
        if garden := await _garden_here(interaction, store):
            await interaction.response.send_message(
                "👥 Pick the team. I'll DM each of them for their check-in.",
                view=MemberPicker(store, garden.channel_id, interaction.user.id),
                ephemeral=True,
            )

    @garden_group.command(name="view", description="Show the team's overall health")
    async def view(interaction: discord.Interaction) -> None:
        if garden := await _garden_here(interaction, store):
            latest = store.latest_checkins(garden.channel_id)
            members = store.members(garden.channel_id)
            await interaction.response.send_message(
                embed=garden_embed(garden, latest, date.today(), members),
                allowed_mentions=discord.AllowedMentions.none(),
            )

    tree.add_command(garden_group)

    @tree.command(name="checkin", description="End-of-day check-in on your work")
    @app_commands.guild_only()
    async def checkin(interaction: discord.Interaction) -> None:
        if garden := await _garden_here(interaction, store):
            await interaction.response.send_message(
                PROMPT,
                view=CheckinView(store, garden.channel_id, interaction.user.id),
                ephemeral=True,
            )

    @tree.command(name="myflower", description="Your work and focus over 7 days")
    @app_commands.guild_only()
    async def myflower(interaction: discord.Interaction) -> None:
        if garden := await _garden_here(interaction, store):
            today = date.today()
            history = store.history(
                garden.channel_id, interaction.user.id, today - timedelta(days=6)
            )
            await interaction.response.send_message(
                embed=myflower_embed(history, today), ephemeral=True
            )

    @tree.command(name="needs", description="Lead only: needs, blockers, and toil")
    @app_commands.guild_only()
    async def needs(interaction: discord.Interaction) -> None:
        if garden := await _garden_here(interaction, store):
            if interaction.user.id != garden.lead_id:
                await interaction.response.send_message(
                    f"Only the team lead, <@{garden.lead_id}>, can see the team's needs.",
                    ephemeral=True,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
                return
            today = date.today()
            week = store.recent(garden.channel_id, today - timedelta(days=6))
            await interaction.response.send_message(
                embed=needs_embed(store.needs_on(garden.channel_id, today), today, week),
                ephemeral=True,
            )

    @tree.command(name="forgetme", description="Delete all your check-ins here")
    @app_commands.guild_only()
    async def forgetme(interaction: discord.Interaction) -> None:
        if garden := await _garden_here(interaction, store):
            count = store.forget(garden.channel_id, interaction.user.id)
            await interaction.response.send_message(
                f"🍃 Deleted {count} check-in(s). Your flower is gone from "
                f"the **{garden.project}** garden.",
                ephemeral=True,
            )

    @tree.command(name="help", description="How team-garden works and its commands")
    async def help_command(interaction: discord.Interaction) -> None:
        garden = store.get_garden(interaction.channel_id or 0)
        await interaction.response.send_message(
            embed=help_embed(garden),
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @tree.error
    async def on_error(
        interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        if isinstance(error, app_commands.MissingPermissions):
            message = "You need the **Manage Server** permission for that."
        else:
            message = "Something went wrong. Please try again."
            print(f"Command error: {error!r}")
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)


def main() -> None:
    load_dotenv()
    token = os.environ.get("DISCORD_TOKEN")
    if not token:
        raise SystemExit("Set DISCORD_TOKEN in .env (see .env.example).")
    guild_id = os.environ.get("DISCORD_GUILD_ID")
    store = Store(os.environ.get("GARDEN_DB", "garden.db"))
    GardenBot(store, int(guild_id) if guild_id else None).run(token)
