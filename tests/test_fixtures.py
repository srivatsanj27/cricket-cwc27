from datetime import date

import pytest

from cwc27.fixtures import Fixture, fixture_home, load_fixtures

HEADER = "date,series,match_no,team_a,team_b,venue,city\n"


def write(tmp_path, rows):
    path = tmp_path / "fixtures.csv"
    path.write_text(HEADER + "".join(r + "\n" for r in rows))
    return path


def fixture(team_a="Betaland", team_b="Alphaland", city="Testville", venue="Test Oval"):
    return Fixture(date(2026, 10, 12), "Alpha tour of Beta", 1, team_a, team_b, venue, city)


def test_loads_fixtures_sorted_by_date(tmp_path):
    path = write(
        tmp_path,
        [
            "2026-10-15,Alpha tour of Beta,2,Betaland,Alphaland,Test Oval,Testville",
            "2026-10-12,Alpha tour of Beta,1,Betaland,Alphaland,Test Oval,Testville",
        ],
    )

    result = load_fixtures(path)

    assert result.errors == ()
    assert [f.match_no for f in result.fixtures] == [1, 2]
    first = result.fixtures[0]
    assert first.date == date(2026, 10, 12)
    assert first.key == "2026-10-12_alphaland_betaland"


def test_key_does_not_depend_on_team_order():
    assert fixture("Betaland", "Alphaland").key == fixture("Alphaland", "Betaland").key


def test_duplicate_fixtures_are_reported_and_the_first_kept(tmp_path):
    path = write(
        tmp_path,
        [
            "2026-10-12,Alpha tour of Beta,1,Betaland,Alphaland,Test Oval,Testville",
            "2026-10-12,Alpha tour of Beta,1,Alphaland,Betaland,Other Oval,Testville",
        ],
    )

    result = load_fixtures(path)

    assert [f.venue for f in result.fixtures] == ["Test Oval"]
    assert "fixtures.csv:3" in result.errors[0] and "duplicate" in result.errors[0]


def test_missing_file_means_no_fixtures(tmp_path):
    result = load_fixtures(tmp_path / "nope.csv")

    assert result.fixtures == ()
    assert result.errors == ()


@pytest.mark.parametrize(
    ("row", "problem"),
    [
        ("12-10-2026,S,1,Betaland,Alphaland,,", "date"),
        ("2026-10-12,S,1,Betaland,Betaland,,", "teams"),
        ("2026-10-12,S,0,Betaland,Alphaland,,", "match_no"),
        ("2026-10-12,S,one,Betaland,Alphaland,,", "match_no"),
        ("2026-10-12,,1,Betaland,Alphaland,,", "series"),
    ],
)
def test_invalid_rows_are_reported(tmp_path, row, problem):
    result = load_fixtures(write(tmp_path, [row]))

    assert result.fixtures == ()
    assert "fixtures.csv:2" in result.errors[0]
    assert problem in result.errors[0]


def test_wrong_header_is_reported(tmp_path):
    path = tmp_path / "fixtures.csv"
    path.write_text("when,who\n")

    assert "header" in load_fixtures(path).errors[0]


def test_home_side_from_city():
    assert fixture_home(fixture(), {"Testville": "Betaland"}) == "Betaland"


def test_home_side_from_venue_when_city_missing():
    f = fixture(city=None, venue="Big Ground, Testville")

    assert fixture_home(f, {"Testville": "Betaland"}) == "Betaland"


def test_neutral_venue_has_no_home_side():
    assert fixture_home(fixture(), {"Testville": "Gammaland"}) is None
