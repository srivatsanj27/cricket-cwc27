from dataclasses import replace

import pytest

from cwc27.ingest.cricsheet import parse_match
from cwc27.venues import country_of, home_team, load_city_countries
from tests.conftest import make_cricsheet_match


@pytest.fixture
def lookup():
    return {"Harare": "Zimbabwe", "Sydney": "Australia", "Dubai": "United Arab Emirates"}


def _match(teams=("Zimbabwe", "Pakistan"), city="Harare", venue="Harare Sports Club"):
    data = make_cricsheet_match(
        teams=teams, city=city, venue=venue, outcome={"winner": teams[0], "by": {"runs": 1}}
    )
    return parse_match(data, match_id="cs_1").match


def test_country_from_city(lookup):
    assert country_of(_match(), lookup) == "Zimbabwe"


def test_country_falls_back_to_venue_name_when_city_missing(lookup):
    m = replace(_match(teams=("Australia", "India")), city=None, venue="Sydney Cricket Ground")

    assert country_of(m, lookup) == "Australia"


def test_unknown_location_returns_none(lookup):
    m = _match(city="Atlantis", venue="Atlantis Oval")

    assert country_of(m, lookup) is None


def test_home_team_when_one_side_plays_in_its_own_country(lookup):
    assert home_team(_match(), lookup) == "Zimbabwe"
    assert home_team(_match(teams=("Pakistan", "Zimbabwe")), lookup) == "Zimbabwe"


def test_no_home_team_at_neutral_venue(lookup):
    m = _match(teams=("Pakistan", "Afghanistan"), city="Dubai", venue="Dubai Stadium")

    assert home_team(m, lookup) is None


def test_venue_fallback_prefers_longest_whole_word_city():
    lookup = {"London": "England", "East London": "South Africa"}
    m = replace(
        _match(teams=("South Africa", "India")), city=None, venue="Buffalo Park, East London"
    )

    assert country_of(m, lookup) == "South Africa"


def test_venue_fallback_ignores_partial_words():
    lookup = {"Kandy": "Sri Lanka"}
    m = replace(_match(), city=None, venue="Kandyland Oval")

    assert country_of(m, lookup) is None


def test_city_table_rejects_duplicate_cities(tmp_path):
    path = tmp_path / "cities.csv"
    path.write_text("city,country\nHamilton,New Zealand\nHamilton,Bermuda\n")

    with pytest.raises(ValueError, match="Hamilton"):
        load_city_countries(path)


def test_bundled_city_table_loads_and_has_known_entries():
    table = load_city_countries()

    assert table["Windhoek"] == "Namibia"
    assert table["Bridgetown"] == "West Indies"
    assert len(table) > 100
