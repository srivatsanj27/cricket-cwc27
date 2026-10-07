"""Specification for simulate_tri_series. Written before the implementation (TDD)."""

import pytest

from cwc27.simulate.multiseries import GroupMatch, simulate_tri_series

MANY = 100_000
TOLERANCE = 0.01


def even_final(a, b):
    return 0.5


def double_round_robin(p=0.5):
    """A, B and C each play the others twice, every match at probability p for team_a."""
    pairs = [("A", "B"), ("A", "C"), ("B", "C")]
    return [GroupMatch(a, b, p) for a, b in pairs + pairs]


def test_exactly_two_finalists_and_one_winner():
    forecast = simulate_tri_series(double_round_robin(0.6), even_final, n_sims=5_000, seed=1)

    assert sum(forecast.p_reach_final.values()) == pytest.approx(2.0)
    assert sum(forecast.p_win.values()) == pytest.approx(1.0)


def test_every_team_is_listed_even_with_no_chance():
    group = [
        GroupMatch("A", "B", 1.0),
        GroupMatch("A", "C", 1.0),
        GroupMatch("B", "C", 1.0),
    ]

    forecast = simulate_tri_series(group, even_final, n_sims=1_000, seed=1)

    assert set(forecast.p_reach_final) == {"A", "B", "C"}
    assert forecast.p_reach_final["C"] == 0.0
    assert forecast.p_win["C"] == 0.0


def test_certain_group_results_then_the_final_decides():
    group = [
        GroupMatch("A", "B", 1.0),
        GroupMatch("A", "C", 1.0),
        GroupMatch("B", "C", 1.0),
    ]

    forecast = simulate_tri_series(group, lambda a, b: 0.7, n_sims=MANY, seed=3)

    assert forecast.p_reach_final == {"A": 1.0, "B": 1.0, "C": 0.0}
    assert forecast.p_win["A"] == pytest.approx(0.7, abs=TOLERANCE)
    assert forecast.p_win["B"] == pytest.approx(0.3, abs=TOLERANCE)


def test_final_probability_is_from_the_first_teams_point_of_view():
    # B and C reach the final; C always wins it, whichever way round it is asked.
    group = [
        GroupMatch("B", "A", 1.0),
        GroupMatch("C", "A", 1.0),
        GroupMatch("B", "C", 1.0),
    ]

    def c_always_wins(first, second):
        return 1.0 if first == "C" else 0.0

    forecast = simulate_tri_series(group, c_always_wins, n_sims=1_000, seed=1)

    assert forecast.p_win["C"] == 1.0


def test_evenly_matched_teams_share_the_chances():
    forecast = simulate_tri_series(double_round_robin(0.5), even_final, n_sims=MANY, seed=5)

    for team in "ABC":
        assert forecast.p_reach_final[team] == pytest.approx(2 / 3, abs=TOLERANCE)
        assert forecast.p_win[team] == pytest.approx(1 / 3, abs=TOLERANCE)


def test_a_washout_gives_each_side_a_point():
    # A and B both beat C; their match is washed out, so they finish level on 3 points
    # and C (0 points) can never reach the final.
    group = [
        GroupMatch("A", "C", 1.0),
        GroupMatch("B", "C", 1.0),
        GroupMatch("A", "B", 0.5, no_result=True),
    ]

    forecast = simulate_tri_series(group, even_final, n_sims=1_000, seed=1)

    assert forecast.p_reach_final == {"A": 1.0, "B": 1.0, "C": 0.0}


def test_same_seed_gives_the_same_forecast():
    first = simulate_tri_series(double_round_robin(0.55), even_final, n_sims=2_000, seed=42)
    again = simulate_tri_series(double_round_robin(0.55), even_final, n_sims=2_000, seed=42)

    assert first == again


@pytest.mark.parametrize(
    ("group", "n_sims"),
    [
        ([GroupMatch("A", "A", 0.5)], 100),
        ([GroupMatch("A", "B", 1.5)], 100),
        ([GroupMatch("A", "B", -0.1)], 100),
        ([], 100),
        ([GroupMatch("A", "B", 0.5)], 0),
    ],
)
def test_invalid_input_raises(group, n_sims):
    with pytest.raises(ValueError):
        simulate_tri_series(group, even_final, n_sims=n_sims, seed=1)
