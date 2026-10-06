"""Specification for cwc27.ratings.elo. Written before the implementation (TDD)."""

from datetime import date

import pytest

from cwc27.models import Match, ResultType
from cwc27.ratings.elo import (
    EloConfig,
    actual_score,
    expected_score,
    initial_rating,
    run_elo,
    update,
)

CONFIG = EloConfig(k=30.0, home_advantage=60.0)


def make_match(
    team_a="India",
    team_b="Australia",
    winner="India",
    result_type=ResultType.NORMAL,
    day=date(2024, 1, 1),
    match_id="m1",
):
    return Match(
        match_id=match_id,
        date=day,
        team_a=team_a,
        team_b=team_b,
        venue=None,
        city=None,
        toss_winner=None,
        toss_decision=None,
        winner=winner,
        result_type=result_type,
        margin_runs=None,
        margin_wickets=None,
        event=None,
        source="test",
    )


# --- initial_rating ---------------------------------------------------------


def test_full_member_starts_at_full_member_rating():
    assert initial_rating("India", CONFIG) == 1500.0


def test_associate_starts_lower():
    assert initial_rating("Namibia", CONFIG) == 1300.0


# --- expected_score ---------------------------------------------------------


def test_equal_ratings_give_even_chance():
    assert expected_score(1500, 1500) == pytest.approx(0.5)


def test_400_point_gap_gives_ten_to_one():
    assert expected_score(1900, 1500) == pytest.approx(10 / 11)


def test_expected_scores_of_both_sides_sum_to_one():
    assert expected_score(1620, 1480) + expected_score(1480, 1620) == pytest.approx(1.0)


def test_scale_changes_how_decisive_a_gap_is():
    assert expected_score(1600, 1500, scale=200) == pytest.approx(1 / (1 + 10**-0.5))


# --- actual_score -----------------------------------------------------------


def test_winner_scores_one_and_loser_zero():
    m = make_match(winner="India")

    assert actual_score(m, "India") == 1.0
    assert actual_score(m, "Australia") == 0.0


def test_dls_win_counts_as_a_win():
    m = make_match(winner="Australia", result_type=ResultType.DLS)

    assert actual_score(m, "Australia") == 1.0


def test_tie_scores_half_each():
    m = make_match(winner=None, result_type=ResultType.TIE)

    assert actual_score(m, "India") == 0.5
    assert actual_score(m, "Australia") == 0.5


def test_no_result_scores_none():
    m = make_match(winner=None, result_type=ResultType.NO_RESULT)

    assert actual_score(m, "India") is None


def test_actual_score_rejects_team_not_in_match():
    with pytest.raises(ValueError):
        actual_score(make_match(), "England")


# --- update -----------------------------------------------------------------


def test_win_between_equals_moves_each_side_half_of_k():
    ratings = {"India": 1500.0, "Australia": 1500.0}

    new = update(ratings, make_match(winner="India"), CONFIG)

    assert new["India"] == pytest.approx(1515.0)
    assert new["Australia"] == pytest.approx(1485.0)


def test_update_is_zero_sum():
    ratings = {"India": 1580.0, "Australia": 1530.0}

    new = update(ratings, make_match(winner="Australia"), CONFIG)

    assert new["India"] + new["Australia"] == pytest.approx(1580.0 + 1530.0)


def test_update_does_not_modify_input():
    ratings = {"India": 1500.0, "Australia": 1500.0}

    update(ratings, make_match(), CONFIG)

    assert ratings == {"India": 1500.0, "Australia": 1500.0}


def test_unseen_teams_start_from_initial_rating():
    m = make_match(team_a="India", team_b="Namibia", winner="India")

    new = update({}, m, CONFIG)

    expected_india = 1 / (1 + 10 ** (-200 / 400))
    assert new["India"] == pytest.approx(1500 + 30 * (1 - expected_india))
    assert new["Namibia"] == pytest.approx(1300 - 30 * (1 - expected_india))


def test_ratings_of_uninvolved_teams_are_kept():
    ratings = {"India": 1500.0, "Australia": 1500.0, "England": 1550.0}

    new = update(ratings, make_match(), CONFIG)

    assert new["England"] == 1550.0


def test_tie_between_equals_changes_nothing():
    ratings = {"India": 1500.0, "Australia": 1500.0}

    new = update(ratings, make_match(winner=None, result_type=ResultType.TIE), CONFIG)

    assert new["India"] == pytest.approx(1500.0)
    assert new["Australia"] == pytest.approx(1500.0)


def test_tie_lifts_the_weaker_side():
    ratings = {"India": 1600.0, "Australia": 1500.0}

    new = update(ratings, make_match(winner=None, result_type=ResultType.TIE), CONFIG)

    assert new["Australia"] > 1500.0
    assert new["India"] < 1600.0


def test_no_result_changes_nothing():
    ratings = {"India": 1600.0, "Australia": 1500.0}

    new = update(ratings, make_match(winner=None, result_type=ResultType.NO_RESULT), CONFIG)

    assert new == ratings
    assert new is not ratings


def test_home_win_earns_less_than_away_win():
    ratings = {"India": 1500.0, "Australia": 1500.0}
    home_expected = 1 / (1 + 10 ** (-60 / 400))

    home_win = update(ratings, make_match(winner="India"), CONFIG, home="India")
    away_win = update(ratings, make_match(winner="Australia"), CONFIG, home="India")

    assert home_win["India"] == pytest.approx(1500 + 30 * (1 - home_expected))
    assert away_win["Australia"] == pytest.approx(1500 + 30 * home_expected)


def test_home_bonus_is_not_stored_in_ratings():
    ratings = {"India": 1500.0, "Australia": 1500.0}

    new = update(ratings, make_match(winner="India"), CONFIG, home="India")

    assert new["India"] + new["Australia"] == pytest.approx(3000.0)


# --- run_elo ----------------------------------------------------------------


def test_run_elo_processes_matches_in_date_order():
    first = make_match(winner="India", day=date(2024, 1, 1), match_id="m1")
    second = make_match(winner="Australia", day=date(2024, 2, 1), match_id="m2")

    in_order = run_elo([first, second], CONFIG, home_of=lambda m: None)
    shuffled = run_elo([second, first], CONFIG, home_of=lambda m: None)

    assert in_order == pytest.approx(shuffled)
    # Australia won most recently from an even start, so ends slightly ahead.
    assert in_order["Australia"] > in_order["India"]


def test_run_elo_uses_home_of_for_each_match():
    m = make_match(winner="India")

    neutral = run_elo([m], CONFIG, home_of=lambda _: None)
    at_home = run_elo([m], CONFIG, home_of=lambda _: "India")

    assert at_home["India"] < neutral["India"]


def test_run_elo_only_rates_teams_that_played():
    ratings = run_elo([make_match()], CONFIG, home_of=lambda m: None)

    assert set(ratings) == {"India", "Australia"}
