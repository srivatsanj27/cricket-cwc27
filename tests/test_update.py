from datetime import UTC, date, datetime

import pytest

from cwc27.fixtures import Fixture
from cwc27.ratings.elo import EloConfig
from cwc27.tracking.display import format_update
from cwc27.tracking.update import run_update
from tests.test_backtest import make_match

CITIES = {"Mumbai": "India"}
NOW = datetime(2026, 10, 10, 9, 0, tzinfo=UTC)
HISTORY = [make_match("India", "Australia", "India", date(2024, 1, 1))]


def fx(day):
    return Fixture(day, "Australia tour of India", 1, "India", "Australia", None, "Mumbai")


def update(matches, fixtures, today):
    return run_update(matches, fixtures, (), EloConfig(), CITIES, today, NOW, n_sims=200, seed=1)


def test_results_after_today_never_feed_into_predictions():
    later_result = make_match("India", "Australia", "India", date(2026, 10, 12))

    with_future = update([*HISTORY, later_result], [fx(date(2026, 10, 12))], date(2026, 10, 10))
    without = update(HISTORY, [fx(date(2026, 10, 12))], date(2026, 10, 10))

    assert with_future.upcoming[0].p_team_a == pytest.approx(without.upcoming[0].p_team_a)


def test_past_predictions_without_a_result_are_flagged_as_awaiting():
    first = update(HISTORY, [fx(date(2026, 10, 12))], date(2026, 10, 10))

    later = run_update(
        HISTORY,
        [fx(date(2026, 10, 12))],
        first.log,
        EloConfig(),
        CITIES,
        date(2026, 10, 14),
        NOW,
        n_sims=200,
        seed=1,
    )

    assert [r.date for r in later.awaiting] == [date(2026, 10, 12)]


def test_tri_series_fixtures_get_a_tri_series_outlook():
    cities = {"Lahore": "Pakistan"}
    pairs = [("Pakistan", "Sri Lanka"), ("Pakistan", "England"), ("England", "Sri Lanka")]
    fixtures = [
        Fixture(date(2026, 10, 18 + i), "Tri-series", i + 1, a, b, None, "Lahore")
        for i, (a, b) in enumerate(pairs)
    ]

    outcome = run_update(
        HISTORY, fixtures, (), EloConfig(), cities, date(2026, 10, 10), NOW, n_sims=200, seed=1
    )

    assert [o.series for o in outcome.tri_outlooks] == ["Tri-series"]
    assert outcome.outlooks == ()


def test_tri_series_outlook_is_displayed():
    cities = {"Lahore": "Pakistan"}
    pairs = [("Pakistan", "Sri Lanka"), ("Pakistan", "England"), ("England", "Sri Lanka")]
    fixtures = [
        Fixture(date(2026, 10, 18 + i), "Tri-series", i + 1, a, b, None, "Lahore")
        for i, (a, b) in enumerate(pairs)
    ]
    outcome = run_update(
        HISTORY, fixtures, (), EloConfig(), cities, date(2026, 10, 10), NOW, n_sims=200, seed=1
    )

    text = format_update(outcome)

    assert "Tri-series outlook" in text
    assert "0 of 3 group matches played" in text
    assert "reach final:" in text and "win:" in text
