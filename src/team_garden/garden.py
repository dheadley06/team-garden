"""Pure functions for flowers and garden health.

Nothing here talks to Discord or SQLite, so it is easy to test.
"""

import math
from collections import Counter
from dataclasses import dataclass
from datetime import date
from typing import Protocol

# "Track Happiness": how did today's engineering work go? (stored as mood)
MOODS = {
    1: "Stuck: no real progress",
    2: "Fighting it: slow and frustrating",
    3: "Steady progress",
    4: "Shipped something: PR merged or task closed",
    5: "In flow: a milestone landed",
}

# Focus and load, an early sign of burnout. (stored as energy)
ENERGIES = {
    1: "Overloaded: running on empty",
    2: "Spread thin: too many context switches",
    3: "Manageable load",
    4: "Good focus time",
    5: "Room to take on more",
}

# What the day's work was mostly spent on. Leads use it to share out the
# thankless tasks evenly, as the chapter recommends.
WORK = {
    "feature": "🛠️ Feature work",
    "bugs": "🐛 Bug fixing",
    "review": "👀 Code review",
    "design": "📐 Design or docs",
    "testing": "🧪 Tests",
    "ops": "🚒 Ops, on-call, or CI fixes",
    "learning": "📚 Learning or research",
    "meetings": "🗓️ Meetings and planning",
}
TOIL = {"bugs", "ops"}

# "The Unexpected Question": what do you need? Each option is something the
# chapter says a lead can give. Values are (label, description).
NEEDS = {
    "direction": (
        "Clearer direction",
        "Scope, priorities, or acceptance criteria for my task",
    ),
    "unblock": (
        "A roadblock removed",
        "Access, a decision, a dependency, an expert, or flaky CI",
    ),
    "review": ("A code or design review", "A second pair of eyes on a PR or design doc"),
    "mentoring": ("Mentoring or pairing", "Help learning a new tool, language, or codebase"),
    "motivation": ("More meaningful work", "Work that connects to the project's purpose"),
    "autonomy": ("More ownership", "Let me decide how to solve it"),
    "neither": ("Nothing, I'm good", "Keep doing what you're doing"),
}

UNWATERED = ("🌱", "unwatered")


def join_needs(values: list[str]) -> str:
    """Store several needs as one comma-separated value.

    "Nothing, I'm good" is dropped when it is picked alongside a real need.
    """
    picked = [v for v in NEEDS if v in values]
    if len(picked) > 1 and "neither" in picked:
        picked.remove("neither")
    if not picked:
        raise ValueError("Pick at least one need")
    return ",".join(picked)


def need_labels(need: str) -> list[str]:
    """Readable labels for a stored need value."""
    return [NEEDS[key][0] if key in NEEDS else key for key in need.split(",")]


def toil_counts(work_by_user: dict[int, list[str | None]]) -> dict[int, int]:
    """How many days each person spent mostly on thankless work, busiest first."""
    counts = {
        user: sum(1 for work in days if work in TOIL)
        for user, days in work_by_user.items()
    }
    return dict(sorted(
        ((user, n) for user, n in counts.items() if n),
        key=lambda item: -item[1],
    ))


@dataclass(frozen=True)
class Flower:
    """One person's latest state in a garden."""

    user_id: int
    score: float | None  # None means unwatered
    emoji: str
    label: str
    note: str | None = None


def flower_score(mood: int, energy: int) -> float:
    """Average mood and energy into a single 1-5 score."""
    for name, value in (("mood", mood), ("energy", energy)):
        if not 1 <= value <= 5:
            raise ValueError(f"{name} must be between 1 and 5, got {value}")
    return (mood + energy) / 2


def flower_for(score: float | None) -> tuple[str, str]:
    """Return the (emoji, label) for a flower score."""
    if score is None:
        return UNWATERED
    if score >= 4:
        return ("🌸", "blooming")
    if score >= 3:
        return ("🌷", "healthy")
    if score >= 2:
        return ("🥀", "wilting")
    return ("🍂", "needs care")


def is_stale(last_checkin: date | None, today: date, stale_days: int) -> bool:
    """A flower is unwatered once stale_days have passed with no check-in.

    With stale_days=1 only today's check-ins count; with 2, yesterday's
    still keep the flower watered, and so on.
    """
    if last_checkin is None:
        return True
    return (today - last_checkin).days >= stale_days


def make_flower(
    user_id: int,
    last_date: date | None,
    mood: int | None,
    energy: int | None,
    today: date,
    stale_days: int,
    note: str | None = None,
) -> Flower:
    """Build a Flower from someone's latest check-in."""
    if is_stale(last_date, today, stale_days) or mood is None or energy is None:
        emoji, label = UNWATERED
        return Flower(user_id, None, emoji, label)
    score = flower_score(mood, energy)
    emoji, label = flower_for(score)
    return Flower(user_id, score, emoji, label, note)


def garden_health(scores: list[float | None]) -> int:
    """Garden health from 0 to 100.

    The mean of the watered flowers (scaled from 1-5 to 0-100) is multiplied
    by the fraction of members who checked in recently. Silence is a warning
    sign too, so unwatered flowers pull the score down.
    """
    if not scores:
        return 0
    watered = [s for s in scores if s is not None]
    if not watered:
        return 0
    mean_scaled = sum((s - 1) / 4 * 100 for s in watered) / len(watered)
    fraction = len(watered) / len(scores)
    return round(mean_scaled * fraction)


def health_label(health: int) -> str:
    """Name the garden's health."""
    if health >= 80:
        return "Thriving"
    if health >= 60:
        return "Healthy"
    if health >= 40:
        return "Needs attention"
    return "Wilting"


def parse_reminder(text: str) -> str:
    """Check that a reminder time is HH:MM (24-hour) and normalize it."""
    try:
        hours, minutes = (int(part) for part in text.strip().split(":"))
    except ValueError:
        raise ValueError("Reminder must look like HH:MM, for example 17:30") from None
    if not (0 <= hours < 24 and 0 <= minutes < 60):
        raise ValueError("Reminder must be a real 24-hour time, like 17:30")
    return f"{hours:02d}:{minutes:02d}"


def add_hour(hhmm: str) -> str:
    """Return the HH:MM one hour later, wrapping past midnight."""
    hours, minutes = (int(part) for part in hhmm.split(":"))
    return f"{(hours + 1) % 24:02d}:{minutes:02d}"


# The garden view shows team-wide numbers only. Below this many check-ins,
# an average would give away how one person feels, so details stay hidden.
MIN_ANONYMOUS = 3


class CheckinLike(Protocol):
    mood: int
    energy: int
    need: str
    work: str | None


# What a lead can do when several people ask for the same thing, from the
# chapter's positive patterns.
NEED_ADVICE = {
    "direction": "📋 Several people want clearer direction. Write down the "
    "priorities and acceptance criteria so everyone pulls the same way. "
    "*(Set Clear Goals)*",
    "unblock": "🚧 Several people are hitting roadblocks. Look for the shared "
    "ones, like access, slow decisions, or flaky CI, and connect people with "
    "whoever knows the answer. *(Remove Roadblocks)*",
    "review": "👀 Several people are waiting on reviews. Set aside time for "
    "code and design reviews so PRs don't sit.",
    "mentoring": "🧑‍🏫 Several people want mentoring or pairing. Pair on "
    "unfamiliar code and let them drive. *(Be a Teacher and Mentor)*",
    "motivation": "🎯 Several people want more meaningful work. Show who the "
    "work helps and pass along user feedback. *(Purpose)*",
    "autonomy": "🗝️ Several people want more ownership. Agree on what needs "
    "to be done and let them choose how. *(Autonomy)*",
}


def garden_insights(watered: list[CheckinLike], total: int) -> list[str]:
    """Up to four team-wide things to improve, most important first.

    Every tip is about the whole team, never one person.
    """
    tips = []
    if total and len(watered) / total < 0.6:
        tips.append(
            f"🌱 Only {len(watered)} of {total} people checked in recently. "
            "Silence is a warning sign too, so check in with the quiet ones. "
            "*(Track Happiness)*"
        )
    if len(watered) < MIN_ANONYMOUS:
        return tips
    n = len(watered)

    strained = sum(1 for c in watered if c.energy <= 2) / n
    if strained >= 1 / 3:
        tips.append(
            f"🔋 {strained:.0%} of the team is overloaded or spread thin. Cut "
            "meetings, protect focus time, and rebalance work before it turns "
            "into burnout."
        )
    avg_work = sum(c.mood for c in watered) / n
    if avg_work < 3:
        tips.append(
            f"🐌 Work is getting stuck (averaging {avg_work:.1f}/5). Look for "
            "what slows everyone down: unclear specs, slow reviews, or a "
            "flaky build."
        )
    toil = sum(1 for c in watered if c.work in TOIL) / n
    if toil >= 0.4:
        tips.append(
            f"🧹 {toil:.0%} of the team spent the day on bug fixing or ops. "
            "Share the thankless work evenly and fix the root causes."
        )
    asked = Counter(
        key for c in watered for key in c.need.split(",") if key in NEED_ADVICE
    )
    threshold = max(2, math.ceil(n / 3))
    tips += [NEED_ADVICE[key] for key, count in asked.most_common() if count >= threshold]
    meetings = sum(1 for c in watered if c.work == "meetings") / n
    if meetings >= 0.4:
        tips.append(
            f"🗓️ {meetings:.0%} of the team spent the day in meetings. "
            "Guard blocks of focus time for building."
        )
    return tips[:4]


def work_mix(watered: list[CheckinLike], top: int = 3) -> list[tuple[str, float]]:
    """The most common kinds of work, as (WORK key, share of the team)."""
    counts = Counter(c.work for c in watered if c.work in WORK)
    return [(key, n / len(watered)) for key, n in counts.most_common(top)]


# The garden shown at the top of /garden view. It is the same every time, so
# it never hints at how anyone is doing. Flowers by Joan G. Stark (jgs),
# trimmed to the first four flowers so it fits in a Discord embed, even on a
# phone, without wrapping.
GARDEN_ART = r"""
                    _
                  _(_)_
      @@@@       (_)@(_)   vVVVv
     @@()@@ wWWWw  (_)\    (___)
      @@@@  (___)     `|/    Y
       /      Y       \|    \|/
    \ |     \ |/       | / \ | /
jgs \\|//   \\|///  \\\|//\\\|///
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
""".strip("\n")
GARDEN_ART_WIDTH = 33
