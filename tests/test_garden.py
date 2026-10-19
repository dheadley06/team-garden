from datetime import date
from types import SimpleNamespace

import pytest

from team_garden.garden import (
    GARDEN_ART,
    GARDEN_ART_WIDTH,
    add_hour,
    flower_for,
    flower_score,
    garden_health,
    garden_insights,
    health_label,
    is_stale,
    join_needs,
    make_flower,
    need_labels,
    parse_reminder,
    toil_counts,
    work_mix,
)

TODAY = date(2026, 10, 19)


def test_flower_score_averages_mood_and_energy():
    assert flower_score(5, 3) == 4
    assert flower_score(1, 2) == 1.5


@pytest.mark.parametrize("mood, energy", [(0, 3), (3, 6)])
def test_flower_score_rejects_out_of_range(mood, energy):
    with pytest.raises(ValueError):
        flower_score(mood, energy)


@pytest.mark.parametrize(
    "score, label",
    [
        (5, "blooming"),
        (4, "blooming"),
        (3.5, "healthy"),
        (3, "healthy"),
        (2.5, "wilting"),
        (2, "wilting"),
        (1.5, "needs care"),
        (None, "unwatered"),
    ],
)
def test_flower_for_thresholds(score, label):
    assert flower_for(score)[1] == label


def test_is_stale():
    assert is_stale(None, TODAY, 2)
    assert not is_stale(TODAY, TODAY, 1)
    assert is_stale(date(2026, 10, 18), TODAY, 1)
    assert not is_stale(date(2026, 10, 18), TODAY, 2)
    assert is_stale(date(2026, 10, 17), TODAY, 2)


def test_make_flower_unwatered_when_stale():
    flower = make_flower(1, date(2026, 10, 10), 5, 5, TODAY, 2, note="hi")
    assert flower.score is None
    assert flower.emoji == "🌱"
    assert flower.note is None


def test_make_flower_watered():
    flower = make_flower(1, TODAY, 4, 5, TODAY, 2, note="shipped it")
    assert flower.score == 4.5
    assert flower.label == "blooming"
    assert flower.note == "shipped it"


def test_health_empty_and_all_unwatered():
    assert garden_health([]) == 0
    assert garden_health([None, None]) == 0


def test_health_all_perfect():
    assert garden_health([5, 5, 5]) == 100


def test_health_scales_one_to_five():
    assert garden_health([1]) == 0
    assert garden_health([3]) == 50


def test_unwatered_flowers_pull_health_down():
    # Two perfect flowers but half the team is silent.
    assert garden_health([5, 5, None, None]) == 50
    assert garden_health([5, 5]) > garden_health([5, 5, None])


@pytest.mark.parametrize(
    "health, label",
    [
        (100, "Thriving"),
        (80, "Thriving"),
        (79, "Healthy"),
        (60, "Healthy"),
        (59, "Needs attention"),
        (40, "Needs attention"),
        (39, "Wilting"),
        (0, "Wilting"),
    ],
)
def test_health_label(health, label):
    assert health_label(health) == label


def test_parse_reminder():
    assert parse_reminder("9:05") == "09:05"
    assert parse_reminder(" 17:30 ") == "17:30"
    for bad in ("24:00", "12:60", "noon", "1730"):
        with pytest.raises(ValueError):
            parse_reminder(bad)


def test_add_hour_wraps_midnight():
    assert add_hour("17:30") == "18:30"
    assert add_hour("23:15") == "00:15"


def test_join_needs_keeps_order_and_drops_neither_alongside_real_needs():
    assert join_needs(["review", "direction"]) == "direction,review"
    assert join_needs(["neither", "unblock"]) == "unblock"
    assert join_needs(["neither"]) == "neither"
    with pytest.raises(ValueError):
        join_needs([])


def test_need_labels_reads_old_and_new_values():
    assert need_labels("direction,unblock") == ["Clearer direction", "A roadblock removed"]
    assert need_labels("both") == ["both"]


def test_toil_counts_only_bugs_and_ops_busiest_first():
    work = {1: ["bugs", "ops", "feature"], 2: ["feature", None], 3: ["ops"]}
    assert toil_counts(work) == {1: 2, 3: 1}


def _c(mood=4, energy=4, need="neither", work="feature"):
    return SimpleNamespace(mood=mood, energy=energy, need=need, work=work)


def test_insights_flag_low_participation_even_when_hidden():
    tips = garden_insights([_c()], total=4)
    assert len(tips) == 1 and "Only 1 of 4" in tips[0]


def test_insights_quiet_for_a_healthy_team():
    assert garden_insights([_c(), _c(), _c()], total=3) == []


def test_insights_spot_strain_stuck_work_and_toil():
    team = [_c(2, 1, work="ops"), _c(2, 2, work="bugs"), _c(2, 4, work="feature")]
    tips = " ".join(garden_insights(team, total=3))
    assert "overloaded" in tips
    assert "stuck" in tips
    assert "bug fixing or ops" in tips


def test_insights_need_several_people_asking():
    one = [_c(need="review"), _c(), _c()]
    two = [_c(need="review"), _c(need="direction,review"), _c()]
    assert not any("reviews" in t for t in garden_insights(one, total=3))
    assert any("reviews" in t for t in garden_insights(two, total=3))


def test_insights_capped_at_four():
    team = [_c(1, 1, "direction,unblock,review", "meetings") for _ in range(3)]
    assert len(garden_insights(team, total=6)) == 4


def test_work_mix_shares():
    assert work_mix([_c(work="bugs"), _c(work="bugs"), _c(work="review"), _c(work=None)]) == [
        ("bugs", 0.5),
        ("review", 0.25),
    ]



def test_garden_art_fits_a_discord_embed():
    lines = GARDEN_ART.splitlines()
    assert max(len(line) for line in lines) == GARDEN_ART_WIDTH
    assert lines[-1] == "^" * GARDEN_ART_WIDTH
