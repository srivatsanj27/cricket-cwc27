"""Hand-entered results (data/manual/*.csv) for matches Cricsheet lacks or hasn't published yet."""

import csv
from collections.abc import Iterable, Mapping
from datetime import date
from pathlib import Path

from cwc27.ingest.cricsheet import ParsedMatch, ParseResult
from cwc27.models import Match, ResultType
from cwc27.teams import normalise_team, team_slug

COLUMNS = (
    "date",
    "team_a",
    "team_b",
    "winner",
    "result_type",
    "margin_runs",
    "margin_wickets",
    "venue",
    "city",
    "toss_winner",
    "toss_decision",
    "event",
    "ref",
)
TOSS_DECISIONS = frozenset({"bat", "field"})
DECISIVE_RESULTS = frozenset({ResultType.NORMAL, ResultType.DLS})


class ManualRowError(ValueError):
    """A row in a manual results file is invalid."""


def load_manual_results(directory: Path) -> ParseResult:
    """Load every CSV in `directory`; invalid rows are reported with file and line, not raised."""
    if not directory.is_dir():
        return ParseResult(parsed=(), errors=())
    loaded: list[ParsedMatch] = []
    errors: list[str] = []
    for path in sorted(directory.glob("*.csv")):
        file_parsed, file_errors = _load_file(path)
        loaded.extend(file_parsed)
        errors.extend(file_errors)

    unique: dict[tuple[date, frozenset[str]], ParsedMatch] = {}
    for p in loaded:
        key = _fixture_key(p.match)
        if key in unique:
            errors.append(f"duplicate result for {p.match.match_id} (kept the first)")
        else:
            unique[key] = p
    parsed = sorted(unique.values(), key=lambda p: (p.match.date, p.match.match_id))
    return ParseResult(parsed=tuple(parsed), errors=tuple(errors))


def merge_sources(
    cricsheet: Iterable[ParsedMatch], manual: Iterable[ParsedMatch]
) -> tuple[tuple[ParsedMatch, ...], tuple[str, ...]]:
    """Combine sources; a manual row is dropped once Cricsheet has the same match."""
    cricsheet = tuple(cricsheet)
    known = {_fixture_key(p.match) for p in cricsheet}
    kept, superseded = [], []
    for p in manual:
        if _fixture_key(p.match) in known:
            superseded.append(p.match.match_id)
        else:
            kept.append(p)
    merged = sorted(cricsheet + tuple(kept), key=lambda p: (p.match.date, p.match.match_id))
    return tuple(merged), tuple(superseded)


def append_result(path: Path, values: Mapping[str, str]) -> Match:
    """Validate one result and append it to `path` (created with a header if needed).

    Raises ManualRowError if the row is invalid or the match is already in any manual file.
    """
    row = {column: values.get(column, "") for column in COLUMNS}
    match = _row_to_match(row)
    existing = load_manual_results(path.parent).parsed
    if any(_fixture_key(p.match) == _fixture_key(match) for p in existing):
        raise ManualRowError(f"a result for {match.match_id} is already recorded")
    path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
        if is_new:
            writer.writeheader()
        writer.writerow(row)
    return match


def _load_file(path: Path) -> tuple[list[ParsedMatch], list[str]]:
    try:
        with path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if tuple(reader.fieldnames or ()) != COLUMNS:
                return [], [f"{path.name}: header must be {','.join(COLUMNS)}"]
            parsed, errors = [], []
            for row in reader:
                try:
                    parsed.append(ParsedMatch(match=_row_to_match(row), appearances=()))
                except ManualRowError as exc:
                    errors.append(f"{path.name}:{reader.line_num}: {exc}")
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        return [], [f"{path.name}: could not read file ({exc})"]
    return parsed, errors


def _row_to_match(row: dict[str, str | None]) -> Match:
    v = {column: (row.get(column) or "").strip() for column in COLUMNS}
    day = _parse_date(v["date"])
    team_a, team_b = _parse_team(v["team_a"]), _parse_team(v["team_b"])
    if team_a == team_b:
        raise ManualRowError(f"teams must differ, got {team_a!r} twice")
    result_type = _parse_result_type(v["result_type"])
    winner = _parse_winner(v["winner"], result_type, (team_a, team_b))
    toss_winner, toss_decision = _parse_toss(v["toss_winner"], v["toss_decision"], (team_a, team_b))
    return Match(
        match_id=f"man_{day.isoformat()}_{team_slug(team_a)}_{team_slug(team_b)}",
        date=day,
        team_a=team_a,
        team_b=team_b,
        venue=v["venue"] or None,
        city=v["city"] or None,
        toss_winner=toss_winner,
        toss_decision=toss_decision,
        winner=winner,
        result_type=result_type,
        margin_runs=_parse_margin(v["margin_runs"], "margin_runs"),
        margin_wickets=_parse_margin(v["margin_wickets"], "margin_wickets"),
        event=v["event"] or None,
        source="manual",
    )


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ManualRowError(f"date {value!r} is not YYYY-MM-DD") from exc


def _parse_team(value: str) -> str:
    try:
        return normalise_team(value)
    except ValueError as exc:
        raise ManualRowError("teams must not be blank") from exc


def _parse_result_type(value: str) -> ResultType:
    try:
        return ResultType(value)
    except ValueError as exc:
        allowed = ", ".join(r.value for r in ResultType)
        raise ManualRowError(f"result_type {value!r} must be one of {allowed}") from exc


def _parse_winner(value: str, result_type: ResultType, teams: tuple[str, str]) -> str | None:
    winner = normalise_team(value) if value else None
    if result_type in DECISIVE_RESULTS and winner is None:
        raise ManualRowError(f"winner is required when result_type is {result_type.value}")
    if result_type not in DECISIVE_RESULTS and winner is not None:
        raise ManualRowError(f"winner must be blank when result_type is {result_type.value}")
    if winner is not None and winner not in teams:
        raise ManualRowError(f"winner {winner!r} did not play")
    return winner


def _parse_toss(
    winner_value: str, decision: str, teams: tuple[str, str]
) -> tuple[str | None, str | None]:
    winner = normalise_team(winner_value) if winner_value else None
    if winner is not None and winner not in teams:
        raise ManualRowError(f"toss winner {winner!r} did not play")
    if decision and decision not in TOSS_DECISIONS:
        raise ManualRowError(f"toss decision {decision!r} must be bat or field")
    if bool(winner) != bool(decision):
        raise ManualRowError("toss winner and toss decision must both be filled or both blank")
    return winner, decision or None


def _parse_margin(value: str, column: str) -> int | None:
    if not value:
        return None
    if not value.isdigit():
        raise ManualRowError(f"{column} {value!r} is not a whole number")
    return int(value)


def _fixture_key(match: Match) -> tuple[date, frozenset[str]]:
    return match.date, frozenset((match.team_a, match.team_b))
