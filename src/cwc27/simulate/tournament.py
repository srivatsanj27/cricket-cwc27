"""Monte Carlo simulation of the 2027 Men's Cricket World Cup, Qualifier included.

Format (ICC, July 2026):
- Qualifier: the winner goes straight to the group stage. Its format isn't published yet,
  so it is simulated as a single round robin.
- Super Series: the Qualifier's 2nd to 4th play a round robin; the winner joins a group.
- Group stage: two groups of six, each a single round robin.
- Super 7: the top three of each group plus the better fourth-placed side. A fresh round
  robin, with no points carried over.
- Semi-finals 1 v 4 and 2 v 3, then the final.

Tables are ranked on points, then wins, then net run rate. With no washouts simulated,
wins follow from points, and a random draw stands in for net run rate.

Ratings for a tournament months away are uncertain, so `elo_predictors` blurs each team's
rating with one random draw per simulated tournament (see cwc27.evaluation.horizon).
"""

import random
import tomllib
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from functools import cache
from itertools import combinations
from pathlib import Path
from types import MappingProxyType

from cwc27.ratings.elo import initial_rating
from cwc27.ratings.model import EloModel
from cwc27.simulate.multiseries import WIN_POINTS, rank_teams

QUALIFIER_WINNER = "Qualifier winner"  # group slot filled by the Qualifier winner
SUPER_SERIES_WINNER = "Super Series winner"  # group slot filled by the Super Series winner
SUPER_SERIES_SIZE = 3
PER_GROUP = 3  # straight into the Super 7 from each group, before the best fourth
SEMI_FINALISTS = 4
FORMAT_TOML = Path(__file__).resolve().parents[3] / "config" / "wc2027_format.toml"

STAGES = ("group_stage", "super7", "semi_final", "final", "champion")
Predict = Callable[[str, str], float]  # chance that the first team beats the second
# One simulated tournament's predictors: (from the Super Series on, for the Qualifier).
Predictors = Callable[[random.Random], tuple[Predict, Predict]]


@dataclass(frozen=True, slots=True)
class WorldCupFormat:
    start: date  # first day of the tournament proper
    groups: tuple[tuple[str, ...], ...]  # group A, group B, with the two slots to fill
    qualifier: tuple[str, ...]
    hosts: tuple[str, ...]  # home advantage from the Super Series on
    qualifier_hosts: tuple[str, ...] = ()  # home advantage in the Qualifier


@dataclass(frozen=True, slots=True)
class TeamOdds:
    """Chance of reaching each stage (and of winning the cup)."""

    group_stage: float
    super7: float
    semi_final: float
    final: float
    champion: float


def load_format(path: Path | None = None) -> WorldCupFormat:
    """The format config. Raises ValueError if it is incomplete or inconsistent."""
    path = path or FORMAT_TOML
    with path.open("rb") as f:
        raw = tomllib.load(f)
    try:
        qualifier = raw["qualifier"]
        fmt = WorldCupFormat(
            start=_date(raw["start"]),
            groups=tuple(_names(raw["groups"][name], f"group {name}") for name in ("A", "B")),
            qualifier=_names(qualifier["teams"], "qualifier teams"),
            hosts=_names(raw["hosts"], "hosts"),
            qualifier_hosts=_names(qualifier.get("hosts", []), "qualifier hosts"),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"{path.name}: missing or malformed {exc}") from exc
    _validate_format(fmt, path.name)
    return fmt


def _date(value: object) -> date:
    if not isinstance(value, date):
        raise ValueError("start must be a date like 2027-10-02")
    return value


def _names(value: object, what: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ValueError(f"{what} must be a list of team names")
    return tuple(value)


def _validate_format(fmt: WorldCupFormat, where: str) -> None:
    named = [team for group in fmt.groups for team in group] + list(fmt.qualifier)
    repeats = sorted({team for team in named if named.count(team) > 1})
    if repeats:
        raise ValueError(f"{where}: {', '.join(repeats)} named more than once")
    for slot in (QUALIFIER_WINNER, SUPER_SERIES_WINNER):
        if slot not in named:
            raise ValueError(f"{where}: no group has a {slot!r} slot")
    if any(len(group) <= PER_GROUP for group in fmt.groups):
        raise ValueError(f"{where}: each group needs at least {PER_GROUP + 1} teams")
    if len(fmt.qualifier) < 1 + SUPER_SERIES_SIZE:
        raise ValueError(f"{where}: the qualifier needs at least four teams")


def host_predictor(
    predict: Callable[[str, str, str | None], float], hosts: Sequence[str]
) -> Predict:
    """Hosts play at home, except against another host (venue unknown, so neutral)."""

    def play(team_a: str, team_b: str) -> float:
        home = [team for team in (team_a, team_b) if team in hosts]
        return predict(team_a, team_b, home[0] if len(home) == 1 else None)

    return play


def fixed_predictors(predict: Predict, qualifier_predict: Predict | None = None) -> Predictors:
    """The same predictors in every simulation (the Qualifier's default to `predict`)."""
    pair = (cache(predict), cache(qualifier_predict or predict))
    return lambda rng: pair


def elo_predictors(model: EloModel, fmt: WorldCupFormat, rating_sd: float) -> Predictors:
    """Per simulation, every rating moves by a normal draw with spread `rating_sd`."""
    if rating_sd < 0:
        raise ValueError(f"rating_sd must not be negative, got {rating_sd}")
    teams = _teams(fmt)

    def draw(rng: random.Random) -> tuple[Predict, Predict]:
        ratings = {
            t: model.ratings.get(t, initial_rating(t, model.config)) + rng.gauss(0.0, rating_sd)
            for t in teams
        }
        drawn = EloModel(model.config, MappingProxyType(ratings))
        return (
            cache(host_predictor(drawn.predict, fmt.hosts)),
            cache(host_predictor(drawn.predict, fmt.qualifier_hosts)),
        )

    return draw


def simulate_world_cup(
    fmt: WorldCupFormat, predictors: Predictors, n_sims: int = 10_000, seed: int | None = None
) -> Mapping[str, TeamOdds]:
    """Play the whole event `n_sims` times; each team's chance of reaching each stage."""
    if n_sims < 1:
        raise ValueError(f"n_sims must be at least 1, got {n_sims}")
    rng = random.Random(seed)
    reached = {stage: Counter[str]() for stage in STAGES}
    for _ in range(n_sims):
        p, pq = predictors(rng)
        for stage, teams in _one_cup(fmt, p, pq, rng).items():
            reached[stage].update(teams)
    return MappingProxyType(
        {t: TeamOdds(*(reached[stage][t] / n_sims for stage in STAGES)) for t in _teams(fmt)}
    )


def _teams(fmt: WorldCupFormat) -> list[str]:
    slots = {QUALIFIER_WINNER, SUPER_SERIES_WINNER}
    return sorted(({t for g in fmt.groups for t in g} - slots) | set(fmt.qualifier))


def _one_cup(
    fmt: WorldCupFormat, p: Predict, pq: Predict, rng: random.Random
) -> dict[str, Sequence[str]]:
    """One simulated tournament: who reached each stage."""
    qualifier, _ = _round_robin(fmt.qualifier, pq, rng)
    super_series, _ = _round_robin(qualifier[1 : 1 + SUPER_SERIES_SIZE], p, rng)
    slots = {QUALIFIER_WINNER: qualifier[0], SUPER_SERIES_WINNER: super_series[0]}
    groups = [[slots.get(team, team) for team in group] for group in fmt.groups]
    tables = [_round_robin(group, p, rng) for group in groups]
    fourths = {ranked[PER_GROUP]: points[ranked[PER_GROUP]] for ranked, points in tables}
    super7 = [team for ranked, _ in tables for team in ranked[:PER_GROUP]]
    super7.append(rank_teams(fourths, {}, rng)[0])
    semis = _round_robin(super7, p, rng)[0][:SEMI_FINALISTS]
    finalists = (_play(semis[0], semis[3], p, rng), _play(semis[1], semis[2], p, rng))
    return {
        "group_stage": [team for group in groups for team in group],
        "super7": super7,
        "semi_final": semis,
        "final": finalists,
        "champion": (_play(*finalists, p, rng),),
    }


def _round_robin(
    teams: Sequence[str], p: Predict, rng: random.Random
) -> tuple[list[str], dict[str, int]]:
    """Everyone plays everyone once: the table, best first, and the points."""
    points = dict.fromkeys(teams, 0)
    for team_a, team_b in combinations(teams, 2):
        points[_play(team_a, team_b, p, rng)] += WIN_POINTS
    return rank_teams(points, {}, rng), points


def _play(team_a: str, team_b: str, p: Predict, rng: random.Random) -> str:
    return team_a if rng.random() < p(team_a, team_b) else team_b
