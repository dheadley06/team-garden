"""SQLite storage for gardens and check-ins.

The database lives on the bot's host (garden.db by default) and is git-ignored,
so no one's feelings ever end up in a repository.
"""

import sqlite3
from dataclasses import dataclass
from datetime import date

SCHEMA = """
CREATE TABLE IF NOT EXISTS gardens (
    channel_id   INTEGER PRIMARY KEY,
    guild_id     INTEGER NOT NULL,
    project      TEXT    NOT NULL,
    lead_id      INTEGER NOT NULL,
    reminder     TEXT    NOT NULL,
    stale_days   INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS checkins (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id INTEGER NOT NULL REFERENCES gardens(channel_id) ON DELETE CASCADE,
    user_id    INTEGER NOT NULL,
    date       TEXT    NOT NULL,
    mood       INTEGER NOT NULL,
    energy     INTEGER NOT NULL,
    need       TEXT    NOT NULL,
    blocker    TEXT,
    note       TEXT,
    share_note INTEGER NOT NULL DEFAULT 0,
    work       TEXT
);
CREATE TABLE IF NOT EXISTS members (
    channel_id INTEGER NOT NULL REFERENCES gardens(channel_id) ON DELETE CASCADE,
    user_id    INTEGER NOT NULL,
    PRIMARY KEY (channel_id, user_id)
);
CREATE INDEX IF NOT EXISTS checkins_by_user ON checkins(channel_id, user_id, date);
"""


@dataclass(frozen=True)
class Garden:
    channel_id: int
    guild_id: int
    project: str
    lead_id: int  # the team lead's user ID
    reminder: str
    stale_days: int


@dataclass(frozen=True)
class Checkin:
    channel_id: int
    user_id: int
    date: date
    mood: int
    energy: int
    need: str
    blocker: str | None = None
    note: str | None = None
    share_note: bool = False
    work: str | None = None  # a key of garden.WORK


class Store:
    def __init__(self, path: str = "garden.db") -> None:
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._migrate()
        self.conn.executescript(SCHEMA)

    def _migrate(self) -> None:
        """Upgrade databases made by older versions of the bot."""
        if "lead_role_id" in self._columns("gardens"):
            with self.conn:
                self.conn.execute(
                    "ALTER TABLE gardens RENAME COLUMN lead_role_id TO lead_id"
                )
        checkin_columns = self._columns("checkins")
        if checkin_columns and "work" not in checkin_columns:
            with self.conn:
                self.conn.execute("ALTER TABLE checkins ADD COLUMN work TEXT")

    def _columns(self, table: str) -> set[str]:
        return {row["name"] for row in self.conn.execute(f"PRAGMA table_info({table})")}

    def close(self) -> None:
        self.conn.close()

    # Gardens

    def save_garden(self, garden: Garden) -> None:
        """Create or replace the garden linked to a channel."""
        with self.conn:
            self.conn.execute(
                "INSERT INTO gardens VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(channel_id) DO UPDATE SET guild_id=excluded.guild_id, "
                "project=excluded.project, lead_id=excluded.lead_id, "
                "reminder=excluded.reminder, "
                "stale_days=excluded.stale_days",
                (
                    garden.channel_id,
                    garden.guild_id,
                    garden.project,
                    garden.lead_id,
                    garden.reminder,
                    garden.stale_days,
                ),
            )

    def get_garden(self, channel_id: int) -> Garden | None:
        row = self.conn.execute(
            "SELECT * FROM gardens WHERE channel_id = ?", (channel_id,)
        ).fetchone()
        return Garden(**row) if row else None

    def all_gardens(self) -> list[Garden]:
        return [Garden(**row) for row in self.conn.execute("SELECT * FROM gardens")]

    # Members

    def set_members(self, channel_id: int, user_ids: list[int]) -> None:
        """Replace the list of teammates the bot DMs for check-ins."""
        with self.conn:
            self.conn.execute("DELETE FROM members WHERE channel_id = ?", (channel_id,))
            self.conn.executemany(
                "INSERT OR IGNORE INTO members VALUES (?, ?)",
                [(channel_id, user_id) for user_id in user_ids],
            )

    def members(self, channel_id: int) -> list[int]:
        rows = self.conn.execute(
            "SELECT user_id FROM members WHERE channel_id = ? ORDER BY user_id",
            (channel_id,),
        )
        return [row["user_id"] for row in rows]

    # Check-ins

    def add_checkin(self, checkin: Checkin) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO checkins (channel_id, user_id, date, mood, energy, "
                "need, blocker, note, share_note, work) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    checkin.channel_id,
                    checkin.user_id,
                    checkin.date.isoformat(),
                    checkin.mood,
                    checkin.energy,
                    checkin.need,
                    checkin.blocker,
                    checkin.note,
                    int(checkin.share_note),
                    checkin.work,
                ),
            )

    def latest_checkins(self, channel_id: int) -> list[Checkin]:
        """Each person's most recent check-in in a garden."""
        rows = self.conn.execute(
            "SELECT * FROM checkins WHERE id IN "
            "(SELECT MAX(id) FROM checkins WHERE channel_id = ? GROUP BY user_id) "
            "ORDER BY user_id",
            (channel_id,),
        )
        return [_to_checkin(row) for row in rows]

    def history(self, channel_id: int, user_id: int, since: date) -> list[Checkin]:
        """One user's latest check-in for each day since a date, oldest first."""
        rows = self.conn.execute(
            "SELECT * FROM checkins WHERE id IN "
            "(SELECT MAX(id) FROM checkins WHERE channel_id = ? AND user_id = ? "
            "AND date >= ? GROUP BY date) ORDER BY date",
            (channel_id, user_id, since.isoformat()),
        )
        return [_to_checkin(row) for row in rows]

    def recent(self, channel_id: int, since: date) -> list[Checkin]:
        """Everyone's latest check-in for each day since a date."""
        rows = self.conn.execute(
            "SELECT * FROM checkins WHERE id IN "
            "(SELECT MAX(id) FROM checkins WHERE channel_id = ? AND date >= ? "
            "GROUP BY user_id, date) ORDER BY user_id, date",
            (channel_id, since.isoformat()),
        )
        return [_to_checkin(row) for row in rows]

    def needs_on(self, channel_id: int, day: date) -> list[Checkin]:
        """Latest check-ins on a day that asked the lead for something,
        or that mention a blocker."""
        rows = self.conn.execute(
            "SELECT * FROM checkins WHERE id IN "
            "(SELECT MAX(id) FROM checkins WHERE channel_id = ? AND date = ? "
            "GROUP BY user_id) "
            "AND (need != 'neither' OR COALESCE(blocker, '') != '') ORDER BY user_id",
            (channel_id, day.isoformat()),
        )
        return [_to_checkin(row) for row in rows]

    def forget(self, channel_id: int, user_id: int) -> int:
        """Delete every check-in a user made in a garden. Returns how many."""
        with self.conn:
            cursor = self.conn.execute(
                "DELETE FROM checkins WHERE channel_id = ? AND user_id = ?",
                (channel_id, user_id),
            )
        return cursor.rowcount


def _to_checkin(row: sqlite3.Row) -> Checkin:
    return Checkin(
        channel_id=row["channel_id"],
        user_id=row["user_id"],
        date=date.fromisoformat(row["date"]),
        mood=row["mood"],
        energy=row["energy"],
        need=row["need"],
        blocker=row["blocker"],
        note=row["note"],
        share_note=bool(row["share_note"]),
        work=row["work"],
    )
