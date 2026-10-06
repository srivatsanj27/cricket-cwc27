"""Where a match was played, and which side (if any) was at home."""

import csv
import re
from collections.abc import Mapping
from functools import cache
from pathlib import Path
from types import MappingProxyType

from cwc27.models import Match

CITY_COUNTRY_CSV = Path(__file__).resolve().parents[2] / "config" / "city_country.csv"


@cache
def load_city_countries(path: Path = CITY_COUNTRY_CSV) -> Mapping[str, str]:
    table: dict[str, str] = {}
    with path.open(newline="") as f:
        for row in csv.DictReader(f):
            city, country = (row.get("city") or "").strip(), (row.get("country") or "").strip()
            if not city or not country:
                raise ValueError(f"{path}: row missing city or country: {row}")
            if city in table:
                raise ValueError(f"{path}: duplicate city {city!r}")
            table[city] = country
    return MappingProxyType(table)


def country_of(match: Match, city_countries: Mapping[str, str]) -> str | None:
    """Country a match was played in, or None if the location isn't in the table."""
    return country_of_place(match.city, match.venue, city_countries)


def country_of_place(
    city: str | None, venue: str | None, city_countries: Mapping[str, str]
) -> str | None:
    """Country for a city, falling back to a city named in the venue; None if unknown."""
    if city and city in city_countries:
        return city_countries[city]
    if venue:
        # Longest whole-word match first, so "East London" beats "London".
        for known_city in sorted(city_countries, key=len, reverse=True):
            if re.search(rf"\b{re.escape(known_city)}\b", venue):
                return city_countries[known_city]
    return None


def home_team(match: Match, city_countries: Mapping[str, str]) -> str | None:
    """The side playing in its own country, or None at a neutral or unknown venue."""
    country = country_of(match, city_countries)
    if country in (match.team_a, match.team_b):
        return country
    return None
