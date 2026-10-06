"""One `cwc27 update` cycle: rate teams, score the log, refresh predictions, forecast series."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime

from cwc27.evaluation.metrics import Summary
from cwc27.fixtures import Fixture, fixture_home
from cwc27.models import Match
from cwc27.ratings.elo import EloConfig, run_elo, win_probability
from cwc27.simulate.forecast import SeriesOutlook, series_outlooks
from cwc27.tracking.log import (
    LoggedPrediction,
    refresh_predictions,
    score_log,
    track_record,
)
from cwc27.venues import home_team


@dataclass(frozen=True, slots=True)
class UpdateOutcome:
    log: tuple[LoggedPrediction, ...]
    newly_scored: tuple[LoggedPrediction, ...]
    upcoming: tuple[LoggedPrediction, ...]
    awaiting: tuple[LoggedPrediction, ...]  # match date passed, no result recorded yet
    outlooks: tuple[SeriesOutlook, ...]
    record: Summary | None


def model_name(config: EloConfig) -> str:
    return f"elo-k{config.k:g}-h{config.home_advantage:g}"


def run_update(
    matches: Sequence[Match],
    fixtures: Sequence[Fixture],
    log: Sequence[LoggedPrediction],
    config: EloConfig,
    city_countries: Mapping[str, str],
    today: date,
    now: datetime,
    n_sims: int = 10_000,
    seed: int | None = None,
) -> UpdateOutcome:
    """Everything `cwc27 update` computes, without any file or console access.

    Only matches up to `today` are used, so replaying a past date can't see later results.
    """
    matches = [m for m in matches if m.date <= today]
    ratings = run_elo(matches, config, home_of=lambda m: home_team(m, city_countries))

    def predict(fixture: Fixture) -> tuple[float, str | None]:
        home = fixture_home(fixture, city_countries)
        return win_probability(ratings, fixture.team_a, fixture.team_b, config, home), home

    scored = score_log(log, matches, now)
    newly_scored = tuple(
        new
        for old, new in zip(log, scored, strict=True)
        if old.result_type is None and new.result_type
    )
    refreshed = refresh_predictions(scored, fixtures, predict, model_name(config), today, now)
    outlooks = series_outlooks(fixtures, matches, lambda f: predict(f)[0], n_sims, seed)
    return UpdateOutcome(
        log=refreshed,
        newly_scored=newly_scored,
        upcoming=tuple(r for r in refreshed if r.date > today and r.result_type is None),
        awaiting=tuple(r for r in refreshed if r.date < today and r.result_type is None),
        outlooks=tuple(o for o in outlooks if o.remaining > 0),
        record=track_record(refreshed),
    )
