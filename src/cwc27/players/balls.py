"""Ball-level inputs for player ratings, read from the deliveries table."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from types import MappingProxyType

from cwc27.store import MatchStore

# Dismissals that don't count against the batter.
NOT_DISMISSALS = ("retired hurt", "retired not out")
# Dismissals credited to the bowler (run outs, retirements, timed out etc. are not).
BOWLER_WICKETS = ("bowled", "caught", "caught and bowled", "lbw", "stumped", "hit wicket")


@dataclass(frozen=True, slots=True)
class FacedBall:
    """One ball a batter faced (wides are not faced; no-balls are)."""

    match_id: str
    date: date
    phase: str
    batter_id: str
    batter: str
    runs: int  # off the bat only
    out: bool  # the batter was dismissed on this ball
    opponent: str = ""  # the bowling team


@dataclass(frozen=True, slots=True)
class BowledBall:
    """One delivery, from the bowler's side."""

    match_id: str
    date: date
    phase: str
    bowler_id: str
    bowler: str
    conceded: int  # off the bat + wides + no-balls; byes and leg-byes aren't the bowler's
    wicket: bool  # a dismissal credited to the bowler
    opponent: str = ""  # the batting team


@dataclass(frozen=True, slots=True)
class PhaseAverage:
    """What an average player does per ball in one phase."""

    runs: float
    wickets: float


def _quoted(values: Iterable[str]) -> str:
    return ", ".join(f"'{v}'" for v in values)


_FACED_SQL = f"""
SELECT d.match_id, m.date, d.phase, d.batter_id, d.batter, d.runs_batter,
       COALESCE(d.player_out_id = d.batter_id
                AND d.wicket_kind NOT IN ({_quoted(NOT_DISMISSALS)}), FALSE),
       d.bowling_team
FROM deliveries d JOIN matches m USING (match_id)
WHERE d.wides = 0 AND m.date >= ?
ORDER BY m.date, d.match_id, d.innings, d.over_no, d.ball
"""

_BOWLED_SQL = f"""
SELECT d.match_id, m.date, d.phase, d.bowler_id, d.bowler,
       d.runs_batter + d.wides + d.noballs,
       COALESCE(d.wicket_kind IN ({_quoted(BOWLER_WICKETS)}), FALSE),
       d.batting_team
FROM deliveries d JOIN matches m USING (match_id)
WHERE m.date >= ?
ORDER BY m.date, d.match_id, d.innings, d.over_no, d.ball
"""


def load_faced(store: MatchStore, since: date) -> tuple[FacedBall, ...]:
    """Every ball faced in matches on or after `since`, in playing order."""
    return tuple(FacedBall(*row) for row in store.fetch(_FACED_SQL, [since]))


def load_bowled(store: MatchStore, since: date) -> tuple[BowledBall, ...]:
    """Every delivery bowled in matches on or after `since`, in playing order."""
    return tuple(BowledBall(*row) for row in store.fetch(_BOWLED_SQL, [since]))


def faced_averages(faced: Iterable[FacedBall]) -> Mapping[str, PhaseAverage]:
    """Average runs and dismissal rate per ball faced, by phase."""
    return _averages((b.phase, b.runs, b.out) for b in faced)


def bowled_averages(bowled: Iterable[BowledBall]) -> Mapping[str, PhaseAverage]:
    """Average runs conceded and wicket rate per delivery, by phase."""
    return _averages((b.phase, b.conceded, b.wicket) for b in bowled)


def faced_opponent_averages(
    faced: Iterable[FacedBall],
) -> Mapping[tuple[str, str], PhaseAverage]:
    """Average runs and dismissal rate per ball faced against each attack, by phase."""
    return _averages(((b.opponent, b.phase), b.runs, b.out) for b in faced)


def bowled_opponent_averages(
    bowled: Iterable[BowledBall],
) -> Mapping[tuple[str, str], PhaseAverage]:
    """Average runs conceded and wicket rate per delivery to each batting side, by phase."""
    return _averages(((b.opponent, b.phase), b.conceded, b.wicket) for b in bowled)


def _averages[K](rows: Iterable[tuple[K, int, bool]]) -> Mapping[K, PhaseAverage]:
    totals: dict[K, tuple[int, int, int]] = {}
    for key, runs, wicket in rows:
        n, total_runs, total_wickets = totals.get(key, (0, 0, 0))
        totals[key] = (n + 1, total_runs + runs, total_wickets + int(wicket))
    if not totals:
        raise ValueError("no balls to average")
    return MappingProxyType(
        {key: PhaseAverage(runs / n, wickets / n) for key, (n, runs, wickets) in totals.items()}
    )
