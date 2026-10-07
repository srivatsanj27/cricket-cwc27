from datetime import date

import pytest

from cwc27.fixtures import Fixture
from cwc27.models import ResultType
from cwc27.simulate.forecast import series_outlooks, tri_series_outlooks
from tests.test_backtest import make_match

SERIES = "Pakistan tour of Sri Lanka"


def fx(day, team_a="Sri Lanka", team_b="Pakistan", series=SERIES, match_no=1):
    return Fixture(date(2026, 10, day), series, match_no, team_a, team_b, None, "Colombo")


def sri_lanka_at(p):
    """Predictor giving Sri Lanka probability p, whichever way round the fixture is listed."""
    return lambda f: p if f.team_a == "Sri Lanka" else 1 - p


def test_played_matches_count_as_certain_and_the_rest_are_simulated():
    fixtures = [fx(12, match_no=1), fx(15, match_no=2), fx(18, match_no=3)]
    played = [make_match("Sri Lanka", "Pakistan", "Sri Lanka", date(2026, 10, 12))]

    (outlook,) = series_outlooks(fixtures, played, sri_lanka_at(0.6), n_sims=100_000, seed=3)

    assert (outlook.team_a, outlook.team_b) == ("Sri Lanka", "Pakistan")
    assert outlook.played == (1, 0)
    assert outlook.remaining == 2
    # Sri Lanka, 1-0 up, only lose the series by losing both remaining matches.
    assert outlook.forecast.p_a_wins_series == pytest.approx(1 - 0.4 * 0.4, abs=0.01)


def test_fixtures_listed_the_other_way_round_are_flipped():
    fixtures = [fx(12, match_no=1), fx(15, team_a="Pakistan", team_b="Sri Lanka", match_no=2)]

    (outlook,) = series_outlooks(fixtures, [], sri_lanka_at(1.0), n_sims=1_000, seed=3)

    assert outlook.forecast.scorelines == {(2, 0): 1.0}


def test_played_results_are_read_from_either_team_order():
    fixtures = [fx(12, match_no=1), fx(15, match_no=2)]
    played = [make_match("Pakistan", "Sri Lanka", "Pakistan", date(2026, 10, 12))]

    (outlook,) = series_outlooks(fixtures, played, sri_lanka_at(0.5), n_sims=1_000, seed=3)

    assert outlook.played == (0, 1)


def test_washed_out_matches_count_for_nobody():
    fixtures = [fx(12, match_no=1), fx(15, match_no=2)]
    played = [
        make_match(
            "Sri Lanka", "Pakistan", None, date(2026, 10, 12), result_type=ResultType.NO_RESULT
        )
    ]

    (outlook,) = series_outlooks(fixtures, played, sri_lanka_at(1.0), n_sims=1_000, seed=3)

    assert outlook.played == (0, 0)
    assert outlook.remaining == 1
    assert outlook.forecast.n_matches == 1


def test_series_with_more_than_two_teams_are_skipped_for_now():
    fixtures = [
        fx(12, "Sri Lanka", "Pakistan", series="Tri-series"),
        fx(14, "Pakistan", "England", series="Tri-series"),
        fx(16, "England", "Sri Lanka", series="Tri-series"),
    ]

    assert series_outlooks(fixtures, [], sri_lanka_at(0.5), n_sims=100, seed=3) == ()


def test_series_are_returned_in_order_of_their_first_match():
    fixtures = [
        fx(20, "India", "New Zealand", series="NZ tour of India"),
        fx(12, match_no=1),
    ]

    outlooks = series_outlooks(fixtures, [], lambda f: 0.5, n_sims=100, seed=3)

    assert [o.series for o in outlooks] == [SERIES, "NZ tour of India"]


TRI = "Tri-series"


def tri_fixtures():
    pairs = [("Pakistan", "Sri Lanka"), ("Pakistan", "England"), ("England", "Sri Lanka")]
    return [
        Fixture(date(2026, 10, 18 + i), TRI, i + 1, a, b, None, "Lahore")
        for i, (a, b) in enumerate(pairs + pairs)
    ]


def test_tri_series_outlook_simulates_the_group_and_final():
    (outlook,) = tri_series_outlooks(tri_fixtures(), [], lambda f: 0.5, n_sims=2_000, seed=1)

    assert outlook.series == TRI
    assert outlook.teams == ("England", "Pakistan", "Sri Lanka")
    assert (outlook.played, outlook.remaining) == (0, 6)
    assert sum(outlook.forecast.p_reach_final.values()) == pytest.approx(2.0)
    assert sum(outlook.forecast.p_win.values()) == pytest.approx(1.0)


def test_tri_series_results_so_far_are_fixed():
    # Pakistan have already won both their first two matches.
    played = [
        make_match("Pakistan", "Sri Lanka", "Pakistan", date(2026, 10, 18)),
        make_match("England", "Pakistan", "Pakistan", date(2026, 10, 19)),
    ]

    def pakistan_lose_the_rest(f):
        return 0.0 if f.team_a == "Pakistan" else (1.0 if f.team_b == "Pakistan" else 0.5)

    (outlook,) = tri_series_outlooks(
        tri_fixtures(), played, pakistan_lose_the_rest, n_sims=2_000, seed=1
    )

    assert (outlook.played, outlook.remaining) == (2, 4)
    # Two wins (4 points) can't guarantee the final once Pakistan lose the rest...
    assert 0.0 < outlook.forecast.p_reach_final["Pakistan"] < 1.0


def test_tri_series_washouts_and_ties_give_a_point_each():
    played = [
        make_match(
            "Pakistan", "Sri Lanka", None, date(2026, 10, 18), result_type=ResultType.NO_RESULT
        )
    ]

    (outlook,) = tri_series_outlooks(tri_fixtures(), played, lambda f: 0.5, n_sims=500, seed=1)

    assert (outlook.played, outlook.remaining) == (1, 5)


def test_tri_series_final_is_predicted_at_the_last_group_venue():
    asked = []

    def record(f):
        asked.append(f)
        return 0.5

    tri_series_outlooks(tri_fixtures(), [], record, n_sims=50, seed=1)

    finals = [f for f in asked if f.match_no == 0]
    assert finals and all(f.city == "Lahore" for f in finals)


def test_two_team_series_have_no_tri_series_outlook():
    assert tri_series_outlooks([fx(12), fx(15)], [], lambda f: 0.5, n_sims=50, seed=1) == ()


def test_tri_series_reads_results_whichever_team_order_they_were_recorded_in():
    # Every group match played. Pakistan win all four; two are recorded England v
    # Pakistan / Sri Lanka v Pakistan, the reverse of the fixture order.
    played = [
        make_match("Pakistan", "Sri Lanka", "Pakistan", date(2026, 10, 18)),
        make_match("England", "Pakistan", "Pakistan", date(2026, 10, 19)),
        make_match("England", "Sri Lanka", "England", date(2026, 10, 20)),
        make_match("Sri Lanka", "Pakistan", "Pakistan", date(2026, 10, 21)),
        make_match("Pakistan", "England", "Pakistan", date(2026, 10, 22)),
        make_match("England", "Sri Lanka", "England", date(2026, 10, 23)),
    ]

    (outlook,) = tri_series_outlooks(tri_fixtures(), played, lambda f: 0.5, n_sims=200, seed=1)

    assert outlook.remaining == 0
    assert outlook.forecast.p_reach_final == {"England": 1.0, "Pakistan": 1.0, "Sri Lanka": 0.0}
