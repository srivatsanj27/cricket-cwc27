"""Monte Carlo simulation of a bilateral ODI series.

YOUR TASK (plan 1.8): implement `simulate_series` so `pytest tests/test_series.py` passes.
"""

import random
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SeriesForecast:
    """Outcome probabilities for one series, from team A's point of view.

    `scorelines` maps (A's wins, B's wins) to its probability, e.g. {(2, 1): 0.43, ...},
    and only includes scorelines that happened in at least one simulation.
    Every match is played (dead rubbers included), so A's wins + B's wins == n_matches.
    """

    n_matches: int
    scorelines: Mapping[tuple[int, int], float]
    p_a_wins_series: float
    p_b_wins_series: float
    p_drawn_series: float  # only possible when n_matches is even, e.g. 1-1 or 2-2


def simulate_series(
    match_probabilities: Sequence[float],
    n_sims: int = 10_000,
    seed: int | None = None,
) -> SeriesForecast:
    """Play the series `n_sims` times and count how often each scoreline happens.

    `match_probabilities[i]` is the chance that team A wins match i (e.g. from
    `win_probability`, with the right home side for that venue). Matches are treated as
    independent, and every match has a winner (ties and washouts are ignored for now).

    Use `random.Random(seed)` so the same seed always gives the same forecast.

    Raise ValueError if there are no matches, any probability is outside 0-1, or n_sims < 1.
    """
    if match_probabilities == []:
        raise ValueError("No matches to simulate!")
    if any(p < 0 or p > 1 for p in match_probabilities):
        raise ValueError("Match probabilities must be between 0 and 1!")
    if n_sims < 1:
        raise ValueError("Must simulate at least one series!")
    rng = random.Random(seed)
    tally = Counter()
    for _ in range(n_sims):
        a_wins = 0
        for p in match_probabilities:
            if rng.random() < p:
                a_wins += 1
        tally[(a_wins, len(match_probabilities) - a_wins)] += 1
    scorelines = {scoreline: count / n_sims for scoreline, count in tally.items()}
    p_a_wins_series = sum(count for (a, b), count in tally.items() if a > b) / n_sims
    p_b_wins_series = sum(count for (a, b), count in tally.items() if b > a) / n_sims
    p_drawn_series = sum(count for (a, b), count in tally.items() if a == b) / n_sims
    return SeriesForecast(
        n_matches=len(match_probabilities),
        scorelines=scorelines,
        p_a_wins_series=p_a_wins_series,
        p_b_wins_series=p_b_wins_series,
        p_drawn_series=p_drawn_series,
    )
