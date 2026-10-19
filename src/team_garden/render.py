"""Builds the Discord embeds the bot sends."""

from datetime import date, timedelta

import discord

from .garden import (
    ENERGIES,
    GARDEN_ART,
    MIN_ANONYMOUS,
    MOODS,
    WORK,
    add_hour,
    flower_score,
    garden_health,
    garden_insights,
    health_label,
    is_stale,
    make_flower,
    need_labels,
    toil_counts,
    work_mix,
)
from .store import Checkin, Garden

GREEN = discord.Color.from_rgb(88, 166, 92)
AMBER = discord.Color.from_rgb(214, 158, 46)
RED = discord.Color.from_rgb(196, 78, 82)


def _bar(value: int) -> str:
    return "▰" * value + "▱" * (5 - value)


def garden_embed(
    garden: Garden, latest: list[Checkin], today: date, members: list[int]
) -> discord.Embed:
    """The team's garden as a whole: one health score, an ASCII garden, and
    team-wide things to improve.

    It never says how any one person is doing. Averages only appear once
    MIN_ANONYMOUS people have checked in, so no one can be singled out. The
    garden holds the team's members; before any are chosen it holds everyone
    who has checked in.
    """
    by_user = {c.user_id: c for c in latest}
    people = members or list(by_user)
    watered = [
        c
        for user_id in people
        if (c := by_user.get(user_id))
        and not is_stale(c.date, today, garden.stale_days)
    ]
    total = len(people)
    anonymous = len(watered) >= MIN_ANONYMOUS

    health = garden_health(
        [flower_score(c.mood, c.energy) for c in watered] + [None] * (total - len(watered))
    )
    label = health_label(health) if anonymous else None
    if label is None:
        color = discord.Color.light_grey()
    else:
        color = GREEN if health >= 60 else AMBER if health >= 40 else RED
    embed = discord.Embed(title=f"🪴 {garden.project} garden", color=color)
    if not total:
        embed.description = "No one has checked in yet. Start with `/checkin`."
        return _add_art(embed)

    if anonymous:
        embed.add_field(name="Health", value=f"**{health}/100** · {label}")
    else:
        embed.add_field(
            name="Health",
            value=f"Shows once {MIN_ANONYMOUS} people have checked in, "
            "so no one's answers can be picked out.",
        )
    embed.add_field(name="Checked in", value=f"{len(watered)} of {total}")

    if anonymous:
        n = len(watered)
        avg_work = sum(c.mood for c in watered) / n
        avg_focus = sum(c.energy for c in watered) / n
        embed.add_field(
            name="Team averages",
            value=f"Work going well `{_bar(round(avg_work))}` {avg_work:.1f}/5\n"
            f"Focus and load `{_bar(round(avg_focus))}` {avg_focus:.1f}/5",
            inline=False,
        )
        mix = work_mix(watered)
        if mix:
            embed.add_field(
                name="Where the time went",
                value=" · ".join(f"{WORK[key]} {share:.0%}" for key, share in mix),
                inline=False,
            )

    tips = garden_insights(watered, total)
    if anonymous and not tips:
        tips = ["🌼 Nothing stands out. Keep it up, and praise good work in public."]
    if tips:
        embed.add_field(
            name="🔧 What to improve",
            value="\n".join(f"• {tip}" for tip in tips),
            inline=False,
        )

    wins = [f"• <@{c.user_id}>: {c.note}" for c in watered if c.share_note and c.note]
    if wins:
        embed.add_field(name="🏆 Shared wins", value="\n".join(wins)[:1024], inline=False)

    embed.set_footer(
        text="Health = how the work is going × how many people check in. "
        "Individual answers are never shown here."
    )
    return _add_art(embed)


def _add_art(embed: discord.Embed) -> discord.Embed:
    """Put the ASCII garden at the bottom, as the embed's last field."""
    embed.add_field(name="​", value=f"```\n{GARDEN_ART}\n```", inline=False)
    return embed


def checkin_embed(checkin: Checkin) -> discord.Embed:
    """What the person sees right after checking in (ephemeral)."""
    flower = make_flower(
        checkin.user_id, checkin.date, checkin.mood, checkin.energy, checkin.date, 1
    )
    embed = discord.Embed(
        title=f"{flower.emoji} Your flower is {flower.label}", color=GREEN
    )
    embed.add_field(
        name="Today's work", value=f"{_bar(checkin.mood)} {MOODS[checkin.mood]}"
    )
    embed.add_field(
        name="Focus & load", value=f"{_bar(checkin.energy)} {ENERGIES[checkin.energy]}"
    )
    if checkin.work in WORK:
        embed.add_field(name="Worked on", value=WORK[checkin.work], inline=False)
    embed.add_field(
        name="You need (lead only)",
        value=", ".join(need_labels(checkin.need)),
        inline=False,
    )
    if checkin.blocker:
        embed.add_field(name="Blocker (lead only)", value=checkin.blocker, inline=False)
    if checkin.note:
        who = "the team" if checkin.share_note else "only you"
        embed.add_field(name=f"Update (seen by {who})", value=checkin.note, inline=False)
    embed.set_footer(text="Thanks for checking in. Log off and rest. 🌙")
    return embed


def myflower_embed(history: list[Checkin], today: date, days: int = 7) -> discord.Embed:
    """A person's own trend over the last week (ephemeral)."""
    by_day = {c.date: c for c in history}
    lines = []
    for offset in range(days - 1, -1, -1):
        day = today - timedelta(days=offset)
        c = by_day.get(day)
        stamp = day.strftime("%a %m/%d")
        if c is None:
            lines.append(f"`{stamp}` 🌱 no check-in")
            continue
        emoji = make_flower(c.user_id, c.date, c.mood, c.energy, c.date, 1).emoji
        work = f" · {WORK[c.work]}" if c.work in WORK else ""
        lines.append(
            f"`{stamp}` {emoji} work `{_bar(c.mood)}` focus `{_bar(c.energy)}`{work}"
        )
    embed = discord.Embed(
        title=f"Your flower, last {days} days",
        description="\n".join(lines),
        color=GREEN,
    )
    if history:
        avg_mood = sum(c.mood for c in history) / len(history)
        avg_energy = sum(c.energy for c in history) / len(history)
        embed.set_footer(
            text=f"Average work {avg_mood:.1f} · average focus {avg_energy:.1f}. "
            "Low focus for days in a row? Bring it up with your lead."
        )
    return embed


def needs_embed(
    needs: list[Checkin], today: date, week: list[Checkin] = ()
) -> discord.Embed:
    """For the lead: who asked for what today, and who is carrying the toil."""
    embed = discord.Embed(
        title=f"What does the team need? · {today:%a %m/%d}", color=AMBER
    )
    lines = []
    for c in needs:
        line = f"<@{c.user_id}> · **{', '.join(need_labels(c.need))}**"
        if c.blocker:
            line += f"\n  🚧 {c.blocker}"
        lines.append(line)
    embed.description = "\n".join(lines) or "No one asked for anything today. 🌿"

    work_by_user: dict[int, list[str | None]] = {}
    for c in week:
        work_by_user.setdefault(c.user_id, []).append(c.work)
    toil = toil_counts(work_by_user)
    if toil:
        embed.add_field(
            name="🧹 Bug fixing and ops in the last 7 days",
            value="\n".join(f"<@{user}> · {n} day(s)" for user, n in toil.items()),
            inline=False,
        )
    embed.set_footer(
        text="Remove roadblocks first. In your one-on-ones, ask: "
        '"What do you need?" Share thankless work evenly.'
    )
    return embed


HELP_COMMANDS = [
    ("For everyone", [
        ("/checkin", "Your end-of-day check-in: how the work went, your focus, "
         "what you worked on, and what you need from your lead. You also get a "
         "DM with a **Check in** button at reminder time."),
        ("/garden view", "Post the team's garden: one overall health score, team "
         "averages, and what to improve. It never shows anyone's answers."),
        ("/myflower", "Your own work and focus over the last 7 days. Only you see it."),
        ("/forgetme", "Delete all your check-ins in this garden."),
        ("/help", "Show this message."),
    ]),
    ("For the team lead", [
        ("/needs", "What each person asked for today, their blockers, and who "
         "carried the bug fixing and ops this week."),
    ]),
    ("For people with Manage Server", [
        ("/garden setup", "Plant a garden in this channel and choose the project, "
         "team lead, reminder time, and when flowers go unwatered."),
        ("/garden members", "Choose who gets check-in DMs (up to 25 people)."),
    ]),
]


def help_embed(garden: Garden | None) -> discord.Embed:
    """What the bot does and how to use it (ephemeral)."""
    embed = discord.Embed(
        title="🪴 team-garden help",
        description=(
            "End-of-day check-ins for software teams, based on \"How to Lead a "
            "Team\" from *Software Engineering at Google*. Your flower shows how "
            "your work is going. Together the flowers make the team's garden."
        ),
        color=GREEN,
    )
    if garden:
        embed.add_field(
            name="This channel",
            value=(
                f"The **{garden.project}** garden · team lead <@{garden.lead_id}> · "
                f"check-in DMs at **{garden.reminder}**, garden posted at "
                f"**{add_hour(garden.reminder)}**"
            ),
            inline=False,
        )
    else:
        embed.add_field(
            name="This channel",
            value="No garden here yet. Someone with **Manage Server** can run "
            "`/garden setup` in your team's private channel.",
            inline=False,
        )
    for heading, commands in HELP_COMMANDS:
        embed.add_field(
            name=heading,
            value="\n".join(f"`{name}` · {text}" for name, text in commands),
            inline=False,
        )
    embed.add_field(
        name="🔒 Who sees what",
        value=(
            "**Team:** only team-wide numbers, never your own answers. They "
            f"appear once {MIN_ANONYMOUS} people have checked in.\n"
            "**Only you:** your flower and your trend in `/myflower`.\n"
            "**Only you and the lead:** what you need and your blockers.\n"
            "**Only you, unless you share it:** your win or lesson."
        ),
        inline=False,
    )
    embed.set_footer(
        text="🌸 blooming · 🌷 healthy · 🥀 wilting · 🍂 needs care · 🌱 unwatered"
    )
    return embed
