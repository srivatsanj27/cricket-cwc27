import json
from datetime import UTC, date, datetime

import pytest

from cwc27.models import Match, ResultType
from cwc27.ratings.elo import EloConfig
from cwc27.web_export import build_web_export, write_web_export

GENERATED_AT = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)
ACTIVE_SINCE = date(2024, 1, 1)
DEFAULT_CONFIG = EloConfig()
CITIES = {"Mumbai": "India", "Lahore": "Pakistan", "Dubai": "United Arab Emirates"}


def make_match(team_a, team_b, winner, day, city=None):
    return Match(
        match_id=f"{day}-{team_a}-{team_b}",
        date=day,
        team_a=team_a,
        team_b=team_b,
        venue=None,
        city=city,
        toss_winner=None,
        toss_decision=None,
        winner=winner,
        result_type=ResultType.NORMAL,
        margin_runs=None,
        margin_wickets=None,
        event=None,
        source="test",
    )


def export(matches, config=DEFAULT_CONFIG):
    return build_web_export(matches, config, CITIES, GENERATED_AT, ACTIVE_SINCE)


def test_teams_are_ranked_by_rating_with_recent_match_counts():
    matches = [
        make_match("India", "Pakistan", "India", date(2024, 2, 1)),
        make_match("India", "Pakistan", "India", date(2024, 3, 1)),
    ]

    payload = export(matches)

    assert [t["name"] for t in payload["teams"]] == ["India", "Pakistan"]
    india, pakistan = payload["teams"]
    assert india["rating"] > 1500 > pakistan["rating"]
    assert india["matches"] == 2
    assert india["full_member"] is True


def test_teams_without_a_recent_match_are_left_out():
    matches = [
        make_match("Kenya", "India", "India", date(2020, 1, 1)),
        make_match("India", "Pakistan", "Pakistan", date(2024, 2, 1)),
    ]

    payload = export(matches)

    assert {t["name"] for t in payload["teams"]} == {"India", "Pakistan"}


def test_old_matches_still_shape_ratings_but_not_match_counts():
    matches = [
        make_match("India", "Pakistan", "India", date(2020, 1, 1)),
        make_match("India", "Pakistan", "Pakistan", date(2024, 2, 1)),
    ]

    def india(payload):
        return next(t for t in payload["teams"] if t["name"] == "India")

    with_history = india(export(matches))
    recent_only = india(export(matches[1:]))

    assert with_history["matches"] == 1
    assert with_history["rating"] != recent_only["rating"]


def test_home_advantage_is_applied_when_rating():
    away_win = [make_match("India", "Pakistan", "Pakistan", date(2024, 2, 1), city="Mumbai")]
    neutral_win = [make_match("India", "Pakistan", "Pakistan", date(2024, 2, 1), city="Dubai")]

    def pakistan_rating(matches):
        return next(t["rating"] for t in export(matches)["teams"] if t["name"] == "Pakistan")

    assert pakistan_rating(away_win) > pakistan_rating(neutral_win)


def test_payload_carries_metadata_and_elo_settings():
    matches = [make_match("India", "Pakistan", "India", date(2024, 2, 1))]

    payload = export(matches, EloConfig(home_advantage=60.0, scale=400.0))

    assert payload["generated_at"] == "2026-10-06T12:00:00+00:00"
    assert payload["ratings_through"] == "2024-02-01"
    assert payload["matches_rated"] == 1
    assert payload["elo"] == {"home_advantage": 60.0, "scale": 400.0}


def test_venues_are_sorted_by_country_then_city():
    payload = export([make_match("India", "Pakistan", "India", date(2024, 2, 1))])

    assert payload["venues"] == [
        {"city": "Mumbai", "country": "India"},
        {"city": "Lahore", "country": "Pakistan"},
        {"city": "Dubai", "country": "United Arab Emirates"},
    ]


def test_ratings_are_rounded_for_display():
    payload = export([make_match("India", "Pakistan", "India", date(2024, 2, 1))])

    for team in payload["teams"]:
        assert team["rating"] == round(team["rating"], 1)


def test_no_recent_matches_is_an_error():
    with pytest.raises(ValueError, match="No matches since"):
        export([make_match("India", "Pakistan", "India", date(2020, 1, 1))])


def test_write_creates_parent_folders_and_valid_json(tmp_path):
    out = tmp_path / "web" / "data" / "ratings.json"
    payload = export([make_match("India", "Pakistan", "India", date(2024, 2, 1))])

    write_web_export(out, payload)

    assert json.loads(out.read_text()) == payload
    assert [f.name for f in out.parent.iterdir()] == ["ratings.json"]  # no temp file left behind
