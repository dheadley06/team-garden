"""Interactive pieces: the check-in form, the DM "Check in" button, and the
team member picker."""

import re
from collections.abc import Callable
from datetime import date

import discord

from .garden import ENERGIES, MOODS, NEEDS, WORK, join_needs
from .render import checkin_embed
from .store import Checkin, Store

QUESTIONS = (
    "How did today's engineering work go, how is your focus, what did you "
    "work on, and **what do you need** from your lead to keep shipping?"
)
PROMPT = f"🌙 **End-of-day check-in.** {QUESTIONS} Only you can see this."
DM_PROMPT = (
    "🌙 **End-of-day check-in for {project}.** " + QUESTIONS + " This is a private DM."
)


def _remember_choice(select: discord.ui.Select) -> None:
    """Mark the chosen options as defaults so they stay shown when the view is redrawn."""
    for option in select.options:
        option.default = option.value in select.values


class NotesModal(discord.ui.Modal, title="Blockers & updates"):
    def __init__(self, view: "CheckinView") -> None:
        super().__init__()
        self.view = view
        self.blocker = discord.ui.TextInput(
            label="Blocked on anything? (only your lead sees)",
            style=discord.TextStyle.paragraph,
            required=False,
            max_length=500,
            placeholder="A PR waiting on review, missing access, a flaky test, "
            "an open design question...",
            default=view.blocker,
        )
        self.note = discord.ui.TextInput(
            label="A win or lesson (private unless shared)",
            style=discord.TextStyle.paragraph,
            required=False,
            max_length=300,
            placeholder="Merged the auth refactor; figured out the caching bug...",
            default=view.note,
        )
        self.add_item(self.blocker)
        self.add_item(self.note)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        self.view.blocker = self.blocker.value.strip() or None
        self.view.note = self.note.value.strip() or None
        await interaction.response.edit_message(
            content=PROMPT + "\n✏️ Blockers and updates saved.", view=self.view
        )


class CheckinView(discord.ui.View):
    def __init__(
        self,
        store: Store,
        channel_id: int,
        user_id: int,
        today: Callable[[], date] = date.today,
    ) -> None:
        super().__init__(timeout=900)
        self.store = store
        self.channel_id = channel_id
        self.user_id = user_id
        self.today = today
        self.mood: int | None = None
        self.energy: int | None = None
        self.need: str | None = None
        self.work: str | None = None
        self.blocker: str | None = None
        self.note: str | None = None
        self.share_note = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id

    @discord.ui.select(
        placeholder="How did today's engineering work go?",
        options=[
            discord.SelectOption(label=f"{v} · {name}", value=str(v))
            for v, name in MOODS.items()
        ],
        row=0,
    )
    async def pick_mood(
        self, interaction: discord.Interaction, select: discord.ui.Select
    ) -> None:
        self.mood = int(select.values[0])
        _remember_choice(select)
        await interaction.response.edit_message(view=self)

    @discord.ui.select(
        placeholder="How are your focus and workload?",
        options=[
            discord.SelectOption(label=f"{v} · {name}", value=str(v))
            for v, name in ENERGIES.items()
        ],
        row=1,
    )
    async def pick_energy(
        self, interaction: discord.Interaction, select: discord.ui.Select
    ) -> None:
        self.energy = int(select.values[0])
        _remember_choice(select)
        await interaction.response.edit_message(view=self)

    @discord.ui.select(
        placeholder="What did you mainly work on?",
        options=[
            discord.SelectOption(label=label, value=value)
            for value, label in WORK.items()
        ],
        row=2,
    )
    async def pick_work(
        self, interaction: discord.Interaction, select: discord.ui.Select
    ) -> None:
        self.work = select.values[0]
        _remember_choice(select)
        await interaction.response.edit_message(view=self)

    @discord.ui.select(
        placeholder="What do you need from your lead? (pick any)",
        options=[
            discord.SelectOption(label=label, value=value, description=description)
            for value, (label, description) in NEEDS.items()
        ],
        min_values=1,
        max_values=len(NEEDS),
        row=3,
    )
    async def pick_need(
        self, interaction: discord.Interaction, select: discord.ui.Select
    ) -> None:
        self.need = join_needs(select.values)
        _remember_choice(select)
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="Blockers & updates", emoji="📝", row=4)
    async def notes(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.send_modal(NotesModal(self))

    @discord.ui.button(label="Share update with team: off", emoji="🔒", row=4)
    async def toggle_share(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.share_note = not self.share_note
        button.label = f"Share update with team: {'on' if self.share_note else 'off'}"
        button.emoji = "👥" if self.share_note else "🔒"
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="Submit", style=discord.ButtonStyle.success, row=4)
    async def submit(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if None in (self.mood, self.energy, self.work, self.need):
            await interaction.response.send_message(
                "Answer all four menus first: how the work went, your focus, "
                "what you worked on, and what you need.",
                ephemeral=True,
            )
            return
        checkin = Checkin(
            channel_id=self.channel_id,
            user_id=self.user_id,
            date=self.today(),
            mood=self.mood,
            energy=self.energy,
            need=self.need,
            blocker=self.blocker,
            note=self.note,
            share_note=self.share_note,
            work=self.work,
        )
        self.store.add_checkin(checkin)
        self.stop()
        await interaction.response.edit_message(
            content=None, embed=checkin_embed(checkin), view=None
        )


class CheckinButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"garden:checkin:(?P<channel_id>\d+)",
):
    """The "Check in" button in a reminder DM.

    The garden's channel is stored in the button's custom_id, so the button
    keeps working after the bot restarts.
    """

    def __init__(self, channel_id: int) -> None:
        super().__init__(
            discord.ui.Button(
                label="Check in",
                emoji="🌙",
                style=discord.ButtonStyle.success,
                custom_id=f"garden:checkin:{channel_id}",
            )
        )
        self.channel_id = channel_id

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Button,
        match: re.Match[str],
    ) -> "CheckinButton":
        return cls(int(match["channel_id"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        store: Store = interaction.client.store  # type: ignore[attr-defined]
        garden = store.get_garden(self.channel_id)
        if garden is None or interaction.user.id not in store.members(garden.channel_id):
            await interaction.response.send_message(
                "You're no longer part of this garden."
            )
            return
        await interaction.response.send_message(
            DM_PROMPT.format(project=garden.project),
            view=CheckinView(store, garden.channel_id, interaction.user.id),
        )


def reminder_view(channel_id: int) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    view.add_item(CheckinButton(channel_id))
    return view


class MemberPicker(discord.ui.View):
    """Lets the person who ran /garden setup choose who gets check-in DMs."""

    def __init__(self, store: Store, channel_id: int, owner_id: int) -> None:
        super().__init__(timeout=600)
        self.store = store
        self.channel_id = channel_id
        self.owner_id = owner_id
        current = store.members(channel_id)
        self.pick.default_values = [
            discord.SelectDefaultValue(id=user_id, type=discord.SelectDefaultValueType.user)
            for user_id in current
        ]

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.owner_id

    @discord.ui.select(
        cls=discord.ui.UserSelect,
        placeholder="Who is on the team? (up to 25)",
        min_values=1,
        max_values=25,
    )
    async def pick(
        self, interaction: discord.Interaction, select: discord.ui.UserSelect
    ) -> None:
        people = [user for user in select.values if not user.bot]
        self.store.set_members(self.channel_id, [user.id for user in people])
        names = ", ".join(user.mention for user in people) or "nobody"
        await interaction.response.edit_message(
            content=(
                f"👥 Team saved: {names}.\nEach of them will get a DM at reminder "
                "time asking for their check-in. They need **Allow DMs from "
                "server members** turned on for this server."
            ),
            view=self,
            allowed_mentions=discord.AllowedMentions.none(),
        )
