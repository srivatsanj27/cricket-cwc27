"""Command-line entry point: `cwc27 <command>`."""

import argparse
import http.client
import sys
import urllib.error
import zipfile
from pathlib import Path

import duckdb

from cwc27 import config
from cwc27.ingest.cricsheet import ParseError, download_odi_zip, parse_zip
from cwc27.ingest.manual import load_manual_results, merge_sources
from cwc27.store import MatchStore

MAX_ERRORS_SHOWN = 10


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    return args.handler(args)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cwc27", description=__doc__)
    commands = parser.add_subparsers(required=True, metavar="command")

    ingest = commands.add_parser("ingest", help="load Cricsheet ODI data into the database")
    ingest.add_argument("--download", action="store_true", help="fetch the latest zip first")
    ingest.add_argument("--zip", type=Path, default=None, help="path to a Cricsheet ODI zip")
    ingest.set_defaults(handler=_ingest)
    return parser


def _ingest(args: argparse.Namespace) -> int:
    zip_path = args.zip or config.raw_zip_path()
    if args.download and not _download(zip_path):
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


def _report_errors(errors: tuple[str, ...]) -> None:
    if not errors:
        return
    print(f"Skipped {len(errors)} file(s):")
    for error in errors[:MAX_ERRORS_SHOWN]:
        print(f"  {error}")


if __name__ == "__main__":
    sys.exit(main())
