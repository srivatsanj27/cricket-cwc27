"""The prediction log (data/predictions_log.csv): the model's public track record.

Each upcoming fixture gets one row. The prediction may be refreshed until two days before
the match (so match 2 reflects match 1's result); from the day before it is locked, which
leaves a full day's margin for time zones. Once the result is known, the row is scored.
Git history keeps every refresh.
"""

import csv
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from pathlib import Path

from cwc27.evaluation.metrics import Summary, summarise
from cwc27.fixtures import Fixture
from cwc27.models import Match
from cwc27.ratings.elo import actual_score

LOG_COLUMNS = (
    "fixture_key",
    "date",
    "series",
    "match_no",
    "team_a",
    "team_b",
    "home",
    "p_team_a",
    "model",
    "predicted_at",
    "result_type",
    "winner",
    "actual_a",
    "brier",
    "scored_at",
)

# Predictions freeze this many days before the match date.
LOCK_DAYS_BEFORE = 1

# Returns (probability team_a wins, home side or None) for a fixture.
Predictor = Callable[[Fixture], tuple[float, str | None]]


@dataclass(frozen=True, slots=True)
class LoggedPrediction:
    fixture_key: str
    date: date
    series: str
    match_no: int
    team_a: str
    team_b: str
    home: str | None
    p_team_a: float
    model: str
    predicted_at: datetime
    result_type: str | None = None
    winner: str | None = None
    actual_a: float | None = None
    brier: float | None = None
    scored_at: datetime | None = None


def refresh_predictions(
    log: Iterable[LoggedPrediction],
    fixtures: Iterable[Fixture],
    predict: Predictor,
    model: str,
    today: date,
    now: datetime,
) -> tuple[LoggedPrediction, ...]:
    """Re-predict every fixture that isn't locked yet.

    Locked or scored rows are never changed. Unlocked rows whose fixture is gone (postponed
    or removed) are dropped, so they can't linger unscored.
    """
    current = {fixture.key for fixture in fixtures}
    rows = {
        row.fixture_key: row
        for row in log
        if row.result_type is not None or is_locked(row.date, today) or row.fixture_key in current
    }
    for fixture in fixtures:
        existing = rows.get(fixture.key)
        if is_locked(fixture.date, today) or (existing and existing.result_type is not None):
            continue
        p, home = predict(fixture)
        rows[fixture.key] = LoggedPrediction(
            fixture_key=fixture.key,
            date=fixture.date,
            series=fixture.series,
            match_no=fixture.match_no,
            team_a=fixture.team_a,
            team_b=fixture.team_b,
            home=home,
            p_team_a=p,
            model=model,
            predicted_at=now,
        )
    return _ordered(rows.values())


def is_locked(match_date: date, today: date) -> bool:
    return match_date <= today + timedelta(days=LOCK_DAYS_BEFORE)


def score_log(
    log: Iterable[LoggedPrediction], matches: Iterable[Match], now: datetime
) -> tuple[LoggedPrediction, ...]:
    """Fill in results for unscored rows whose match has been played."""
    played = {(m.date, frozenset((m.team_a, m.team_b))): m for m in matches}
    return tuple(
        _scored(row, played.get((row.date, frozenset((row.team_a, row.team_b)))), now)
        for row in log
    )


def track_record(log: Iterable[LoggedPrediction]) -> Summary | None:
    """Scores over every decided, logged match; None until there is at least one."""
    decided = [row for row in log if row.actual_a is not None]
    if not decided:
        return None
    return summarise([row.p_team_a for row in decided], [row.actual_a for row in decided])


def read_log(path: Path) -> tuple[LoggedPrediction, ...]:
    """Read the log; a missing file is an empty log. Raises ValueError naming the bad line."""
    if not path.exists():
        return ()
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if tuple(reader.fieldnames or ()) != LOG_COLUMNS:
            raise ValueError(f"{path.name}: header must be {','.join(LOG_COLUMNS)}")
        rows = []
        for row in reader:
            try:
                rows.append(_from_csv(row))
            except (ValueError, KeyError, TypeError) as exc:
                raise ValueError(f"{path.name}:{reader.line_num}: {exc}") from exc
    return tuple(rows)


def write_log(path: Path, log: Iterable[LoggedPrediction]) -> None:
    """Write the whole log, replacing the file only once it is fully written."""
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".tmp")
    with partial.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(LOG_COLUMNS)
        writer.writerows(_to_csv(row) for row in log)
    partial.replace(path)


def _scored(row: LoggedPrediction, match: Match | None, now: datetime) -> LoggedPrediction:
    if row.result_type is not None or match is None:
        return row
    actual = actual_score(match, row.team_a)
    return replace(
        row,
        result_type=match.result_type.value,
        winner=match.winner,
        actual_a=actual,
        brier=None if actual is None else (row.p_team_a - actual) ** 2,
        scored_at=now,
    )


def _ordered(rows: Iterable[LoggedPrediction]) -> tuple[LoggedPrediction, ...]:
    return tuple(sorted(rows, key=lambda r: (r.date, r.series, r.match_no, r.fixture_key)))


def _to_csv(row: LoggedPrediction) -> list[str]:
    return [
        row.fixture_key,
        row.date.isoformat(),
        row.series,
        str(row.match_no),
        row.team_a,
        row.team_b,
        row.home or "",
        repr(row.p_team_a),
        row.model,
        row.predicted_at.isoformat(),
        row.result_type or "",
        row.winner or "",
        "" if row.actual_a is None else repr(row.actual_a),
        "" if row.brier is None else repr(row.brier),
        "" if row.scored_at is None else row.scored_at.isoformat(),
    ]


def _from_csv(row: dict[str, str]) -> LoggedPrediction:
    def optional(column: str) -> str | None:
        return row[column] or None

    def optional_float(column: str) -> float | None:
        return float(row[column]) if row[column] else None

    p_team_a = float(row["p_team_a"])
    if not 0.0 <= p_team_a <= 1.0:
        raise ValueError(f"p_team_a {p_team_a} is not between 0 and 1")
    scored_at = optional("scored_at")
    return LoggedPrediction(
        fixture_key=row["fixture_key"],
        date=date.fromisoformat(row["date"]),
        series=row["series"],
        match_no=int(row["match_no"]),
        team_a=row["team_a"],
        team_b=row["team_b"],
        home=optional("home"),
        p_team_a=p_team_a,
        model=row["model"],
        predicted_at=datetime.fromisoformat(row["predicted_at"]),
        result_type=optional("result_type"),
        winner=optional("winner"),
        actual_a=optional_float("actual_a"),
        brier=optional_float("brier"),
        scored_at=datetime.fromisoformat(scored_at) if scored_at else None,
    )
