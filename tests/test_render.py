from datetime import date

from team_garden.render import garden_embed, help_embed, needs_embed
from team_garden.store import Checkin, Garden

TODAY = date(2026, 10, 19)
GARDEN = Garden(100, 1, "demo", 9, "17:00", 2)


def _checkin(user, mood=4, energy=4, need="neither", **kw):
    return Checkin(100, user, TODAY, mood, energy, need, **kw)


def _text(embed):
    return (embed.description or "") + "".join(f.name + f.value for f in embed.fields)


def _fields(embed):
    return {f.name: f.value for f in embed.fields}


def test_garden_never_names_anyone_or_shows_their_answers():
    latest = [
        _checkin(1, 1, 1, "direction", blocker="stuck on CI", work="bugs"),
        _checkin(2, 5, 5, "review", work="feature"),
        _checkin(3, 3, 3, "neither", note="private lesson"),
    ]
    text = _text(garden_embed(GARDEN, latest, TODAY, members=[1, 2, 3]))
    for secret in ("<@1>", "<@2>", "<@3>", "stuck on CI", "private lesson"):
        assert secret not in text


def test_health_hidden_until_enough_people_check_in():
    latest = [_checkin(1), _checkin(2)]
    fields = _fields(garden_embed(GARDEN, latest, TODAY, members=[1, 2, 3, 4]))
    assert "/100" not in fields["Health"]
    assert "Team averages" not in fields
    assert fields["Checked in"] == "2 of 4"


def test_health_and_averages_with_enough_check_ins():
    latest = [_checkin(1, 5, 5), _checkin(2, 5, 5), _checkin(3, 5, 5)]
    fields = _fields(garden_embed(GARDEN, latest, TODAY, members=[1, 2, 3, 4]))
    assert "75/100" in fields["Health"]
    assert "5.0/5" in fields["Team averages"]
    assert "Only 3 of 4" not in fields.get("🔧 What to improve", "")


def test_stale_check_ins_and_non_members_do_not_count():
    old = Checkin(100, 1, date(2026, 10, 1), 5, 5, "neither")
    latest = [old, _checkin(2), _checkin(9)]
    fields = _fields(garden_embed(GARDEN, latest, TODAY, members=[1, 2]))
    assert fields["Checked in"] == "1 of 2"


def test_without_members_everyone_who_checked_in_counts():
    latest = [_checkin(1), _checkin(2), _checkin(3)]
    fields = _fields(garden_embed(GARDEN, latest, TODAY, members=[]))
    assert fields["Checked in"] == "3 of 3"


def test_garden_shows_ascii_art_and_where_time_went():
    latest = [_checkin(u, work="review") for u in (1, 2, 3)]
    embed = garden_embed(GARDEN, latest, TODAY, members=[1, 2, 3])
    assert embed.fields[-1].value.startswith("```")
    assert "Code review 100%" in _fields(embed)["Where the time went"]


def test_shared_wins_appear_only_when_shared():
    latest = [
        _checkin(1, note="merged the refactor", share_note=True),
        _checkin(2, note="kept to myself"),
        _checkin(3),
    ]
    text = _text(garden_embed(GARDEN, latest, TODAY, members=[1, 2, 3]))
    assert "merged the refactor" in text
    assert "kept to myself" not in text


def test_needs_embed_lists_needs_and_toil():
    today_needs = [_checkin(1, 2, 2, "direction,unblock", blocker="flaky CI")]
    week = [_checkin(2, 3, 3, work="ops")]
    embed = needs_embed(today_needs, TODAY, week)
    assert "Clearer direction, A roadblock removed" in embed.description
    assert "flaky CI" in embed.description
    assert "<@2> · 1 day(s)" in embed.fields[0].value


def test_help_lists_every_command_and_this_garden():
    embed = help_embed(GARDEN)
    text = "".join(f.value for f in embed.fields)
    for command in ("/checkin", "/garden view", "/myflower", "/forgetme", "/help",
                    "/needs", "/garden setup", "/garden members"):
        assert f"`{command}`" in text
    assert "**demo** garden" in embed.fields[0].value
    assert "No garden here yet" in help_embed(None).fields[0].value


def test_garden_art_is_the_same_whatever_the_health():
    from team_garden.garden import GARDEN_ART

    thriving = garden_embed(GARDEN, [_checkin(u, 5, 5) for u in (1, 2, 3)], TODAY, [1, 2, 3])
    wilting = garden_embed(GARDEN, [_checkin(u, 1, 1) for u in (1, 2, 3)], TODAY, [1, 2, 3])
    empty = garden_embed(GARDEN, [], TODAY, [])
    for embed in (thriving, wilting, empty):
        # Always the last thing in the message.
        assert embed.fields[-1].value == f"```\n{GARDEN_ART}\n```"
        assert GARDEN_ART not in (embed.description or "")
