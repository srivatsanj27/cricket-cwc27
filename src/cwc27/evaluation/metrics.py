"""Scoring rules for probabilistic match predictions.

Each function takes parallel sequences: the predicted probability that team A wins,
and what happened for team A (1.0 win, 0.0 loss, 0.5 tie).
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass

# Clip probabilities so a confident wrong prediction costs a lot, not infinity.
LOG_LOSS_EPSILON = 1e-15
CALIBRATION_BIN_WIDTH = 0.1
VALID_OUTCOMES = frozenset({0.0, 0.5, 1.0})


@dataclass(frozen=True, slots=True)
class Summary:
    n: int
    brier: float
    log_loss: float
    accuracy: float


@dataclass(frozen=True, slots=True)
class CalibrationBin:
    lower: float
    upper: float
    count: int
    mean_predicted: float
    observed_rate: float


def brier_score(probabilities: Sequence[float], outcomes: Sequence[float]) -> float:
    """Mean squared error of the probabilities: 0 is perfect, 0.25 is a coin flip."""
    _validate(probabilities, outcomes)
    return sum((p - y) ** 2 for p, y in zip(probabilities, outcomes, strict=True)) / len(outcomes)


def log_loss(probabilities: Sequence[float], outcomes: Sequence[float]) -> float:
    """Mean negative log-likelihood: punishes confident mistakes hard. ln 2 is a coin flip."""
    _validate(probabilities, outcomes)
    total = 0.0
    for p, y in zip(probabilities, outcomes, strict=True):
        p = min(max(p, LOG_LOSS_EPSILON), 1 - LOG_LOSS_EPSILON)
        total -= y * math.log(p) + (1 - y) * math.log(1 - p)
    return total / len(outcomes)


def accuracy(probabilities: Sequence[float], outcomes: Sequence[float]) -> float:
    """Share of decided matches the favourite won (ties skipped; a 50/50 call gets half)."""
    _validate(probabilities, outcomes)
    decided = [(p, y) for p, y in zip(probabilities, outcomes, strict=True) if y != 0.5]
    if not decided:
        return math.nan
    credit = sum(0.5 if p == 0.5 else float((p > 0.5) == (y == 1.0)) for p, y in decided)
    return credit / len(decided)


def calibration_table(
    probabilities: Sequence[float], outcomes: Sequence[float]
) -> tuple[CalibrationBin, ...]:
    """Bucket predictions by the favourite's probability (0.5-0.6, ..., 0.9-1.0).

    In a well-calibrated model, favourites at ~70% win ~70% of the time.
    Ties count as half a win for the favourite; an exact 50/50 call counts team A as favourite.
    """
    _validate(probabilities, outcomes)
    favourite = [
        (p, y) if p >= 0.5 else (1 - p, 1 - y) for p, y in zip(probabilities, outcomes, strict=True)
    ]
    n_bins = round(0.5 / CALIBRATION_BIN_WIDTH)
    bins = []
    for i in range(n_bins):
        lower = round(0.5 + i * CALIBRATION_BIN_WIDTH, 10)
        upper = round(lower + CALIBRATION_BIN_WIDTH, 10)
        last = i == n_bins - 1
        members = [(p, y) for p, y in favourite if lower <= p < upper or (last and p == upper)]
        count = len(members)
        bins.append(
            CalibrationBin(
                lower=lower,
                upper=upper,
                count=count,
                mean_predicted=sum(p for p, _ in members) / count if count else math.nan,
                observed_rate=sum(y for _, y in members) / count if count else math.nan,
            )
        )
    return tuple(bins)


def summarise(probabilities: Sequence[float], outcomes: Sequence[float]) -> Summary:
    """All scores at once. ValueError on empty or invalid input; accuracy is NaN if all ties."""
    return Summary(
        n=len(outcomes),
        brier=brier_score(probabilities, outcomes),
        log_loss=log_loss(probabilities, outcomes),
        accuracy=accuracy(probabilities, outcomes),
    )


def _validate(probabilities: Sequence[float], outcomes: Sequence[float]) -> None:
    if not outcomes:
        raise ValueError("no predictions to score")
    if len(probabilities) != len(outcomes):
        raise ValueError(f"{len(probabilities)} probabilities but {len(outcomes)} outcomes")
    if any(not 0.0 <= p <= 1.0 for p in probabilities):
        raise ValueError("probabilities must be between 0 and 1")
    if any(y not in VALID_OUTCOMES for y in outcomes):
        raise ValueError("outcomes must be 1.0 (win), 0.0 (loss) or 0.5 (tie)")
