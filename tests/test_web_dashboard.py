import json
from datetime import UTC, date, datetime
from types import MappingProxyType

import pytest

from cwc27.ratings.elo import EloConfig
from cwc27.simulate.tournament import TeamOdds, WorldCupOutlook
from cwc27.tracking.log import LoggedPrediction
from cwc27.web_dashboard import build_dashboard, write_dashboard
from tests.test_backtest import make_match

NOW = datetime(2026, 10, 13, 1, 0, tzinfo=UTC)
TODAY = date(2026, 10, 13)


def row(day, p, actual=None, winner=None):
    return LoggedPrediction(
        fixture_key=f"{day}_a_b",
        date=day,
        series="A tour of B",
        match_no=1,
        team_a="A",
        team_b="B",
        home="A",
        p_team_a=p,
        model="elo-k25-h80",
        predicted_at=NOW,
        result_type=None if actual is None else "normal",
        winner=winner,
        actual_a=actual,
        brier=None if actual is None else (p - actual) ** 2,
        scored_at=None if actual is None else NOW,
    )


OUTLOOK = WorldCupOutlook(
    odds=MappingProxyType(
        {"A": TeamOdds(1.0, 0.9, 0.7, 0.5, 0.3), "B": TeamOdds(1.0, 0.8, 0.6, 0.4, 0.2)}
    ),
    rating_sd=100.0,
    days_ahead=360,
    start=date(2027, 10, 2),
)
MATCHES = [
    make_match("A", "B", "A", date(2023, 6, 1)),
    make_match("A", "B", "A", date(2024, 1, 1)),
    make_match("A", "C", "C", date(2024, 2, 1)),
]


def build(log=()):
    return build_dashboard(
        MATCHES,
        log,
        EloConfig(),
        lambda m: None,
        OUTLOOK,
        teams=("A", "B"),
        since=date(2023, 11, 20),
        today=TODAY,
        generated_at=NOW,
    )


def test_timeline_starts_at_the_rating_held_on_the_start_date_then_follows_each_match():
    timeline = build()["timeline"]

    a = timeline["teams"]["A"]
    assert a[0][0] == "2023-11-20"
    assert [point[0] for point in a[1:]] == ["2024-01-01", "2024-02-01"]
    assert a[1][1] > a[0][1] > a[2][1] - 100
    assert "C" not in timeline["teams"]


def test_upcoming_and_results_come_from_the_log():
    log = [
        row(date(2026, 10, 1), 0.7, actual=1.0, winner="A"),
        row(date(2026, 10, 14), 0.6),
        row(date(2026, 10, 20), 0.55),
    ]

    data = build(log)

    assert [(u["date"], u["locked"]) for u in data["upcoming"]] == [
        ("2026-10-14", True),
        ("2026-10-20", False),
    ]
    assert data["results"][0]["winner"] == "A"
    assert data["track_record"]["matches"] == 1
    assert data["track_record"]["brier"] == pytest.approx(0.09)
    assert data["track_record"]["calibration"][0]["count"] == 1


def test_no_track_record_before_any_results():
    assert build()["track_record"] is None


def test_world_cup_odds_are_sorted_by_title_chance():
    worldcup = build()["worldcup"]

    assert [t["name"] for t in worldcup["teams"]] == ["A", "B"]
    assert worldcup["teams"][0]["champion"] == 0.3
    assert (worldcup["rating_sd"], worldcup["days_ahead"]) == (100.0, 360)
    assert worldcup["start"] == "2027-10-02"


def test_write_makes_folders_and_valid_json(tmp_path):
    path = tmp_path / "web" / "data" / "dashboard.json"

    write_dashboard(path, build())

    assert json.loads(path.read_text())["generated_at"] == NOW.isoformat()
