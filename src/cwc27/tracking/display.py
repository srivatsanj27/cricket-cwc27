"""Plain-text summary printed by `cwc27 update`."""

from cwc27.simulate.forecast import SeriesOutlook, TriSeriesOutlook
from cwc27.tracking.log import LoggedPrediction
from cwc27.tracking.update import UpdateOutcome


def format_update(outcome: UpdateOutcome) -> str:
    sections = [
        _section("Scored since last update", [_scored_line(r) for r in outcome.newly_scored]),
        _section(
            "Awaiting results (add with `cwc27 result`)",
            [f"  {r.date} {r.team_a} v {r.team_b} ({r.series})" for r in outcome.awaiting],
        ),
        _section(
            "Upcoming (each prediction locks the day before the match)",
            [_upcoming_line(r) for r in outcome.upcoming],
        ),
        _section("Series outlook", [_outlook_line(o) for o in outcome.outlooks]),
        _section(
            "Tri-series outlook (level on points: head-to-head, then a coin toss for NRR)",
            [line for o in outcome.tri_outlooks for line in _tri_outlook_lines(o)],
        ),
        _record_line(outcome),
    ]
    return "\n\n".join(s for s in sections if s)


def _section(title: str, lines: list[str]) -> str:
    return "\n".join([title, *lines]) if lines else ""


def _scored_line(row: LoggedPrediction) -> str:
    teams = f"{row.date} {row.team_a} v {row.team_b}"
    if row.brier is None:
        return f"  {teams}: {row.result_type}, not scored"
    outcome = "tie" if row.actual_a == 0.5 else f"{row.winner} won"
    return f"  {teams}: {outcome} (gave {row.team_a} {row.p_team_a:.0%}), Brier {row.brier:.3f}"


def _upcoming_line(row: LoggedPrediction) -> str:
    venue = f"home: {row.home}" if row.home else "neutral"
    return (
        f"  {row.date} {row.team_a} v {row.team_b} ({row.series}, match {row.match_no}): "
        f"{row.team_a} {row.p_team_a:.1%} | {row.team_b} {1 - row.p_team_a:.1%}  [{venue}]"
    )


def _outlook_line(outlook: SeriesOutlook) -> str:
    a_wins, b_wins = outlook.played
    f = outlook.forecast
    drawn = f" | drawn {f.p_drawn_series:.0%}" if f.p_drawn_series else ""
    return (
        f"  {outlook.series}: {outlook.team_a} {a_wins}-{b_wins} {outlook.team_b}, "
        f"{outlook.remaining} to play -> {outlook.team_a} {f.p_a_wins_series:.0%} | "
        f"{outlook.team_b} {f.p_b_wins_series:.0%}{drawn}"
    )


def _tri_outlook_lines(outlook: TriSeriesOutlook) -> list[str]:
    f = outlook.forecast
    order = sorted(outlook.teams, key=lambda team: -f.p_win[team])
    total = outlook.played + outlook.remaining
    return [
        f"  {outlook.series} ({outlook.played} of {total} group matches played)",
        "    reach final: " + " | ".join(f"{t} {f.p_reach_final[t]:.0%}" for t in order),
        "    win:         " + " | ".join(f"{t} {f.p_win[t]:.0%}" for t in order),
    ]


def _record_line(outcome: UpdateOutcome) -> str:
    record = outcome.record
    if record is None:
        return "Track record: no scored predictions yet"
    plural = "match" if record.n == 1 else "matches"
    return (
        f"Track record: {record.n} {plural}, Brier {record.brier:.3f}, "
        f"accuracy {record.accuracy:.0%} (coin flip: Brier 0.250, 50%)"
    )
