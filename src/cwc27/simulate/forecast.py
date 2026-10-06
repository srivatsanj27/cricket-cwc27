"""Series outlooks: results so far are certain, the remaining matches are simulated."""

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import date

from cwc27.fixtures import Fixture
from cwc27.models import Match
from cwc27.ratings.elo import actual_score
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


def series_outlooks(
    fixtures: Iterable[Fixture],
    matches: Iterable[Match],
    predict: Callable[[Fixture], float],
    n_sims: int = 10_000,
    seed: int | None = None,
) -> tuple[SeriesOutlook, ...]:
    """One outlook per two-team series, in order of each series' first match.

    `predict(fixture)` is the chance that the fixture's team_a wins. Series with more than
    two teams (tri-series) are skipped until the tri-series simulator exists.
    """
    played = {(m.date, frozenset((m.team_a, m.team_b))): m for m in matches}
    by_series: dict[str, list[Fixture]] = {}
    for fixture in sorted(fixtures, key=lambda f: (f.date, f.match_no)):
        by_series.setdefault(fixture.series, []).append(fixture)

    outlooks = []
    for series, games in by_series.items():
        if len({team for g in games for team in (g.team_a, g.team_b)}) != 2:
            continue
        outlook = _outlook(series, games, played, predict, n_sims, seed)
        if outlook is not None:
            outlooks.append(outlook)
    return tuple(outlooks)


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
        match = played.get((game.date, frozenset((game.team_a, game.team_b))))
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
