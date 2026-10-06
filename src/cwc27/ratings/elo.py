"""Team Elo ratings.

Standard Elo (https://en.wikipedia.org/wiki/Elo_rating_system) with a home-advantage
term. Functions are pure: they never modify the `ratings` mapping they are given.
"""

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

from cwc27.models import Match, ResultType
from cwc27.teams import is_full_member


@dataclass(frozen=True, slots=True)
class EloConfig:
    k: float = 25.0  # how far one result moves a rating
    home_advantage: float = 80.0  # Elo points added to the home side's rating when predicting
    initial_full_member: float = 1500.0
    initial_associate: float = 1300.0
    scale: float = 400.0  # a gap of `scale` points means 10:1 odds


def initial_rating(team: str, config: EloConfig) -> float:
    """Starting rating for a team never seen before: full members start higher than associates."""
    if is_full_member(team):
        return config.initial_full_member
    else:
        return config.initial_associate


def expected_score(rating_a: float, rating_b: float, scale: float = 400.0) -> float:
    """Probability that A beats B: 1 / (1 + 10 ** ((rating_b - rating_a) / scale))."""
    return 1 / (1 + 10 ** ((rating_b - rating_a) / scale))


def actual_score(match: Match, team: str) -> float | None:
    """1.0 for a win (including DLS), 0.0 for a loss, 0.5 for a tie, None for no result.

    Raises ValueError if `team` didn't play in `match`.
    """
    if team != match.team_a and team != match.team_b:
        raise ValueError(f"{team} did not play in {match}")
    if match.result_type == ResultType.NO_RESULT:
        return None
    if match.result_type == ResultType.TIE:
        return 0.5
    if team == match.winner:
        return 1.0
    else:
        return 0.0


def win_probability(
    ratings: Mapping[str, float],
    team_a: str,
    team_b: str,
    config: EloConfig,
    home: str | None = None,
) -> float:
    """Probability that team_a beats team_b, before the match is played.

    - Teams missing from `ratings` use `initial_rating`.
    - The `home` side (if any) gets `config.home_advantage` added; use `config.scale`.
    - Raise ValueError if team_a == team_b, or if `home` is set but isn't one of them.
    """
    if team_a == team_b:
        raise ValueError(f"A team cannot play itself: {team_a!r}!")
    if home is not None and home not in (team_a, team_b):
        raise ValueError(f"The home team {home!r} is not {team_a!r} or {team_b!r}!")

    rating_a = ratings.get(team_a, initial_rating(team_a, config))
    rating_b = ratings.get(team_b, initial_rating(team_b, config))

    predict_a = rating_a + (config.home_advantage if home == team_a else 0.0)
    predict_b = rating_b + (config.home_advantage if home == team_b else 0.0)

    return expected_score(predict_a, predict_b, config.scale)


def update(
    ratings: Mapping[str, float],
    match: Match,
    config: EloConfig,
    home: str | None = None,
) -> dict[str, float]:
    """Return new ratings after `match`.

    - Teams missing from `ratings` start at `initial_rating`.
    - The `home` side (if any) gets `config.home_advantage` added to its rating
      when computing the expected score only; the bonus is not stored.
    - Each side moves by k * (actual - expected); the two changes cancel out.
    - No result: ratings are unchanged (but still return a new dict).
    """
    team_a, team_b = match.team_a, match.team_b
    rating_a = ratings.get(team_a, initial_rating(team_a, config))
    rating_b = ratings.get(team_b, initial_rating(team_b, config))

    actual_a = actual_score(match, team_a)
    if actual_a is None:
        return dict(ratings)  # a new dict, unchanged

    expected_a = win_probability(ratings, team_a, team_b, config, home)
    delta = config.k * (actual_a - expected_a)

    new_ratings = dict(ratings)  # a copy of ratings
    new_ratings[team_a] = rating_a + delta
    new_ratings[team_b] = rating_b - delta
    return new_ratings


def run_elo(
    matches: Iterable[Match],
    config: EloConfig,
    home_of: Callable[[Match], str | None],
) -> dict[str, float]:
    """Rate every match in date order (whatever order they're given in); return final ratings.

    `home_of(match)` returns the home team or None (see cwc27.venues.home_team).
    """
    sorted_matches = sorted(matches, key=lambda m: m.date)  # sort by date
    ratings = {}
    for match in sorted_matches:
        home = home_of(match)
        ratings = update(ratings, match, config, home)
    return ratings
