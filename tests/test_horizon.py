from datetime import date, timedelta

import pytest

from cwc27.evaluation.horizon import (
    blurred_probability,
    horizon_scores,
    rating_history,
    rating_sd,
    ratings_before,
)
from cwc27.ratings.elo import EloConfig, expected_score
from tests.test_backtest import make_match

CONFIG = EloConfig()


def no_home(match):
    return None


def test_no_blur_is_the_plain_elo_probability():
    assert blurred_probability(1600, 1500, 0.0) == pytest.approx(expected_score(1600, 1500))


def test_blur_pulls_the_probability_towards_a_coin_flip_but_keeps_the_favourite():
    sharp = blurred_probability(1700, 1500, 0.0)
    blurred = blurred_probability(1700, 1500, 150.0)

    assert 0.5 < blurred < sharp
    assert blurred + blurred_probability(1500, 1700, 150.0) == pytest.approx(1.0)


def test_blur_must_not_be_negative():
    with pytest.raises(ValueError, match="sd"):
        blurred_probability(1500, 1500, -1.0)


def test_ratings_before_a_date_ignore_matches_on_or_after_it():
    matches = [
        make_match("A", "B", "A", date(2020, 1, 1)),
        make_match("A", "B", "A", date(2020, 2, 1)),
    ]
    history = rating_history(matches, CONFIG, no_home)

    assert ratings_before(history, date(2020, 1, 1)) == {}
    after_one = ratings_before(history, date(2020, 2, 1))
    assert after_one["A"] > after_one["B"]
    assert ratings_before(history, date(2021, 1, 1))["A"] > after_one["A"]


def test_a_stable_rivalry_is_best_predicted_with_little_blur():
    start = date(2010, 1, 1)
    matches = [make_match("A", "B", "A", start + timedelta(days=30 * i)) for i in range(60)]

    scores = horizon_scores(
        matches, CONFIG, no_home, horizon_days=365, sds=(0.0, 300.0), since=date(2012, 1, 1)
    )

    assert scores[0.0].log_loss < scores[300.0].log_loss
    assert scores[0.0].matches == scores[300.0].matches > 0


def test_teams_unrated_at_the_snapshot_are_skipped():
    matches = [
        make_match("A", "B", "A", date(2010, 1, 1)),
        make_match("A", "C", "A", date(2012, 1, 1)),
        make_match("A", "B", "A", date(2012, 1, 2)),
    ]

    scores = horizon_scores(
        matches, CONFIG, no_home, horizon_days=365, sds=(0.0,), since=date(2011, 1, 1)
    )

    assert scores[0.0].matches == 1


def test_rating_uncertainty_grows_with_the_horizon():
    assert rating_sd(0) == pytest.approx(60.0)
    assert rating_sd(365) == pytest.approx(100.0, abs=0.1)
    assert rating_sd(-5) == rating_sd(0)
    assert rating_sd(180) < rating_sd(365) < rating_sd(730)
