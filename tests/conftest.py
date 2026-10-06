"""Shared test helpers: build synthetic Cricsheet match JSON."""

import json
import zipfile
from pathlib import Path

import pytest


def make_cricsheet_match(
    *,
    teams=("Alphaland", "Betaland"),
    date="2024-01-10",
    outcome=None,
    toss=None,
    venue="Test Oval",
    city="Testville",
    gender="male",
    match_type="ODI",
    team_type="international",
    event=None,
):
    """Return a dict shaped like a Cricsheet JSON file (synthetic values only)."""
    team_a, team_b = teams
    players = {
        team_a: [f"A Player{i}" for i in range(1, 12)],
        team_b: [f"B Player{i}" for i in range(1, 12)],
    }
    people = {
        name: f"id{index:06d}"
        for index, name in enumerate(name for xi in players.values() for name in xi)
    }
    info = {
        "balls_per_over": 6,
        "dates": [date],
        "gender": gender,
        "match_type": match_type,
        "outcome": outcome if outcome is not None else {"winner": team_a, "by": {"runs": 25}},
        "players": players,
        "registry": {"people": people},
        "season": date[:4],
        "team_type": team_type,
        "teams": list(teams),
        "toss": toss if toss is not None else {"winner": team_b, "decision": "field"},
        "venue": venue,
        "city": city,
    }
    if event is not None:
        info["event"] = event
    return {"meta": {"data_version": "1.1.0"}, "info": info, "innings": []}


@pytest.fixture
def cricsheet_zip(tmp_path: Path):
    """Write the given {stem: match_dict} mapping into a zip shaped like Cricsheet's download."""

    def _build(matches: dict[str, dict]) -> Path:
        path = tmp_path / "odis_male_json.zip"
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr("README.txt", "synthetic")
            for stem, data in matches.items():
                zf.writestr(f"{stem}.json", json.dumps(data))
        return path

    return _build
