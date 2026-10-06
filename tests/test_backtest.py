from dataclasses import dataclass
from datetime import date

import pytest

from cwc27.evaluation.backtest import walk_forward
from cwc27.evaluation.baselines import CoinFlip, WinRate
from cwc27.models import Match, ResultType


def make_match(team_a, team_b, winner, day, result_type=ResultType.NORMAL, match_id=None):
    return Match(
        match_id=match_id or f"m_{day.isoformat()}_{team_a}_{team_b}",
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


@dataclass(frozen=True)
class CountingModel:
    """Predicts (matches seen) / 10, so we can tell when learning happened."""

    seen: int = 0

    def predict(self, team_a, team_b, home):
        return self.seen / 10

    def learn(self, match, home):
        return CountingModel(self.seen + 1)


def test_predicts_each_match_before_learning_from_it():
    matches = [
        make_match("A", "B", "A", date(2024, 1, 1)),
        make_match("A", "B", "B", date(2024, 1, 2)),
    ]

    predictions = walk_forward(matches, CountingModel(), home_of=lambda m: None)

    assert [p.p_team_a for p in predictions] == [0.0, 0.1]
    assert [p.actual_a for p in predictions] == [1.0, 0.0]


def test_processes_matches_in_date_order():
    later = make_match("A", "B", "A", date(2024, 2, 1))
    earlier = make_match("A", "B", "A", date(2024, 1, 1))

    predictions = walk_forward([later, earlier], CountingModel(), home_of=lambda m: None)

    assert [p.match.date for p in predictions] == [date(2024, 1, 1), date(2024, 2, 1)]


def test_no_results_are_not_scored_but_still_passed_to_learn():
    matches = [
        make_match("A", "B", None, date(2024, 1, 1), ResultType.NO_RESULT),
        make_match("A", "B", "A", date(2024, 1, 2)),
    ]

    predictions = walk_forward(matches, CountingModel(), home_of=lambda m: None)

    assert len(predictions) == 1
    assert predictions[0].p_team_a == pytest.approx(0.1)


def test_home_side_is_recorded_on_each_prediction():
    matches = [make_match("A", "B", "A", date(2024, 1, 1))]

    (prediction,) = walk_forward(matches, CountingModel(), home_of=lambda m: "B")

    assert prediction.home == "B"


def test_coin_flip_always_predicts_even():
    model = CoinFlip().learn(make_match("A", "B", "A", date(2024, 1, 1)), None)

    assert model.predict("A", "B", None) == 0.5


def test_win_rate_starts_even_for_unseen_teams():
    assert WinRate().predict("A", "B", None) == pytest.approx(0.5)


def test_win_rate_favours_the_team_that_has_won_more():
    model = WinRate().learn(make_match("A", "B", "A", date(2024, 1, 1)), None)

    # Smoothed rates: A = (1+1)/(1+2) = 2/3, B = (0+1)/(1+2) = 1/3
    assert model.predict("A", "B", None) == pytest.approx((2 / 3) / (2 / 3 + 1 / 3))


def test_win_rate_counts_a_tie_as_half_a_win_and_ignores_no_results():
    tie = make_match("A", "B", None, date(2024, 1, 1), ResultType.TIE)
    washout = make_match("A", "C", None, date(2024, 1, 2), ResultType.NO_RESULT)

    model = WinRate().learn(tie, None).learn(washout, None)

    assert model.predict("A", "B", None) == pytest.approx(0.5)
    assert model.predict("C", "B", None) == pytest.approx(0.5)


def test_win_rate_learn_returns_new_model_without_changing_the_old_one():
    original = WinRate()

    original.learn(make_match("A", "B", "A", date(2024, 1, 1)), None)

    assert original.predict("A", "B", None) == pytest.approx(0.5)
