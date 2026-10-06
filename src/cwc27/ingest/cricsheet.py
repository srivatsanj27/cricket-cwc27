"""Parse Cricsheet ODI JSON (https://cricsheet.org/format/json/) into domain types."""

import json
import shutil
import ssl
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import certifi

from cwc27.models import Appearance, Match, ResultType
from cwc27.teams import normalise_team

ODI_MALE_ZIP_URL = "https://cricsheet.org/downloads/odis_male_json.zip"
DOWNLOAD_TIMEOUT_SECONDS = 60

REQUIRED_INFO_FIELDS = (
    "dates",
    "gender",
    "match_type",
    "outcome",
    "players",
    "registry",
    "team_type",
    "teams",
    "toss",
)
EXPECTED_SCOPE = {"gender": "male", "match_type": "ODI", "team_type": "international"}
DLS_METHODS = frozenset({"D/L", "DLS"})


class ParseError(ValueError):
    """A Cricsheet file is malformed or outside the project's scope."""


@dataclass(frozen=True, slots=True)
class ParsedMatch:
    match: Match
    appearances: tuple[Appearance, ...]


@dataclass(frozen=True, slots=True)
class ParseResult:
    parsed: tuple[ParsedMatch, ...]
    errors: tuple[str, ...]


def parse_match(data: Any, match_id: str) -> ParsedMatch:
    if not isinstance(data, dict) or not isinstance(data.get("info"), dict):
        raise ParseError("missing 'info' section")
    try:
        _validate(data["info"])
        return _build(data["info"], match_id)
    except ParseError:
        raise
    except (KeyError, TypeError, AttributeError, IndexError, ValueError) as exc:
        # Unexpected shapes in external data: report this file and let the rest load.
        raise ParseError(f"malformed data: {exc!r}") from exc


def _build(info: dict[str, Any], match_id: str) -> ParsedMatch:
    team_a, team_b = (normalise_team(t) for t in info["teams"])
    if team_a == team_b:
        raise ParseError(f"teams must differ, got {team_a!r} twice")
    winner, result_type, margin_runs, margin_wickets = _parse_outcome(info["outcome"])
    if winner is not None and winner not in (team_a, team_b):
        raise ParseError(f"winner {winner!r} did not play")
    toss = info["toss"]
    toss_winner = normalise_team(toss["winner"]) if toss.get("winner") else None
    if toss_winner is not None and toss_winner not in (team_a, team_b):
        raise ParseError(f"toss winner {toss_winner!r} did not play")
    event = info.get("event") or {}

    match = Match(
        match_id=match_id,
        date=date.fromisoformat(info["dates"][0]),
        team_a=team_a,
        team_b=team_b,
        venue=info.get("venue"),
        city=info.get("city"),
        toss_winner=toss_winner,
        toss_decision=toss.get("decision"),
        winner=winner,
        result_type=result_type,
        margin_runs=margin_runs,
        margin_wickets=margin_wickets,
        event=event.get("name"),
        source="cricsheet",
    )
    return ParsedMatch(match=match, appearances=_parse_appearances(info, match_id))


def parse_zip(path: Path) -> ParseResult:
    """Parse every match file in a Cricsheet zip; bad files are reported, not raised."""
    parsed: list[ParsedMatch] = []
    errors: list[str] = []
    with zipfile.ZipFile(path) as zf:
        for name in zf.namelist():
            if not name.endswith(".json"):
                continue
            try:
                data = json.loads(zf.read(name))
                parsed.append(parse_match(data, match_id=f"cs_{Path(name).stem}"))
            except (ParseError, json.JSONDecodeError, UnicodeDecodeError) as exc:
                errors.append(f"{name}: {exc}")
    parsed.sort(key=lambda p: (p.match.date, p.match.match_id))
    return ParseResult(parsed=tuple(parsed), errors=tuple(errors))


def download_odi_zip(dest: Path, url: str = ODI_MALE_ZIP_URL) -> Path:
    """Download the Cricsheet men's ODI zip, replacing dest only once fully written and valid."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_suffix(dest.suffix + ".part")
    # certifi's CA bundle: python.org builds on macOS don't use the system keychain.
    tls = ssl.create_default_context(cafile=certifi.where())
    try:
        with (
            urllib.request.urlopen(url, timeout=DOWNLOAD_TIMEOUT_SECONDS, context=tls) as response,
            partial.open("wb") as out,
        ):
            shutil.copyfileobj(response, out)
        if not zipfile.is_zipfile(partial):
            raise ParseError(f"download from {url} is not a zip archive")
        partial.replace(dest)
    finally:
        partial.unlink(missing_ok=True)
    return dest


def _validate(info: dict[str, Any]) -> None:
    for field in REQUIRED_INFO_FIELDS:
        if field not in info:
            raise ParseError(f"missing required field '{field}'")
    for field, expected in EXPECTED_SCOPE.items():
        if info[field] != expected:
            raise ParseError(f"out of scope: {field}={info[field]!r}")
    if len(info["teams"]) != 2:
        raise ParseError(f"expected 2 teams, got {info['teams']!r}")
    if not info["dates"]:
        raise ParseError("'dates' is empty")


def _parse_outcome(
    outcome: dict[str, Any],
) -> tuple[str | None, ResultType, int | None, int | None]:
    if "winner" in outcome:
        by = outcome.get("by") or {}
        result_type = ResultType.DLS if outcome.get("method") in DLS_METHODS else ResultType.NORMAL
        return normalise_team(outcome["winner"]), result_type, by.get("runs"), by.get("wickets")
    result = outcome.get("result")
    # A tie stays a tie even if a super over or bowl-out decided it ("eliminator" / "bowl_out"):
    # over 50 overs the sides were level, which is what the ratings should learn from.
    if result == "tie":
        return None, ResultType.TIE, None, None
    if result == "no result":
        return None, ResultType.NO_RESULT, None, None
    raise ParseError(f"unrecognised outcome: {outcome!r}")


def _parse_appearances(info: dict[str, Any], match_id: str) -> tuple[Appearance, ...]:
    people = info["registry"].get("people", {})
    appearances = []
    for raw_team in info["teams"]:
        xi = info["players"].get(raw_team)
        if not xi:
            raise ParseError(f"no players listed for {raw_team!r}")
        if len(set(xi)) != len(xi):
            raise ParseError(f"duplicate player listed for {raw_team!r}")
        for name in xi:
            if name not in people:
                raise ParseError(f"player {name!r} missing from registry")
            appearances.append(
                Appearance(
                    match_id=match_id,
                    team=normalise_team(raw_team),
                    player_name=name,
                    player_id=people[name],
                )
            )
    return tuple(appearances)
