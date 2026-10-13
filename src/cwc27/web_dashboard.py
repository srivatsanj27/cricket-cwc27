"""Data for the website's dashboard (web/data/dashboard.json).

Ratings over time, the prediction log's upcoming calls, results and track record, and the
World Cup odds. Written by `cwc27 export-web` next to the fantasy page's ratings.json.
"""

from collections.abc import Callable, Iterable, Sequence
from datetime import date, datetime
from pathlib import Path
from typing import Any

from cwc27.evaluation.horizon import rating_history, ratings_before
from cwc27.evaluation.metrics import calibration_table
from cwc27.models import Match
from cwc27.ratings.elo import EloConfig
from cwc27.simulate.tournament import STAGES, WorldCupOutlook
from cwc27.tracking.log import LoggedPrediction, is_locked, track_record
from cwc27.web_export import write_web_export

RATING_DECIMALS = 1
PROBABILITY_DECIMALS = 4
RECENT_RESULTS = 30


def build_dashboard(
    matches: Iterable[Match],
    log: Iterable[LoggedPrediction],
    config: EloConfig,
    home_of: Callable[[Match], str | None],
    outlook: WorldCupOutlook,
    *,
    teams: Sequence[str],
    since: date,
    today: date,
    generated_at: datetime,
) -> dict[str, Any]:
    ordered = sorted(matches, key=lambda m: m.date)
    rows = tuple(log)
    finished = sorted((r for r in rows if r.result_type is not None), key=lambda r: r.date)
    return {
        "generated_at": generated_at.isoformat(),
        "ratings_through": ordered[-1].date.isoformat() if ordered else None,
        "timeline": _timeline(ordered, config, home_of, teams, since),
        "upcoming": [_upcoming(r, today) for r in rows if r.result_type is None],
        "results": [_result(r) for r in reversed(finished[-RECENT_RESULTS:])],
        "track_record": _track_record(rows),
        "worldcup": _worldcup(outlook),
    }


def write_dashboard(path: Path, payload: dict[str, Any]) -> None:
    write_web_export(path, payload)


def _timeline(
    ordered: Sequence[Match],
    config: EloConfig,
    home_of: Callable[[Match], str | None],
    teams: Sequence[str],
    since: date,
) -> dict[str, Any]:
    """Each team's rating on `since`, then after each of its matches from then on."""
    history = rating_history(ordered, config, home_of)  # same date order as `ordered`
    start = ratings_before(history, since)
    points = {
        t: [[since.isoformat(), round(start[t], RATING_DECIMALS)]] for t in teams if t in start
    }
    for match, after in zip(ordered, history.ratings, strict=True):
        if match.date < since:
            continue
        for team in (match.team_a, match.team_b):
            if team in teams:
                points.setdefault(team, []).append(
                    [match.date.isoformat(), round(after[team], RATING_DECIMALS)]
                )
    return {"since": since.isoformat(), "teams": points}


def _upcoming(row: LoggedPrediction, today: date) -> dict[str, Any]:
    return {
        "date": row.date.isoformat(),
        "series": row.series,
        "match_no": row.match_no,
        "team_a": row.team_a,
        "team_b": row.team_b,
        "home": row.home,
        "p_team_a": round(row.p_team_a, PROBABILITY_DECIMALS),
        "locked": is_locked(row.date, today),
    }


def _result(row: LoggedPrediction) -> dict[str, Any]:
    return {
        "date": row.date.isoformat(),
        "series": row.series,
        "team_a": row.team_a,
        "team_b": row.team_b,
        "p_team_a": round(row.p_team_a, PROBABILITY_DECIMALS),
        "winner": row.winner,
        "result_type": row.result_type,
        "brier": None if row.brier is None else round(row.brier, PROBABILITY_DECIMALS),
    }


def _track_record(rows: Sequence[LoggedPrediction]) -> dict[str, Any] | None:
    summary = track_record(rows)
    if summary is None:
        return None
    decided = [r for r in rows if r.actual_a is not None]
    bins = calibration_table([r.p_team_a for r in decided], [r.actual_a for r in decided])
    return {
        "matches": summary.n,
        "brier": round(summary.brier, PROBABILITY_DECIMALS),
        "log_loss": round(summary.log_loss, PROBABILITY_DECIMALS),
        "accuracy": round(summary.accuracy, PROBABILITY_DECIMALS),
        "calibration": [  # empty bins are left out (their averages aren't numbers)
            {
                "lower": b.lower,
                "upper": b.upper,
                "count": b.count,
                "mean_predicted": round(b.mean_predicted, PROBABILITY_DECIMALS),
                "observed_rate": round(b.observed_rate, PROBABILITY_DECIMALS),
            }
            for b in bins
            if b.count
        ],
    }


def _worldcup(outlook: WorldCupOutlook) -> dict[str, Any]:
    ranked = sorted(outlook.odds.items(), key=lambda item: (-item[1].champion, item[0]))
    return {
        "rating_sd": round(outlook.rating_sd, RATING_DECIMALS),
        "days_ahead": outlook.days_ahead,
        "start": outlook.start.isoformat(),
        "teams": [
            {"name": team, **{s: round(getattr(o, s), PROBABILITY_DECIMALS) for s in STAGES}}
            for team, o in ranked
        ],
    }
