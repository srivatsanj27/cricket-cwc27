from datetime import UTC, date, datetime

import pytest

from cwc27.fixtures import Fixture
from cwc27.models import ResultType
from cwc27.tracking.log import (
    read_log,
    refresh_predictions,
    score_log,
    track_record,
    write_log,
)
from tests.test_backtest import make_match

TODAY = date(2026, 10, 10)
NOW = datetime(2026, 10, 10, 9, 0, tzinfo=UTC)
LATER = datetime(2026, 10, 20, 9, 0, tzinfo=UTC)


def fx(day, team_a="Sri Lanka", team_b="Pakistan", match_no=1):
    return Fixture(day, "Pakistan tour of Sri Lanka", match_no, team_a, team_b, None, "Colombo")


def predictor(p):
    return lambda fixture: (p, "Sri Lanka")


def predicted(fixtures, p=0.6):
    return refresh_predictions((), fixtures, predictor(p), "elo", TODAY, NOW)


def test_predicts_only_fixtures_after_tomorrow():
    log = predicted(
        [fx(date(2026, 10, 9)), fx(TODAY), fx(date(2026, 10, 11)), fx(date(2026, 10, 12))]
    )

    assert [row.date for row in log] == [date(2026, 10, 12)]
    row = log[0]
    assert (row.team_a, row.team_b, row.home, row.p_team_a) == (
        "Sri Lanka",
        "Pakistan",
        "Sri Lanka",
        0.6,
    )
    assert row.predicted_at == NOW
    assert row.result_type is None


def test_refresh_replaces_a_future_prediction():
    first = predicted([fx(date(2026, 10, 13))])
    later_now = datetime(2026, 10, 11, 9, 0, tzinfo=UTC)

    second = refresh_predictions(
        first, [fx(date(2026, 10, 13))], predictor(0.7), "elo", date(2026, 10, 11), later_now
    )

    assert len(second) == 1
    assert second[0].p_team_a == 0.7
    assert second[0].predicted_at == later_now


@pytest.mark.parametrize("day", [date(2026, 10, 11), date(2026, 10, 12), date(2026, 10, 14)])
def test_predictions_lock_the_day_before_the_match(day):
    log = predicted([fx(date(2026, 10, 12))])

    later = refresh_predictions(log, [fx(date(2026, 10, 12))], predictor(0.9), "elo", day, LATER)

    assert later == log


def test_unlocked_rows_for_removed_or_postponed_fixtures_are_dropped():
    log = predicted([fx(date(2026, 10, 15))])

    assert refresh_predictions(log, [], predictor(0.6), "elo", TODAY, NOW) == ()


def test_locked_rows_are_kept_even_if_the_fixture_is_removed():
    log = predicted([fx(date(2026, 10, 12))])

    kept = refresh_predictions(log, [], predictor(0.6), "elo", date(2026, 10, 11), LATER)

    assert kept == log


def test_scoring_fills_in_the_result_from_team_a_view():
    log = predicted([fx(date(2026, 10, 12))])
    match = make_match("Pakistan", "Sri Lanka", "Pakistan", date(2026, 10, 12))

    (row,) = score_log(log, [match], LATER)

    assert row.result_type == ResultType.NORMAL.value
    assert row.winner == "Pakistan"
    assert row.actual_a == 0.0
    assert row.brier == pytest.approx(0.36)
    assert row.scored_at == LATER


def test_no_result_is_recorded_without_a_brier_score():
    log = predicted([fx(date(2026, 10, 12))])
    washout = make_match(
        "Sri Lanka", "Pakistan", None, date(2026, 10, 12), result_type=ResultType.NO_RESULT
    )

    (row,) = score_log(log, [washout], LATER)

    assert row.result_type == ResultType.NO_RESULT.value
    assert row.actual_a is None and row.brier is None


def test_unplayed_and_already_scored_rows_are_left_alone():
    log = predicted([fx(date(2026, 10, 12))])
    match = make_match("Sri Lanka", "Pakistan", "Sri Lanka", date(2026, 10, 12))
    scored = score_log(log, [match], LATER)

    assert score_log(log, [], LATER) == log
    assert score_log(scored, [match], datetime(2027, 1, 1, tzinfo=UTC)) == scored


def test_write_then_read_round_trips(tmp_path):
    log = predicted([fx(date(2026, 10, 12)), fx(date(2026, 10, 15), match_no=2)])
    result = make_match("Sri Lanka", "Pakistan", "Sri Lanka", date(2026, 10, 12))
    log = score_log(log, [result], LATER)
    path = tmp_path / "log.csv"

    write_log(path, log)

    assert read_log(path) == log


def test_reading_a_missing_log_gives_nothing(tmp_path):
    assert read_log(tmp_path / "nope.csv") == ()


def test_reading_a_corrupt_log_raises_with_line_number(tmp_path):
    path = tmp_path / "log.csv"
    write_log(path, predicted([fx(date(2026, 10, 12))]))
    path.write_text(path.read_text().replace("0.6", "lots"))

    with pytest.raises(ValueError, match="log.csv:2"):
        read_log(path)


def test_track_record_scores_only_decided_matches():
    log = predicted(
        [fx(date(2026, 10, 12)), fx(date(2026, 10, 15), match_no=2), fx(date(2026, 10, 18))]
    )
    results = [
        make_match("Sri Lanka", "Pakistan", "Sri Lanka", date(2026, 10, 12)),
        make_match(
            "Sri Lanka", "Pakistan", None, date(2026, 10, 15), result_type=ResultType.NO_RESULT
        ),
    ]

    summary = track_record(score_log(log, results, LATER))

    assert summary is not None
    assert summary.n == 1
    assert summary.brier == pytest.approx(0.16)


def test_track_record_is_none_before_any_results():
    assert track_record(()) is None
