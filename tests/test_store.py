import sqlite3
from datetime import date

import pytest

from team_garden.store import Checkin, Garden, Store

CHANNEL = 100
OTHER_CHANNEL = 200


@pytest.fixture
def store():
    store = Store(":memory:")
    for channel in (CHANNEL, OTHER_CHANNEL):
        store.save_garden(Garden(channel, 1, f"proj{channel}", 9, "17:00", 2))
    yield store
    store.close()


def checkin(user, day, mood=3, energy=3, need="neither", channel=CHANNEL, **kw):
    return Checkin(channel, user, date(2026, 10, day), mood, energy, need, **kw)


def test_garden_round_trip(store):
    garden = Garden(300, 1, "team-garden", 9, "18:30", 3)
    store.save_garden(garden)
    assert store.get_garden(300) == garden
    assert store.get_garden(999) is None


def test_setup_again_updates_garden(store):
    store.save_garden(Garden(CHANNEL, 1, "renamed", 9, "09:00", 1))
    assert store.get_garden(CHANNEL).project == "renamed"
    assert len(store.all_gardens()) == 2


def test_checkin_round_trip(store):
    original = checkin(1, 19, 4, 2, "direction", blocker="CI", note="hi", share_note=True)
    store.add_checkin(original)
    assert store.latest_checkins(CHANNEL) == [original]


def test_latest_checkins_one_per_user(store):
    store.add_checkin(checkin(1, 18, mood=1))
    store.add_checkin(checkin(1, 19, mood=2))
    store.add_checkin(checkin(1, 19, mood=5))  # changed their mind today
    store.add_checkin(checkin(2, 17))
    store.add_checkin(checkin(3, 19, channel=OTHER_CHANNEL))
    latest = store.latest_checkins(CHANNEL)
    assert [(c.user_id, c.mood) for c in latest] == [(1, 5), (2, 3)]


def test_history_one_per_day_since(store):
    for day, mood in [(10, 1), (14, 2), (15, 3), (15, 4), (19, 5)]:
        store.add_checkin(checkin(1, day, mood=mood))
    history = store.history(CHANNEL, 1, date(2026, 10, 13))
    assert [(c.date.day, c.mood) for c in history] == [(14, 2), (15, 4), (19, 5)]


def test_needs_only_today_and_only_asks(store):
    store.add_checkin(checkin(1, 19, need="motivation"))
    store.add_checkin(checkin(2, 19, need="neither"))
    store.add_checkin(checkin(3, 19, need="neither", blocker="waiting on review"))
    store.add_checkin(checkin(4, 18, need="direction"))
    store.add_checkin(checkin(5, 19, need="both"))
    store.add_checkin(checkin(5, 19, need="neither"))  # latest says fine now
    needs = store.needs_on(CHANNEL, date(2026, 10, 19))
    assert [c.user_id for c in needs] == [1, 3]


def test_forget_deletes_only_that_user_in_that_garden(store):
    store.add_checkin(checkin(1, 18))
    store.add_checkin(checkin(1, 19))
    store.add_checkin(checkin(2, 19))
    store.add_checkin(checkin(1, 19, channel=OTHER_CHANNEL))
    assert store.forget(CHANNEL, 1) == 2
    assert [c.user_id for c in store.latest_checkins(CHANNEL)] == [2]
    assert [c.user_id for c in store.latest_checkins(OTHER_CHANNEL)] == [1]


def test_members_replace_and_stay_per_garden(store):
    assert store.members(CHANNEL) == []
    store.set_members(CHANNEL, [3, 1, 1])
    store.set_members(OTHER_CHANNEL, [7])
    assert store.members(CHANNEL) == [1, 3]
    store.set_members(CHANNEL, [2])
    assert store.members(CHANNEL) == [2]
    assert store.members(OTHER_CHANNEL) == [7]


def test_old_lead_role_column_is_renamed(tmp_path):
    path = str(tmp_path / "old.db")
    old = sqlite3.connect(path)
    old.execute(
        "CREATE TABLE gardens (channel_id INTEGER PRIMARY KEY, guild_id INTEGER, "
        "project TEXT, lead_role_id INTEGER, reminder TEXT, stale_days INTEGER)"
    )
    old.execute("INSERT INTO gardens VALUES (5, 1, 'old', 42, '17:00', 2)")
    old.commit()
    old.close()
    store = Store(path)
    assert store.get_garden(5).lead_id == 42
    store.close()


def test_work_round_trips_and_recent_has_one_per_user_per_day(store):
    store.add_checkin(checkin(1, 18, work="bugs"))
    store.add_checkin(checkin(1, 19, work="feature"))
    store.add_checkin(checkin(1, 19, work="ops"))
    store.add_checkin(checkin(2, 12, work="ops"))
    recent = store.recent(CHANNEL, date(2026, 10, 13))
    assert [(c.user_id, c.date.day, c.work) for c in recent] == [(1, 18, "bugs"), (1, 19, "ops")]


def test_old_checkins_table_gets_work_column(tmp_path):
    path = str(tmp_path / "old.db")
    old = sqlite3.connect(path)
    old.execute(
        "CREATE TABLE checkins (id INTEGER PRIMARY KEY AUTOINCREMENT, channel_id INTEGER, "
        "user_id INTEGER, date TEXT, mood INTEGER, energy INTEGER, need TEXT, "
        "blocker TEXT, note TEXT, share_note INTEGER NOT NULL DEFAULT 0)"
    )
    old.execute("INSERT INTO checkins VALUES (1, 5, 7, '2026-10-19', 3, 3, 'both', NULL, NULL, 0)")
    old.commit()
    old.close()
    store = Store(path)
    assert store.latest_checkins(5)[0].work is None
    store.close()
