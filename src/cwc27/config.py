"""Project-wide settings and file locations."""

import os
from datetime import date
from pathlib import Path

# Day after the 2023 World Cup final (19 Nov 2023): start of the analysis window.
WINDOW_START = date(2023, 11, 20)
# Ratings warm up from here, so they are settled by the analysis window.
RATINGS_START = date(2019, 1, 1)


def data_dir() -> Path:
    return Path(os.environ.get("CWC27_DATA_DIR", "data"))


def raw_zip_path() -> Path:
    return data_dir() / "raw" / "odis_male_json.zip"


def manual_results_dir() -> Path:
    return data_dir() / "manual"


# Qualified automatically for the 2027 World Cup (ICC ranking cutoff 30 Sep 2026, plus hosts).
WC2027_TEAMS = (
    "South Africa",
    "Zimbabwe",
    "Australia",
    "India",
    "New Zealand",
    "Pakistan",
    "Sri Lanka",
    "England",
    "Bangladesh",
    "Afghanistan",
)


def squads_dir() -> Path:
    """Announced squads from past tournaments, matched to player ids."""
    return data_dir() / "squads"


def recent_results_path() -> Path:
    """Where `cwc27 result` records matches Cricsheet hasn't published yet."""
    return manual_results_dir() / "recent.csv"


def fixtures_path() -> Path:
    return data_dir() / "fixtures.csv"


def predictions_log_path() -> Path:
    return data_dir() / "predictions_log.csv"


def database_path() -> Path:
    return data_dir() / "processed" / "cwc27.duckdb"
