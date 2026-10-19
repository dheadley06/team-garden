# 🪴 team-garden

A Discord bot for end-of-day check-ins on a software team. Each engineer
tends a **flower** by answering four questions: how today's engineering work
went, how their focus and workload are, what they mainly worked on, and what
they need from their lead. All the flowers together make the team's
**garden**, which gets a health score.

## Why

It's built on three ideas from
[*Software Engineering at Google*, "How to Lead a Team"](https://abseil.io/resources/swe-book/html/ch05.html):

- **People Are Like Plants.** Some engineers need more direction (clear scope
  and priorities), and some need more motivation (meaningful work, ownership,
  room to learn). The check-in asks which one you need today.
- **The Unexpected Question.** "What do you need?" The answers are things the
  chapter says a lead can give: clearer direction, a roadblock removed (access,
  a decision, an expert, flaky CI), a code or design review, mentoring or
  pairing, more meaningful work, or more ownership. The lead sees them with
  `/needs`, which is a starting point for one-on-ones.
- **Track Happiness.** The garden's health falls when the work is going badly
  or people are overloaded, *and* when people stop checking in, because
  silence is a warning sign too. `/needs` also shows who has spent the most
  days on bug fixing and ops this week, so the lead can share thankless work
  evenly.

## Privacy

- **Team-only garden.** Each garden belongs to one channel. Make that channel
  private to your team, and the bot only posts summaries there.
- **Private check-ins by DM.** At reminder time the bot DMs each team member a
  **Check in** button, so check-ins happen in a private conversation with the
  bot. `/checkin`, `/myflower`, `/needs`, and `/forgetme` also work in the
  garden channel, where they reply *ephemerally* (only you see the reply).
- **Three levels of visibility.**
  - The team sees only team-wide numbers: one health score, averages, where
    the time went, and things to improve. Averages appear once 3 people have
    checked in, so no one's answers can be picked out.
  - Your own flower and trend are seen only by you (`/myflower`).
  - What you need and your blockers are seen only by you and the team lead.
  - Your win or lesson is private unless you turn on **Share update with team**.
- **No data on GitHub.** Check-ins live in a local SQLite file (`garden.db`) on
  the bot's host. `.env` and `*.db` are git-ignored.
- **`/forgetme`** deletes all of your check-ins in that garden.

## Commands

| Command | Who | What it does |
|---|---|---|
| `/garden setup` | Manage Server | Plant a garden in the current channel (`project`, `lead`, `reminder` HH:MM, `stale_days`), then pick the team members |
| `/garden members` | Manage Server | Change who is on the team (up to 25 people) |
| `/checkin` | team | Answer the four questions, add blockers and a win or lesson, and submit |
| `/garden view` | team | Post the team's overall health, an ASCII garden, team averages, and what to improve. Never shows anyone's answers |
| `/myflower` | you | How your work and focus went over the last 7 days |
| `/needs` | team lead | What each person asked for today, their blockers, and who carried the bug fixing and ops this week |
| `/forgetme` | you | Delete your check-ins in this garden |
| `/help` | anyone | How the bot works, every command, who sees what, and this channel's garden. Works in DMs too |

Every day at the garden's `reminder` time the bot DMs each team member a
**Check in** button. If it can't DM someone, it mentions them in the garden
channel and asks them to allow DMs. One hour later it posts the garden.
Times use the bot host's local time zone.

### The check-in

| Question | Answers |
|---|---|
| How did today's engineering work go? | 1 Stuck · 2 Fighting it · 3 Steady progress · 4 Shipped something · 5 In flow |
| How are your focus and workload? | 1 Overloaded · 2 Spread thin · 3 Manageable · 4 Good focus time · 5 Room for more |
| What did you mainly work on? | Feature work, bug fixing, code review, design or docs, tests, ops/on-call/CI fixes, learning, meetings |
| What do you need from your lead? (pick any) | Clearer direction, a roadblock removed, a code or design review, mentoring or pairing, more meaningful work, more ownership, or nothing |
| Blockers & updates (optional) | What's blocking you (lead only), and a win or lesson (shared only if you choose) |

### Flowers and health

A flower's score is the average of the first two answers (1–5) from the
person's latest check-in. Only you see your own flower.

| Flower | Score |
|---|---|
| 🌸 blooming | ≥ 4 |
| 🌷 healthy | ≥ 3 |
| 🥀 wilting | ≥ 2 |
| 🍂 needs care | < 2 |
| 🌱 unwatered | no check-in for `stale_days` days |

**Garden health (0–100)** = the average watered score (scaled to 0–100) × the
fraction of members who checked in recently. Thriving ≥ 80, Healthy ≥ 60, Needs
attention ≥ 40, Wilting < 40. Members are the people picked with
`/garden members`, so people who don't check in pull the score down.

### The garden view

`/garden view` (and the daily summary) shows the team as a whole, with the
same ASCII garden at the bottom every time (flowers by Joan G. Stark, trimmed to 33
characters so the embed doesn't wrap them, even on a phone):

```text
                    _
                  _(_)_
      @@@@       (_)@(_)   vVVVv
     @@()@@ wWWWw  (_)\    (___)
      @@@@  (___)     `|/    Y
       /      Y       \|    \|/
    \ |     \ |/       | / \ | /
jgs \\|//   \\|///  \\\|//\\\|///
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
```

- **Health** and **Checked in** (for example "3 of 4").
- **Team averages** for how the work is going and for focus and load, plus
  **where the time went** (for example "🛠️ Feature work 50%").
- **What to improve**: up to four team-wide tips taken from the chapter. Tips
  appear when check-ins are low, when a third or more of the team is
  overloaded, when work is stuck, when 40% or more is bug fixing or ops, when
  several people ask for the same thing (such as clearer direction or
  reviews), or when meetings eat the day.
- **Shared wins** that people chose to share.

With fewer than 3 check-ins, only the art, the check-in count, and the
low-participation tip are shown. `MIN_ANONYMOUS` in `garden.py` sets that
limit.

## Setup

### 1. Create the bot in Discord

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications)
   and click **New Application**. Name it `team-garden`.
2. Open **Bot**, click **Reset Token**, and copy the token. Keep it secret.
   No privileged intents are needed, so leave them all off.
3. Open **OAuth2 → URL Generator**. Check the scopes **`bot`** and
   **`applications.commands`**. Under bot permissions check **View Channels**,
   **Send Messages**, and **Embed Links**.
4. Open the generated URL and add the bot to your server.

### 2. Run it

You need [uv](https://docs.astral.sh/uv/).

```bash
cp .env.example .env     # then paste your token after DISCORD_TOKEN=
uv sync
uv run team-garden
```

Global slash commands can take a few minutes to appear the first time. While
testing, set `DISCORD_GUILD_ID` in `.env` to your server's ID (turn on
Developer Mode in Discord, then right-click the server → **Copy Server ID**)
and they appear right away.

The bot must keep running for reminders to post, so host it on a machine that
stays on.

### 3. Plant a garden for a project

1. Create a channel such as `#garden-myproject`.
2. In the channel settings, turn on **Private Channel** and add your team role
   (for example `@myproject-team`) and the bot.
3. In that channel, run
   `/garden setup project:myproject lead:@your-lead reminder:17:00 stale_days:2`.
4. Pick your teammates in the menu that appears. Only you see it.
5. Ask each teammate to keep **Allow DMs from server members** on for the
   server (right-click the server → **Privacy Settings**), or the bot can't
   reach them.

One bot can run many gardens: one per channel.

## Development

```bash
uv run pytest
```

- `src/team_garden/garden.py`: pure functions for flowers, health, and staleness
- `src/team_garden/store.py`: SQLite storage
- `src/team_garden/render.py`: Discord embeds
- `src/team_garden/views.py`: the `/checkin` form
- `src/team_garden/bot.py`: slash commands and the daily loop
