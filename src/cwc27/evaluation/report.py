"""Compare models on the same walk-forward predictions, split into segments of interest."""

import math
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

from cwc27.config import WINDOW_START
from cwc27.evaluation.backtest import Model, score, walk_forward
from cwc27.evaluation.metrics import Summary
from cwc27.models import Match


@dataclass(frozen=True, slots=True)
class Segment:
    """A named subset of matches to score, e.g. one tournament."""

    name: str
    includes: Callable[[Match], bool]


@dataclass(frozen=True, slots=True)
class ReportRow:
    segment: str
    model: str
    summary: Summary


DEFAULT_SEGMENTS = (
    Segment("Since 2023 WC final", lambda m: m.date >= WINDOW_START),
    Segment("2023 World Cup", lambda m: m.event == "ICC Cricket World Cup" and m.date.year == 2023),
    Segment(
        "2025 Champions Trophy",
        lambda m: m.event == "ICC Champions Trophy" and m.date.year == 2025,
    ),
)


def compare(
    matches: Iterable[Match],
    models: Mapping[str, Model],
    home_of: Callable[[Match], str | None],
    segments: Iterable[Segment] = DEFAULT_SEGMENTS,
) -> tuple[ReportRow, ...]:
    """Walk every model over all matches, then score each segment. Empty segments are skipped.

    Models learn from every match, including those outside a segment; only scoring is filtered.
    """
    matches = tuple(matches)
    predictions = {name: walk_forward(matches, model, home_of) for name, model in models.items()}
    rows = []
    for segment in segments:
        for name, model_predictions in predictions.items():
            chosen = [p for p in model_predictions if segment.includes(p.match)]
            if chosen:
                rows.append(ReportRow(segment.name, name, score(chosen)))
    return tuple(rows)


def format_rows(rows: Iterable[ReportRow]) -> str:
    """Plain-text table, one block per segment. Lower Brier and log loss are better."""
    lines = []
    current = None
    for row in rows:
        if row.segment != current:
            current = row.segment
            lines += [
                "",
                row.segment,
                f"  {'Model':<12}{'n':>5}{'Brier':>9}{'Log loss':>10}{'Acc':>8}",
            ]
        acc = "-" if math.isnan(row.summary.accuracy) else f"{row.summary.accuracy:.1%}"
        lines.append(
            f"  {row.model:<12}{row.summary.n:>5}{row.summary.brier:>9.4f}"
            f"{row.summary.log_loss:>10.4f}{acc:>8}"
        )
    return "\n".join(lines)
