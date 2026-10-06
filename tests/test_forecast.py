from datetime import date

import pytest

from cwc27.fixtures import Fixture
from cwc27.models import ResultType
from cwc27.simulate.forecast import series_outlooks
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
