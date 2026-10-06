"""Grid search over Elo settings: tune on one period, confirm on a later one.

Picking settings by their score on the same matches you report would flatter the model,
so the best setting is chosen on the tuning segment only and then checked on the
confirmation segment, which it never saw during selection.
"""

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, replace
from datetime import date
from itertools import product

from cwc27.config import WINDOW_START
from cwc27.evaluation.backtest import score, walk_forward
from cwc27.evaluation.metrics import Summary
from cwc27.evaluation.report import Segment
from cwc27.models import Match
from cwc27.ratings.elo import EloConfig
from cwc27.ratings.model import EloModel

# 2019-2020 warm the ratings up; 2021 to the 2023 final is scored for tuning.
TUNE_START = date(2021, 1, 1)
TUNE_SEGMENT = Segment("2021 to 2023 WC final", lambda m: TUNE_START <= m.date < WINDOW_START)
CONFIRM_SEGMENT = Segment("since 2023 WC final", lambda m: m.date >= WINDOW_START)
DEFAULT_CONFIG = EloConfig()


@dataclass(frozen=True, slots=True)
class TuningResult:
    config: EloConfig
    tune: Summary
    confirm: Summary | None


def grid_search(
    matches: Iterable[Match],
    home_of: Callable[[Match], str | None],
    k_values: Sequence[float],
    home_values: Sequence[float],
    tune: Segment = TUNE_SEGMENT,
    confirm: Segment = CONFIRM_SEGMENT,
    base: EloConfig = DEFAULT_CONFIG,
) -> tuple[TuningResult, ...]:
    """Score every (k, home advantage) pair; best first by tuning Brier, then log loss."""
    if not k_values or not home_values:
        raise ValueError("grid needs at least one k and one home advantage value")
    matches = tuple(matches)
    results = []
    for k, home in product(k_values, home_values):
        config = replace(base, k=k, home_advantage=home)
        predictions = walk_forward(matches, EloModel(config), home_of)
        tuned = [p for p in predictions if tune.includes(p.match)]
        if not tuned:
            raise ValueError(f"no matches in the tune segment {tune.name!r}")
        confirmed = [p for p in predictions if confirm.includes(p.match)]
        results.append(TuningResult(config, score(tuned), score(confirmed) if confirmed else None))
    return tuple(sorted(results, key=lambda r: (r.tune.brier, r.tune.log_loss)))


def format_results(results: Sequence[TuningResult], top: int, baseline: TuningResult) -> str:
    """Table of the best `top` settings, then the winner compared with `baseline`."""
    header = (
        f"  {'Setting':<28}{'Tune Brier':>11}{'Tune LL':>9}"
        f"{'Confirm Brier':>15}{'Confirm LL':>12}{'Confirm acc':>13}"
    )
    lines = [f"Top {min(top, len(results))} of {len(results)} settings by tuning Brier", header]
    lines += [f"  {_label(r.config):<28}{_scores(r)}" for r in results[:top]]
    best = results[0]
    lines += [
        "",
        f"Baseline: {_label(baseline.config)} (current defaults){_scores(baseline)}",
        f"Best: {_label(best.config)}{_scores(best)}",
    ]
    return "\n".join(lines)


def _label(config: EloConfig) -> str:
    return f"k={config.k:g}, home advantage={config.home_advantage:g}"


def _scores(result: TuningResult) -> str:
    tune = f"{result.tune.brier:>11.4f}{result.tune.log_loss:>9.4f}"
    if result.confirm is None:
        return tune + f"{'-':>15}{'-':>12}{'-':>13}"
    c = result.confirm
    return tune + f"{c.brier:>15.4f}{c.log_loss:>12.4f}{c.accuracy:>13.1%}"
