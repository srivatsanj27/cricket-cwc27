from datetime import date

import pytest

from cwc27.ingest.cricsheet import ParseError, download_odi_zip, parse_match, parse_zip
from cwc27.models import ResultType
from tests.conftest import make_cricsheet_match


def test_parses_win_by_runs():
    data = make_cricsheet_match(outcome={"winner": "Alphaland", "by": {"runs": 25}})

    parsed = parse_match(data, match_id="cs_1")

    m = parsed.match
    assert m.match_id == "cs_1"
    assert m.date == date(2024, 1, 10)
    assert (m.team_a, m.team_b) == ("Alphaland", "Betaland")
    assert m.winner == "Alphaland"
    assert m.result_type is ResultType.NORMAL
    assert m.margin_runs == 25
    assert m.margin_wickets is None
    assert m.venue == "Test Oval"
    assert m.city == "Testville"
    assert (m.toss_winner, m.toss_decision) == ("Betaland", "field")


def test_parses_win_by_wickets():
    data = make_cricsheet_match(outcome={"winner": "Betaland", "by": {"wickets": 4}})

    m = parse_match(data, match_id="cs_2").match

    assert m.winner == "Betaland"
    assert m.margin_wickets == 4
    assert m.margin_runs is None


def test_dls_result_is_flagged():
    data = make_cricsheet_match(
        outcome={"winner": "Alphaland", "by": {"runs": 30}, "method": "D/L"}
    )

    m = parse_match(data, match_id="cs_3").match

    assert m.result_type is ResultType.DLS
    assert m.winner == "Alphaland"


def test_tie_has_no_winner_even_with_super_over_eliminator():
    data = make_cricsheet_match(outcome={"result": "tie", "eliminator": "Betaland"})

    m = parse_match(data, match_id="cs_4").match

    assert m.result_type is ResultType.TIE
    assert m.winner is None


def test_no_result():
    data = make_cricsheet_match(outcome={"result": "no result"})

    m = parse_match(data, match_id="cs_5").match

    assert m.result_type is ResultType.NO_RESULT
    assert m.winner is None


def test_event_name_is_captured_when_present():
    data = make_cricsheet_match(event={"name": "Alphaland tour of Betaland", "match_number": 2})

    m = parse_match(data, match_id="cs_6").match

    assert m.event == "Alphaland tour of Betaland"


def test_missing_city_is_allowed():
    data = make_cricsheet_match()
    del data["info"]["city"]

    m = parse_match(data, match_id="cs_7").match

    assert m.city is None


def test_playing_xis_are_extracted_with_registry_ids():
    data = make_cricsheet_match()

    parsed = parse_match(data, match_id="cs_8")

    assert len(parsed.appearances) == 22
    first = parsed.appearances[0]
    assert first.match_id == "cs_8"
    assert first.team == "Alphaland"
    assert first.player_name == "A Player1"
    assert first.player_id == data["info"]["registry"]["people"]["A Player1"]


def test_team_names_are_normalised():
    data = make_cricsheet_match(
        teams=("U.A.E.", "Betaland"), outcome={"winner": "U.A.E.", "by": {"runs": 1}}
    )
    data["info"]["toss"] = {"winner": "U.A.E.", "decision": "bat"}

    m = parse_match(data, match_id="cs_9").match

    assert m.team_a == "United Arab Emirates"
    assert m.winner == "United Arab Emirates"
    assert m.toss_winner == "United Arab Emirates"


@pytest.mark.parametrize(
    ("field", "value"),
    [("gender", "female"), ("match_type", "T20"), ("team_type", "club")],
)
def test_rejects_matches_outside_scope(field, value):
    data = make_cricsheet_match(**{field: value})

    with pytest.raises(ParseError, match=field):
        parse_match(data, match_id="cs_10")


def test_rejects_unknown_outcome_shape():
    data = make_cricsheet_match(outcome={"something": "odd"})

    with pytest.raises(ParseError, match="outcome"):
        parse_match(data, match_id="cs_11")


def test_rejects_missing_required_field():
    data = make_cricsheet_match()
    del data["info"]["teams"]

    with pytest.raises(ParseError, match="teams"):
        parse_match(data, match_id="cs_12")


def test_rejects_winner_who_did_not_play():
    data = make_cricsheet_match(outcome={"winner": "Gammaland", "by": {"runs": 5}})

    with pytest.raises(ParseError, match="winner"):
        parse_match(data, match_id="cs_13")


def test_rejects_toss_winner_who_did_not_play():
    data = make_cricsheet_match(toss={"winner": "Gammaland", "decision": "bat"})

    with pytest.raises(ParseError, match="toss"):
        parse_match(data, match_id="cs_14")


def test_rejects_team_playing_itself():
    data = make_cricsheet_match(teams=("Alphaland", "Alphaland"))

    with pytest.raises(ParseError, match="teams"):
        parse_match(data, match_id="cs_15")


def test_rejects_team_with_no_players():
    data = make_cricsheet_match()
    data["info"]["players"]["Betaland"] = []

    with pytest.raises(ParseError, match="players"):
        parse_match(data, match_id="cs_16")


def test_rejects_duplicate_player_in_a_team():
    data = make_cricsheet_match()
    data["info"]["players"]["Alphaland"][1] = "A Player1"

    with pytest.raises(ParseError, match="duplicate"):
        parse_match(data, match_id="cs_17")


@pytest.mark.parametrize(
    "corrupt",
    [
        lambda d: d["info"].update(toss="Alphaland"),
        lambda d: d["info"].update(registry=[]),
        lambda d: d["info"].update(dates=["not-a-date"]),
    ],
)
def test_malformed_shapes_raise_parse_error(corrupt):
    data = make_cricsheet_match()
    corrupt(data)

    with pytest.raises(ParseError):
        parse_match(data, match_id="cs_18")


def test_non_object_file_raises_parse_error():
    with pytest.raises(ParseError):
        parse_match([], match_id="cs_19")


def test_download_from_url_writes_zip(tmp_path, cricsheet_zip):
    source = cricsheet_zip({"1": make_cricsheet_match()})
    dest = tmp_path / "out" / "odis.zip"

    download_odi_zip(dest, url=source.as_uri())

    assert parse_zip(dest).parsed
    assert not dest.with_suffix(".zip.part").exists()


def test_download_rejects_non_zip_and_keeps_existing_file(tmp_path):
    html = tmp_path / "error.html"
    html.write_text("<html>Service unavailable</html>")
    dest = tmp_path / "odis.zip"
    dest.write_bytes(b"previous good copy")

    with pytest.raises(ParseError, match="not a zip"):
        download_odi_zip(dest, url=html.as_uri())

    assert dest.read_bytes() == b"previous good copy"
    assert not dest.with_suffix(".zip.part").exists()


def test_parse_zip_collects_matches_and_reports_errors(cricsheet_zip):
    missing_dates = make_cricsheet_match()
    del missing_dates["info"]["dates"]
    bad_toss = make_cricsheet_match()
    bad_toss["info"]["toss"] = "Alphaland"
    path = cricsheet_zip(
        {
            "1001": make_cricsheet_match(date="2024-02-01"),
            "1002": make_cricsheet_match(date="2023-12-01"),
            "1003": missing_dates,
            "1004": bad_toss,
        }
    )

    result = parse_zip(path)

    assert [p.match.match_id for p in result.parsed] == ["cs_1002", "cs_1001"]  # sorted by date
    assert len(result.errors) == 2
    assert "1003.json" in result.errors[0]
    assert "1004.json" in result.errors[1]
