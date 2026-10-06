"""Upcoming matches (data/fixtures.csv) and where they are played."""

import csv
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from cwc27.teams import normalise_team, team_slug
from cwc27.venues import country_of_place

FIXTURE_COLUMNS = ("date", "series", "match_no", "team_a", "team_b", "venue", "city")


class FixtureError(ValueError):
    """A row in the fixtures file is invalid."""


@dataclass(frozen=True, slots=True)
class Fixture:
    date: date
    series: str
    match_no: int
    team_a: str
    team_b: str
    venue: str | None
    city: str | None

    @property
    def key(self) -> str:
        """Stable ID whatever the team order, e.g. '2026-10-12_pakistan_sri-lanka'."""
        slugs = sorted((team_slug(self.team_a), team_slug(self.team_b)))
        return f"{self.date.isoformat()}_{slugs[0]}_{slugs[1]}"


@dataclass(frozen=True, slots=True)
class FixtureLoad:
    fixtures: tuple[Fixture, ...]
    errors: tuple[str, ...]


def load_fixtures(path: Path) -> FixtureLoad:
    """Fixtures sorted by date; invalid rows are reported with file and line, not raised."""
    if not path.exists():
        return FixtureLoad(fixtures=(), errors=())
    fixtures: list[Fixture] = []
    errors: list[str] = []
    try:
        with path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if tuple(reader.fieldnames or ()) != FIXTURE_COLUMNS:
                header = ",".join(FIXTURE_COLUMNS)
                return FixtureLoad((), (f"{path.name}: header must be {header}",))
            seen: set[str] = set()
            for row in reader:
                try:
                    fixture = _row_to_fixture(row)
                    if fixture.key in seen:
                        raise FixtureError(f"duplicate fixture {fixture.key} (kept the first)")
                    seen.add(fixture.key)
                    fixtures.append(fixture)
                except FixtureError as exc:
                    errors.append(f"{path.name}:{reader.line_num}: {exc}")
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        return FixtureLoad((), (f"{path.name}: could not read file ({exc})",))
    fixtures.sort(key=lambda f: (f.date, f.series, f.match_no))
    return FixtureLoad(fixtures=tuple(fixtures), errors=tuple(errors))


def fixture_home(fixture: Fixture, city_countries: Mapping[str, str]) -> str | None:
    """The side playing in its own country, or None at a neutral or unknown venue."""
    country = country_of_place(fixture.city, fixture.venue, city_countries)
    return country if country in (fixture.team_a, fixture.team_b) else None


def _row_to_fixture(row: dict[str, str | None]) -> Fixture:
    v = {column: (row.get(column) or "").strip() for column in FIXTURE_COLUMNS}
    try:
        day = date.fromisoformat(v["date"])
    except ValueError as exc:
        raise FixtureError(f"date {v['date']!r} is not YYYY-MM-DD") from exc
    if not v["series"]:
        raise FixtureError("series must not be blank")
    if not v["match_no"].isdigit() or int(v["match_no"]) < 1:
        raise FixtureError(f"match_no {v['match_no']!r} must be a whole number from 1")
    try:
        team_a, team_b = normalise_team(v["team_a"]), normalise_team(v["team_b"])
    except ValueError as exc:
        raise FixtureError("teams must not be blank") from exc
    if team_a == team_b:
        raise FixtureError(f"teams must differ, got {team_a!r} twice")
    return Fixture(
        date=day,
        series=v["series"],
        match_no=int(v["match_no"]),
        team_a=team_a,
        team_b=team_b,
        venue=v["venue"] or None,
        city=v["city"] or None,
    )
