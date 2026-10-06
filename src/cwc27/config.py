"""Project-wide settings and file locations."""

import os
from datetime import date
from pathlib import Path

# First day after the 2023 World Cup final: start of the analysis window.
WINDOW_START = date(2023, 11, 19)


def data_dir() -> Path:
    return Path(os.environ.get("CWC27_DATA_DIR", "data"))


def raw_zip_path() -> Path:
    return data_dir() / "raw" / "odis_male_json.zip"


def database_path() -> Path:
    return data_dir() / "processed" / "cwc27.duckdb"
