"""Monte Carlo simulation of a round robin followed by a final (e.g. an ODI tri-series)."""

import random
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from itertools import groupby

WIN_POINTS = 2
NO_RESULT_POINTS = 1  # each side, for a washout


@dataclass(frozen=True, slots=True)
class GroupMatch:
    """One round-robin match.

    `p_team_a` is team_a's chance of winning: use 1.0 or 0.0 for a match already played.
    For a washout already played, set `no_result=True` (p_team_a is then ignored).
    """

    team_a: str
    team_b: str
    p_team_a: float
    no_result: bool = False


@dataclass(frozen=True, slots=True)
class TriSeriesForecast:
    """Per-team probabilities. Every team appears in both maps, even with 0.0."""

    p_reach_final: Mapping[str, float]  # values sum to 2.0 (two finalists)
    p_win: Mapping[str, float]  # values sum to 1.0


def rank_teams(
    points: Mapping[str, int],
    wins_against: Mapping[tuple[str, str], int],
    rng: random.Random,
) -> list[str]:
    """Order teams for the points table, best first.

    Ties on points are broken by wins in matches between the tied teams, then by a random
    draw. The draw stands in for net run rate, which this model doesn't simulate.
    `wins_against[(x, y)]` is how many times x beat y.
    """
    ordered: list[str] = []
    by_points = sorted(points, key=lambda team: -points[team])
    for _, tied in groupby(by_points, key=lambda team: points[team]):
        group = sorted(tied)  # sorted so the random draw is reproducible for a given seed
        head_to_head = {
            team: sum(wins_against.get((team, other), 0) for other in group if other != team)
            for team in group
        }
        draw = {team: rng.random() for team in group}
        ordered += sorted(group, key=lambda team: (-head_to_head[team], draw[team]))
    return ordered


def simulate_tri_series(
    group_matches: Sequence[GroupMatch],
    final_probability: Callable[[str, str], float],
    n_sims: int = 10_000,
    seed: int | None = None,
) -> TriSeriesForecast:
    """Play the round robin and final `n_sims` times; count finalists and winners.

    Each simulation plays every group match, ranks the table with `rank_teams`, then plays
    the final between the top two. `final_probability(first, second)` is the chance the
    first-placed team wins it. One seeded generator drives every draw, so the same seed
    gives the same forecast.

    Raises ValueError if there are fewer than two teams, a team plays itself, any
    p_team_a is outside 0-1, or n_sims < 1.
    """
    _validate(group_matches, n_sims)
    teams = sorted({team for m in group_matches for team in (m.team_a, m.team_b)})
    rng = random.Random(seed)
    finals: Counter[str] = Counter()
    winners: Counter[str] = Counter()

    for _ in range(n_sims):
        points, wins_against = _play_group(group_matches, teams, rng)
        first, second = rank_teams(points, wins_against, rng)[:2]
        finals.update((first, second))
        winners[first if rng.random() < final_probability(first, second) else second] += 1

    return TriSeriesForecast(
        p_reach_final={team: finals[team] / n_sims for team in teams},
        p_win={team: winners[team] / n_sims for team in teams},
    )


def _validate(group_matches: Sequence[GroupMatch], n_sims: int) -> None:
    if n_sims < 1:
        raise ValueError(f"n_sims must be at least 1, got {n_sims}")
    if not group_matches:
        raise ValueError("no group matches to simulate")
    for match in group_matches:
        if match.team_a == match.team_b:
            raise ValueError(f"a team cannot play itself: {match.team_a!r}")
        if not 0.0 <= match.p_team_a <= 1.0:
            raise ValueError(f"p_team_a must be between 0 and 1, got {match.p_team_a}")


def _play_group(
    group_matches: Sequence[GroupMatch], teams: Sequence[str], rng: random.Random
) -> tuple[dict[str, int], Counter[tuple[str, str]]]:
    """One simulated group stage: points per team, and who beat whom."""
    points = dict.fromkeys(teams, 0)
    wins_against: Counter[tuple[str, str]] = Counter()
    for match in group_matches:
        if match.no_result:
            points[match.team_a] += NO_RESULT_POINTS
            points[match.team_b] += NO_RESULT_POINTS
            continue
        a_wins = rng.random() < match.p_team_a
        winner, loser = (match.team_a, match.team_b) if a_wins else (match.team_b, match.team_a)
        points[winner] += WIN_POINTS
        wins_against[(winner, loser)] += 1
    return points, wins_against
