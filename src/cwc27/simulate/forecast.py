"""Series outlooks: results so far are certain, the remaining matches are simulated.

Two-team series use the bilateral series simulator; three or more teams use the
round-robin-plus-final simulator. Once a tri-series group stage ends, add its final to
fixtures.csv as its own series (e.g. "... Final") so it is predicted like any other match.
"""

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import date

from cwc27.fixtures import Fixture
from cwc27.models import Match
from cwc27.ratings.elo import actual_score
from cwc27.simulate.multiseries import GroupMatch, TriSeriesForecast, simulate_tri_series
from cwc27.simulate.series import SeriesForecast, simulate_series

MatchKey = tuple[date, frozenset[str]]


@dataclass(frozen=True, slots=True)
class SeriesOutlook:
    series: str
    team_a: str
    team_b: str
    played: tuple[int, int]  # (team_a wins, team_b wins) so far
    remaining: int
    forecast: SeriesForecast


@dataclass(frozen=True, slots=True)
class TriSeriesOutlook:
    series: str
    teams: tuple[str, ...]
    played: int  # group matches with a result (washouts and ties included)
    remaining: int
    forecast: TriSeriesForecast


def series_outlooks(
    fixtures: Iterable[Fixture],
    matches: Iterable[Match],
    predict: Callable[[Fixture], float],
    n_sims: int = 10_000,
    seed: int | None = None,
) -> tuple[SeriesOutlook, ...]:
    """One outlook per two-team series, in order of each series' first match.

    `predict(fixture)` is the chance that the fixture's team_a wins.
    """
    played = _played_by_key(matches)
    outlooks = []
    for series, games in _by_series(fixtures).items():
        if len({team for g in games for team in (g.team_a, g.team_b)}) != 2:
            continue
        outlook = _outlook(series, games, played, predict, n_sims, seed)
        if outlook is not None:
            outlooks.append(outlook)
    return tuple(outlooks)


def tri_series_outlooks(
    fixtures: Iterable[Fixture],
    matches: Iterable[Match],
    predict: Callable[[Fixture], float],
    n_sims: int = 10_000,
    seed: int | None = None,
) -> tuple[TriSeriesOutlook, ...]:
    """One outlook per series with three or more teams: group stage plus a final.

    The final is predicted at the venue of the last group match.
    """
    played = _played_by_key(matches)
    outlooks = []
    for series, games in _by_series(fixtures).items():
        teams = tuple(sorted({team for g in games for team in (g.team_a, g.team_b)}))
        if len(teams) < 3:
            continue
        group = [_group_match(g, played, predict) for g in games]
        n_played = sum(1 for g in games if _key(g) in played)
        last = games[-1]

        def final_probability(first: str, second: str, last: Fixture = last) -> float:
            return predict(replace(last, team_a=first, team_b=second, match_no=0))

        forecast = simulate_tri_series(group, final_probability, n_sims=n_sims, seed=seed)
        outlooks.append(TriSeriesOutlook(series, teams, n_played, len(games) - n_played, forecast))
    return tuple(outlooks)


def _group_match(
    game: Fixture, played: Mapping[MatchKey, Match], predict: Callable[[Fixture], float]
) -> GroupMatch:
    match = played.get(_key(game))
    if match is None:
        return GroupMatch(game.team_a, game.team_b, predict(game))
    actual = actual_score(match, game.team_a)
    if actual in (1.0, 0.0):
        return GroupMatch(game.team_a, game.team_b, actual)
    # A washout or a tie: one point each in the table.
    return GroupMatch(game.team_a, game.team_b, 0.5, no_result=True)


def _by_series(fixtures: Iterable[Fixture]) -> dict[str, list[Fixture]]:
    """Fixtures grouped by series, each in date order, series in order of first match."""
    by_series: dict[str, list[Fixture]] = {}
    for fixture in sorted(fixtures, key=lambda f: (f.date, f.match_no)):
        by_series.setdefault(fixture.series, []).append(fixture)
    return by_series


def _played_by_key(matches: Iterable[Match]) -> dict[MatchKey, Match]:
    return {(m.date, frozenset((m.team_a, m.team_b))): m for m in matches}


def _key(fixture: Fixture) -> MatchKey:
    return fixture.date, frozenset((fixture.team_a, fixture.team_b))


def _outlook(
    series: str,
    games: list[Fixture],
    played: Mapping[MatchKey, Match],
    predict: Callable[[Fixture], float],
    n_sims: int,
    seed: int | None,
) -> SeriesOutlook | None:
    team_a, team_b = games[0].team_a, games[0].team_b
    probabilities: list[float] = []
    a_wins = b_wins = remaining = 0
    for game in games:
        match = played.get(_key(game))
        if match is None:
            p = predict(game)
            probabilities.append(p if game.team_a == team_a else 1 - p)
            remaining += 1
            continue
        actual = actual_score(match, team_a)
        if actual in (1.0, 0.0):  # ties and washouts count for nobody
            probabilities.append(actual)
            a_wins += actual == 1.0
            b_wins += actual == 0.0
    if not probabilities:
        return None
    forecast = simulate_series(probabilities, n_sims=n_sims, seed=seed)
    return SeriesOutlook(series, team_a, team_b, (a_wins, b_wins), remaining, forecast)
