"""Player ratings: runs above an average player per 100 balls, for batting and bowling.

Method, per ball:
    batting value = (runs - average runs) - wicket_value * (out - average out rate)
    bowling value = (average runs - conceded) + wicket_value * (wicket - average wicket rate)
Each ball is weighted by recency, and the weighted total is shrunk towards average:
    rating per 100 balls = 100 * sum(weight * value) / (sum(weight) + prior_balls)
"""

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from types import MappingProxyType

from cwc27.players.balls import (
    BowledBall,
    FacedBall,
    PhaseAverage,
    bowled_averages,
    bowled_opponent_averages,
    faced_averages,
    faced_opponent_averages,
)


@dataclass(frozen=True, slots=True)
class RatingConfig:
    wicket_value: float = 25.0  # runs a wicket is worth (lambda)
    half_life_days: float = 365.0  # a ball this many days old counts half (H)
    prior_balls: float = 300.0  # balls of exactly average play added to everyone (k)
    # Judge each ball against what everyone did against the same opponent in that phase,
    # so wickets against weak line-ups (and runs against weak attacks) count for less.
    opponent_adjusted: bool = True


@dataclass(frozen=True, slots=True)
class PlayerRating:
    player_id: str
    name: str  # the most recent name the player appeared under
    batting: float  # runs above average per 100 balls faced (0.0 if never batted)
    bowling: float  # runs saved against average per 100 balls bowled (0.0 if never bowled)
    balls_faced: int  # raw count, not weighted
    balls_bowled: int  # raw count, not weighted
    last_played: date  # latest match date they batted or bowled in


def recency_weight(match_date: date, as_of: date, half_life_days: float) -> float:
    """0.5 ** (days between match_date and as_of / half_life_days); 1.0 on as_of itself."""
    days = (as_of - match_date).days
    if days < 0:
        raise ValueError(f"match on {match_date} is after the rating date {as_of}")
    return 0.5 ** (days / half_life_days)


def batting_value(ball: FacedBall, average: PhaseAverage, wicket_value: float) -> float:
    """Runs this ball was worth to the batter, compared with an average batter in its phase."""
    return (ball.runs - average.runs) - wicket_value * (int(ball.out) - average.wickets)


def bowling_value(ball: BowledBall, average: PhaseAverage, wicket_value: float) -> float:
    """Runs this ball was worth to the bowler, compared with an average bowler in its phase."""
    return (average.runs - ball.conceded) + wicket_value * (int(ball.wicket) - average.wickets)


def shrunk_per_100(weighted_value: float, weight: float, prior_balls: float) -> float:
    """100 * weighted_value / (weight + prior_balls); 0.0 when there's nothing to divide by."""
    denominator = weight + prior_balls
    return 100 * weighted_value / denominator if denominator > 0 else 0.0


@dataclass(slots=True)
class _Totals:
    """Running totals for one player while rating. Local to rate_players; never returned."""

    name: str = ""
    latest: date = date.min
    bat_value: float = 0.0
    bat_weight: float = 0.0
    balls_faced: int = 0
    bowl_value: float = 0.0
    bowl_weight: float = 0.0
    balls_bowled: int = 0

    def seen(self, name: str, day: date) -> None:
        if day >= self.latest:
            self.name, self.latest = name, day


def rate_players(
    faced: Iterable[FacedBall],
    bowled: Iterable[BowledBall],
    config: RatingConfig,
    as_of: date,
) -> Mapping[str, PlayerRating]:
    """One PlayerRating per player id who batted or bowled, keyed by player id.

    Players are matched by id (names can change); the latest name and date seen are kept.
    """
    faced, bowled = tuple(faced), tuple(bowled)
    bat_average = _average_for(faced, faced_averages, faced_opponent_averages, config)
    bowl_average = _average_for(bowled, bowled_averages, bowled_opponent_averages, config)
    totals: dict[str, _Totals] = {}

    for ball in faced:
        t = totals.setdefault(ball.batter_id, _Totals())
        weight = recency_weight(ball.date, as_of, config.half_life_days)
        value = batting_value(ball, bat_average(ball), config.wicket_value)
        t.bat_value += weight * value
        t.bat_weight += weight
        t.balls_faced += 1
        t.seen(ball.batter, ball.date)

    for ball in bowled:
        t = totals.setdefault(ball.bowler_id, _Totals())
        weight = recency_weight(ball.date, as_of, config.half_life_days)
        value = bowling_value(ball, bowl_average(ball), config.wicket_value)
        t.bowl_value += weight * value
        t.bowl_weight += weight
        t.balls_bowled += 1
        t.seen(ball.bowler, ball.date)

    return MappingProxyType({pid: _rating(pid, t, config) for pid, t in totals.items()})


def _average_for[B: (FacedBall, BowledBall)](
    balls: tuple[B, ...],
    by_phase: Callable[[Iterable[B]], Mapping[str, PhaseAverage]],
    by_opponent: Callable[[Iterable[B]], Mapping[tuple[str, str], PhaseAverage]],
    config: RatingConfig,
) -> Callable[[B], PhaseAverage]:
    """The average a ball is judged against: same opponent and phase, else same phase."""
    if not balls:
        return lambda ball: PhaseAverage(0.0, 0.0)
    phase = by_phase(balls)
    if not config.opponent_adjusted:
        return lambda ball: phase[ball.phase]
    opponent = by_opponent(balls)
    return lambda ball: opponent.get((ball.opponent, ball.phase), phase[ball.phase])


def _rating(player_id: str, t: _Totals, config: RatingConfig) -> PlayerRating:
    batting = shrunk_per_100(t.bat_value, t.bat_weight, config.prior_balls)
    bowling = shrunk_per_100(t.bowl_value, t.bowl_weight, config.prior_balls)
    return PlayerRating(
        player_id=player_id,
        name=t.name,
        batting=batting if t.balls_faced else 0.0,
        bowling=bowling if t.balls_bowled else 0.0,
        balls_faced=t.balls_faced,
        balls_bowled=t.balls_bowled,
        last_played=t.latest,
    )
