from datetime import date

from cwc27.evaluation.baselines import CoinFlip, WinRate
from cwc27.evaluation.report import Segment, compare
from tests.test_backtest import make_match


def _matches():
    return [
        make_match("A", "B", "A", date(2024, 1, 1)),
        make_match("A", "B", "A", date(2024, 2, 1)),
        make_match("A", "B", "B", date(2024, 3, 1)),
    ]


def test_compare_scores_every_model_in_every_segment():
    segments = (
        Segment("all", lambda m: True),
        Segment("from Feb", lambda m: m.date >= date(2024, 2, 1)),
    )

    rows = compare(
        _matches(),
        {"coin": CoinFlip(), "rate": WinRate()},
        home_of=lambda m: None,
        segments=segments,
    )

    assert [(r.segment, r.model, r.summary.n) for r in rows] == [
        ("all", "coin", 3),
        ("all", "rate", 3),
        ("from Feb", "coin", 2),
        ("from Feb", "rate", 2),
    ]
    assert rows[0].summary.brier == 0.25


def test_segments_with_no_matches_are_skipped():
    rows = compare(
        _matches(),
        {"coin": CoinFlip()},
        home_of=lambda m: None,
        segments=(Segment("never", lambda m: False),),
    )

    assert rows == ()


def test_models_learn_from_matches_outside_the_scored_segment():
    # WinRate only beats a coin flip on the March match if it learned from Jan and Feb.
    rows = compare(
        _matches(),
        {"rate": WinRate()},
        home_of=lambda m: None,
        segments=(Segment("March", lambda m: m.date.month == 3),),
    )

    (row,) = rows
    assert row.summary.n == 1
    assert row.summary.accuracy == 0.0  # A favoured after two wins, but B won
