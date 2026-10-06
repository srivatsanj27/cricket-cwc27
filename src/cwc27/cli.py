"""Command-line entry point: `cwc27 <command>`."""

import argparse
import http.client
import math
import sys
import urllib.error
import zipfile
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path

import duckdb

from cwc27 import config
from cwc27.evaluation.baselines import CoinFlip, WinRate
from cwc27.evaluation.report import compare, format_rows
from cwc27.evaluation.tuning import (
    CONFIRM_SEGMENT,
    TUNE_SEGMENT,
    format_results,
    grid_search,
)
from cwc27.fixtures import Fixture, load_fixtures
from cwc27.ingest.cricsheet import ParseError, download_odi_zip, parse_zip
from cwc27.ingest.manual import append_result, load_manual_results, merge_sources
from cwc27.models import Match
from cwc27.ratings.elo import EloConfig
from cwc27.ratings.model import EloModel
from cwc27.store import MatchStore
from cwc27.teams import normalise_team
from cwc27.tracking.display import format_update
from cwc27.tracking.log import read_log, write_log
from cwc27.tracking.update import run_update
from cwc27.venues import home_team, load_city_countries

MAX_ERRORS_SHOWN = 10
DEFAULT_ELO = EloConfig()
DEFAULT_K_VALUES = (10.0, 15.0, 20.0, 25.0, 30.0, 35.0, 40.0, 50.0, 60.0)
DEFAULT_HOME_VALUES = (0.0, 20.0, 40.0, 60.0, 80.0, 100.0, 120.0)


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    return args.handler(args)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cwc27", description=__doc__)
    commands = parser.add_subparsers(required=True, metavar="command")
    _add_ingest_command(commands)
    _add_backtest_command(commands)
    _add_tune_command(commands)
    _add_result_command(commands)
    _add_update_command(commands)
    return parser


def _add_ingest_command(commands: argparse._SubParsersAction) -> None:
    ingest = commands.add_parser("ingest", help="load Cricsheet ODI data into the database")
    ingest.add_argument("--download", action="store_true", help="fetch the latest zip first")
    ingest.add_argument("--zip", type=Path, default=None, help="path to a Cricsheet ODI zip")
    ingest.set_defaults(handler=_ingest)


def _add_backtest_command(commands: argparse._SubParsersAction) -> None:
    backtest = commands.add_parser(
        "backtest", help="score models on past ODIs, predicting each from earlier results only"
    )
    backtest.add_argument(
        "--k", type=_positive_float, default=DEFAULT_ELO.k, help="Elo K-factor (> 0)"
    )
    backtest.add_argument(
        "--home-advantage",
        type=_non_negative_float,
        default=DEFAULT_ELO.home_advantage,
        help="Elo home bonus (>= 0)",
    )
    _add_since_argument(backtest)
    backtest.set_defaults(handler=_backtest)


def _add_tune_command(commands: argparse._SubParsersAction) -> None:
    tune = commands.add_parser(
        "tune", help="grid-search Elo settings: tune on 2021 to WC23, confirm on matches since"
    )
    tune.add_argument(
        "--k-values",
        type=_float_list(_positive_float),
        default=DEFAULT_K_VALUES,
        help="comma-separated K values to try",
    )
    tune.add_argument(
        "--home-values",
        type=_float_list(_non_negative_float),
        default=DEFAULT_HOME_VALUES,
        help="comma-separated home advantages to try",
    )
    tune.add_argument("--top", type=_positive_int, default=10, help="how many settings to list")
    _add_since_argument(tune)
    tune.set_defaults(handler=_tune)


def _add_result_command(commands: argparse._SubParsersAction) -> None:
    result = commands.add_parser(
        "result", help="record a finished match that Cricsheet hasn't published yet"
    )
    result.add_argument("date", type=date.fromisoformat, help="YYYY-MM-DD")
    result.add_argument("team_a")
    result.add_argument("team_b")
    outcome = result.add_mutually_exclusive_group(required=True)
    outcome.add_argument("--winner", help="the team that won")
    outcome.add_argument("--tie", action="store_true")
    outcome.add_argument("--no-result", action="store_true", help="washout or abandoned")
    margin = result.add_mutually_exclusive_group()
    margin.add_argument("--runs", type=_positive_int, help="won by this many runs")
    margin.add_argument("--wickets", type=_positive_int, help="won by this many wickets")
    result.add_argument("--dls", action="store_true", help="decided by DLS")
    result.add_argument("--venue", help="defaults to the fixture's venue")
    result.add_argument("--city", help="defaults to the fixture's city")
    result.add_argument("--event", help="defaults to the fixture's series")
    result.set_defaults(handler=_result)


def _add_update_command(commands: argparse._SubParsersAction) -> None:
    update = commands.add_parser(
        "update", help="ingest, score the prediction log and predict upcoming fixtures"
    )
    update.add_argument("--download", action="store_true", help="fetch the latest zip first")
    update.add_argument("--zip", type=Path, default=None, help="path to a Cricsheet ODI zip")
    update.add_argument("--sims", type=_positive_int, default=10_000, help="series simulations")
    # For tests and replays: treat this date as today.
    update.add_argument("--today", type=date.fromisoformat, default=None, help=argparse.SUPPRESS)
    update.set_defaults(handler=_update)


def _add_since_argument(command: argparse.ArgumentParser) -> None:
    command.add_argument(
        "--since",
        type=date.fromisoformat,
        default=config.RATINGS_START,
        help="first match to learn from, YYYY-MM-DD",
    )


def _positive_float(text: str) -> float:
    value = float(text)
    if not (math.isfinite(value) and value > 0):
        raise argparse.ArgumentTypeError(f"must be a finite number above 0, got {text}")
    return value


def _non_negative_float(text: str) -> float:
    value = float(text)
    if not (math.isfinite(value) and value >= 0):
        raise argparse.ArgumentTypeError(f"must be a finite number, 0 or more, got {text}")
    return value


def _positive_int(text: str) -> int:
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError(f"must be at least 1, got {text}")
    return value


def _float_list(parse_one: Callable[[str], float]) -> Callable[[str], tuple[float, ...]]:
    def parse(text: str) -> tuple[float, ...]:
        try:
            values = (parse_one(part) for part in text.split(",") if part.strip())
            return tuple(dict.fromkeys(values))  # drop repeats, keep order
        except ValueError as exc:
            raise argparse.ArgumentTypeError(f"invalid list {text!r}: {exc}") from exc

    return parse


def _load_matches_or_report(since: date) -> list[Match] | None:
    """Matches from the database, or None after printing why they couldn't be loaded."""
    db_path = config.database_path()
    if not db_path.exists():
        print(f"No database at {db_path}; run `cwc27 ingest` first.", file=sys.stderr)
        return None
    try:
        matches = MatchStore(db_path).load_matches(since=since)
    except (duckdb.Error, OSError) as exc:
        print(f"Could not read database: {exc}", file=sys.stderr)
        return None
    if not matches:
        print(f"No matches since {since}; run `cwc27 ingest` first.", file=sys.stderr)
        return None
    return matches


def _backtest(args: argparse.Namespace) -> int:
    matches = _load_matches_or_report(args.since)
    if matches is None:
        return 1
    lookup = load_city_countries()
    models = {
        "Coin flip": CoinFlip(),
        "Win rate": WinRate(),
        "Elo": EloModel(EloConfig(k=args.k, home_advantage=args.home_advantage)),
    }
    rows = compare(matches, models, home_of=lambda m: home_team(m, lookup))
    print(
        f"Backtest over {len(matches)} ODIs, {matches[0].date} to {matches[-1].date} "
        f"(Elo k={args.k:g}, home advantage={args.home_advantage:g})"
    )
    print("Each match is predicted from earlier results only. Lower Brier and log loss are better.")
    print(format_rows(rows))
    return 0


def _tune(args: argparse.Namespace) -> int:
    matches = _load_matches_or_report(args.since)
    if matches is None:
        return 1
    lookup = load_city_countries()

    def home_of(m: Match) -> str | None:
        return home_team(m, lookup)

    try:
        results = grid_search(matches, home_of, args.k_values, args.home_values)
        (baseline,) = grid_search(matches, home_of, [DEFAULT_ELO.k], [DEFAULT_ELO.home_advantage])
    except ValueError as exc:
        print(f"Cannot tune: {exc}", file=sys.stderr)
        return 1
    print(
        f"Grid search over {len(matches)} ODIs from {matches[0].date}. Settings are ranked on "
        f"{TUNE_SEGMENT.name} only; '{CONFIRM_SEGMENT.name}' is the fair check."
    )
    print(format_results(results, top=args.top, baseline=baseline))
    return 0


def _ingest(args: argparse.Namespace) -> int:
    return _run_ingest(args.zip or config.raw_zip_path(), args.download)


def _run_ingest(zip_path: Path, download: bool) -> int:
    if download and not _download(zip_path):
        return 1
    if not zip_path.exists():
        print(f"Zip not found: {zip_path} (try --download)", file=sys.stderr)
        return 1

    try:
        result = parse_zip(zip_path)
    except (zipfile.BadZipFile, OSError) as exc:
        print(f"Could not read {zip_path}: {exc}", file=sys.stderr)
        return 1
    _report_errors(result.errors)
    if not result.parsed:
        print("No matches parsed; database left unchanged.", file=sys.stderr)
        return 1

    manual = load_manual_results(config.manual_results_dir())
    _report_errors(manual.errors)
    merged, superseded = merge_sources(result.parsed, manual.parsed)

    try:
        MatchStore(config.database_path()).save(merged, replace_source="manual")
    except (duckdb.Error, OSError) as exc:
        print(f"Could not save to database: {exc}", file=sys.stderr)
        return 1

    in_window = sum(1 for p in merged if p.match.date >= config.WINDOW_START)
    print(
        f"Loaded {len(merged)} matches ({len(result.parsed)} Cricsheet, "
        f"{len(merged) - len(result.parsed)} manual; "
        f"{in_window} since {config.WINDOW_START.isoformat()})"
    )
    if superseded:
        print(f"{len(superseded)} manual result(s) now covered by Cricsheet and can be removed:")
        for match_id in superseded:
            print(f"  {match_id}")
    return 0


def _download(zip_path: Path) -> bool:
    print(f"Downloading Cricsheet ODI data to {zip_path} ...")
    try:
        download_odi_zip(zip_path)
    except (urllib.error.URLError, http.client.HTTPException, ParseError, OSError) as exc:
        print(f"Download failed: {exc}", file=sys.stderr)
        return False
    return True


def _result(args: argparse.Namespace) -> int:
    try:
        teams = {normalise_team(args.team_a), normalise_team(args.team_b)}
        fixture = next(
            (
                f
                for f in load_fixtures(config.fixtures_path()).fixtures
                if f.date == args.date and {f.team_a, f.team_b} == teams
            ),
            None,
        )
        match = append_result(config.recent_results_path(), _result_values(args, fixture))
    except (ValueError, OSError) as exc:
        print(f"Could not record result: {exc}", file=sys.stderr)
        return 1
    print(f"Recorded {match.match_id}. Run `cwc27 update` to score and re-predict.")
    return 0


def _result_values(args: argparse.Namespace, fixture: Fixture | None) -> dict[str, str]:
    if args.tie:
        result_type = "tie"
    elif args.no_result:
        result_type = "no_result"
    else:
        result_type = "dls" if args.dls else "normal"
    return {
        "date": args.date.isoformat(),
        "team_a": args.team_a,
        "team_b": args.team_b,
        "winner": args.winner or "",
        "result_type": result_type,
        "margin_runs": str(args.runs or ""),
        "margin_wickets": str(args.wickets or ""),
        "venue": args.venue or (fixture.venue if fixture and fixture.venue else ""),
        "city": args.city or (fixture.city if fixture and fixture.city else ""),
        "event": args.event or (fixture.series if fixture else ""),
        "ref": "cwc27 result",
    }


def _update(args: argparse.Namespace) -> int:
    if _run_ingest(args.zip or config.raw_zip_path(), args.download) != 0:
        return 1
    matches = _load_matches_or_report(config.RATINGS_START)
    if matches is None:
        return 1
    fixture_load = load_fixtures(config.fixtures_path())
    _report_errors(fixture_load.errors)
    log_path = config.predictions_log_path()
    try:
        log = read_log(log_path)
    except (ValueError, OSError) as exc:
        print(f"Could not read the prediction log: {exc}", file=sys.stderr)
        return 1

    outcome = run_update(
        matches,
        fixture_load.fixtures,
        log,
        DEFAULT_ELO,
        load_city_countries(),
        today=args.today or date.today(),
        now=datetime.now(UTC),
        n_sims=args.sims,
    )
    try:
        write_log(log_path, outcome.log)
    except OSError as exc:
        print(f"Could not write the prediction log: {exc}", file=sys.stderr)
        return 1
    print()
    print(format_update(outcome))
    return 0


def _report_errors(errors: tuple[str, ...]) -> None:
    if not errors:
        return
    print(f"Skipped {len(errors)} file(s):")
    for error in errors[:MAX_ERRORS_SHOWN]:
        print(f"  {error}")


if __name__ == "__main__":
    sys.exit(main())
