"""How uncertain is a team's Elo for a match a long way ahead?

Predict each past match from ratings frozen `horizon_days` before it, with each side's
rating blurred by a normal spread of `sd` Elo points, and score the predictions. The
spread that scores best is how far ratings typically drift over that horizon, which is the
uncertainty to add when simulating a tournament that far away.
"""

import math
from bisect import bisect_left
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from statistics import NormalDist

from cwc27.evaluation.metrics import brier_score, log_loss
from cwc27.models import Match
from cwc27.ratings.elo import EloConfig, actual_score, expected_score, update

# Fitted on 2010-2022 with `horizon_scores`, confirmed on matches since 2023: the best blur
# is about 60 Elo points even for tomorrow's match, and about 100 a year ahead.
BASE_RATING_SD = 60.0
YEARLY_DRIFT_SD = 80.0  # sqrt(100^2 - 60^2): extra spread built up over a year
DAYS_PER_YEAR = 365.25
QUADRATURE_POINTS = 41  # normal quantiles used to average over the blur
_QUANTILES = tuple(
    NormalDist().inv_cdf((i + 0.5) / QUADRATURE_POINTS) for i in range(QUADRATURE_POINTS)
)


@dataclass(frozen=True, slots=True)
class RatingHistory:
    dates: tuple[date, ...]  # date of each match, in order
    ratings: tuple[Mapping[str, float], ...]  # ratings after that match


@dataclass(frozen=True, slots=True)
class HorizonScore:
    matches: int
    brier: float
    log_loss: float


def rating_sd(days_ahead: int) -> float:
    """How uncertain a rating is `days_ahead` days out (drift adds up like a random walk)."""
    years = max(days_ahead, 0) / DAYS_PER_YEAR
    return math.sqrt(BASE_RATING_SD**2 + YEARLY_DRIFT_SD**2 * years)


def blurred_probability(rating_a: float, rating_b: float, sd: float, scale: float = 400.0) -> float:
    """Chance team a wins when each rating is only known to within a normal spread `sd`."""
    if sd < 0:
        raise ValueError(f"sd must not be negative, got {sd}")
    gap_sd = sd * math.sqrt(2)  # the gap between two independent ratings
    total = sum(expected_score(rating_a + z * gap_sd, rating_b, scale) for z in _QUANTILES)
    return total / QUADRATURE_POINTS


def rating_history(
    matches: Iterable[Match], config: EloConfig, home_of: Callable[[Match], str | None]
) -> RatingHistory:
    """Elo ratings after every match, in date order."""
    ordered = sorted(matches, key=lambda m: m.date)
    snapshots: list[Mapping[str, float]] = []
    ratings: Mapping[str, float] = {}
    for match in ordered:
        ratings = update(ratings, match, config, home_of(match))
        snapshots.append(ratings)
    return RatingHistory(tuple(m.date for m in ordered), tuple(snapshots))


def ratings_before(history: RatingHistory, day: date) -> Mapping[str, float]:
    """Ratings from every match before `day` (none on the day itself)."""
    played = bisect_left(history.dates, day)
    return history.ratings[played - 1] if played else {}


def horizon_scores(
    matches: Sequence[Match],
    config: EloConfig,
    home_of: Callable[[Match], str | None],
    horizon_days: int,
    sds: Iterable[float],
    since: date,
) -> dict[float, HorizonScore]:
    """Score predictions of matches from `since` on, made `horizon_days` ahead, per blur.

    `matches` can be in any order. Matches without a result, or with a side unrated at
    the time, are skipped.
    """
    history = rating_history(matches, config, home_of)
    gaps: list[float] = []  # team a's rating edge, home advantage included
    outcomes: list[float] = []
    for match in matches:
        outcome = actual_score(match, match.team_a)
        if match.date < since or outcome is None:
            continue
        frozen = ratings_before(history, match.date - timedelta(days=horizon_days))
        if match.team_a not in frozen or match.team_b not in frozen:
            continue
        home = home_of(match)
        bonus = {match.team_a: config.home_advantage, match.team_b: -config.home_advantage}
        gaps.append(frozen[match.team_a] - frozen[match.team_b] + bonus.get(home, 0.0))
        outcomes.append(outcome)
    scores = {}
    for sd in sds:
        probabilities = [blurred_probability(gap, 0.0, sd, config.scale) for gap in gaps]
        scores[sd] = HorizonScore(
            len(outcomes), brier_score(probabilities, outcomes), log_loss(probabilities, outcomes)
        )
    return scores
