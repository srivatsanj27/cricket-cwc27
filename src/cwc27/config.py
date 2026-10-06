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


def database_path() -> Path:
    return data_dir() / "processed" / "cwc27.duckdb"
