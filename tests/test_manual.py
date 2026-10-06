from datetime import date
from pathlib import Path

import pytest

from cwc27.ingest.cricsheet import parse_match
from cwc27.ingest.manual import load_manual_results, merge_sources
from cwc27.models import ResultType
from tests.conftest import make_cricsheet_match

HEADER = (
    "date,team_a,team_b,winner,result_type,margin_runs,margin_wickets,"
    "venue,city,toss_winner,toss_decision,event,ref\n"
)


def write_csv(directory: Path, name: str, rows: list[str]) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(HEADER + "".join(row + "\n" for row in rows))
    return path


def test_loads_a_win_by_runs(tmp_path):
    write_csv(
        tmp_path,
        "a.csv",
        [
            "2024-03-07,Alphaland,Betaland,Alphaland,normal,35,,Test Oval,Testville,"
            "Betaland,field,Alpha v Beta,ESPNcricinfo ODI # 1"
        ],
    )

    result = load_manual_results(tmp_path)

    assert result.errors == ()
    (parsed,) = result.parsed
    m = parsed.match
    assert m.date == date(2024, 3, 7)
    assert (m.team_a, m.team_b, m.winner) == ("Alphaland", "Betaland", "Alphaland")
    assert m.result_type is ResultType.NORMAL
    assert (m.margin_runs, m.margin_wickets) == (35, None)
    assert (m.toss_winner, m.toss_decision) == ("Betaland", "field")
    assert m.source == "manual"
    assert m.match_id == "man_2024-03-07_alphaland_betaland"
    assert parsed.appearances == ()


def test_loads_no_result_with_blank_optional_fields(tmp_path):
    write_csv(tmp_path, "a.csv", ["2024-03-09,Alphaland,Betaland,,no_result,,,,,,,,"])

    (parsed,) = load_manual_results(tmp_path).parsed

    assert parsed.match.result_type is ResultType.NO_RESULT
    assert parsed.match.winner is None
    assert parsed.match.city is None


def test_reads_every_csv_in_the_directory_sorted_by_date(tmp_path):
    write_csv(tmp_path, "a.csv", ["2024-05-01,Alphaland,Betaland,Betaland,normal,,3,,,,,,"])
    write_csv(tmp_path, "b.csv", ["2024-01-01,Alphaland,Gammaland,Alphaland,dls,10,,,,,,,"])

    result = load_manual_results(tmp_path)

    assert [p.match.date for p in result.parsed] == [date(2024, 1, 1), date(2024, 5, 1)]
    assert result.parsed[0].match.result_type is ResultType.DLS


def test_missing_directory_gives_empty_result(tmp_path):
    result = load_manual_results(tmp_path / "nope")

    assert result.parsed == ()
    assert result.errors == ()


@pytest.mark.parametrize(
    ("row", "problem"),
    [
        ("24-03-2024,Alphaland,Betaland,Alphaland,normal,1,,,,,,,", "date"),
        ("2024-03-07,Alphaland,Alphaland,Alphaland,normal,1,,,,,,,", "teams"),
        ("2024-03-07,Alphaland,Betaland,Gammaland,normal,1,,,,,,,", "winner"),
        ("2024-03-07,Alphaland,Betaland,,normal,1,,,,,,,", "winner"),
        ("2024-03-07,Alphaland,Betaland,Alphaland,tie,,,,,,,,", "winner"),
        ("2024-03-07,Alphaland,Betaland,Alphaland,thrashing,1,,,,,,,", "result_type"),
        ("2024-03-07,Alphaland,Betaland,Alphaland,normal,lots,,,,,,,", "margin_runs"),
        ("2024-03-07,Alphaland,Betaland,Alphaland,normal,1,,,,Gammaland,bat,,", "toss"),
        ("2024-03-07,Alphaland,Betaland,Alphaland,normal,1,,,,Betaland,bowl,,", "toss"),
        ("2024-03-07,Alphaland,Betaland,Alphaland,normal,1,,,,Betaland,,,", "toss"),
        ("2024-03-07,Alphaland,Betaland,Alphaland,normal,1,,,,,bat,,", "toss"),
        ("2024-03-07, ,Betaland,Alphaland,normal,1,,,,,,,", "teams"),
    ],
)
def test_invalid_rows_are_reported_with_file_and_line(tmp_path, row, problem):
    write_csv(tmp_path, "bad.csv", [row])

    result = load_manual_results(tmp_path)

    assert result.parsed == ()
    (error,) = result.errors
    assert "bad.csv:2" in error
    assert problem in error


def test_wrong_header_is_reported(tmp_path):
    (tmp_path / "x.csv").write_text("when,who\n2024-01-01,Alphaland\n")

    result = load_manual_results(tmp_path)

    assert result.parsed == ()
    assert "header" in result.errors[0]


def test_unreadable_file_is_reported_not_raised(tmp_path):
    (tmp_path / "latin1.csv").write_bytes(
        HEADER.encode() + "2024-01-01,Caf\xe9land".encode("latin-1")
    )

    result = load_manual_results(tmp_path)

    assert result.parsed == ()
    assert "latin1.csv" in result.errors[0]


def test_duplicate_rows_are_reported(tmp_path):
    row = "2024-03-07,Alphaland,Betaland,Alphaland,normal,1,,,,,,,"
    write_csv(tmp_path, "a.csv", [row, row])

    result = load_manual_results(tmp_path)

    assert len(result.parsed) == 1
    assert "duplicate" in result.errors[0]


def test_merge_drops_manual_rows_that_cricsheet_already_has(tmp_path):
    cricsheet = [
        parse_match(
            make_cricsheet_match(teams=("Betaland", "Alphaland"), date="2024-03-07"), "cs_1"
        )
    ]
    write_csv(
        tmp_path,
        "m.csv",
        [
            "2024-03-07,Alphaland,Betaland,Betaland,normal,5,,,,,,,",
            "2024-03-09,Alphaland,Betaland,Alphaland,normal,5,,,,,,,",
        ],
    )
    manual = load_manual_results(tmp_path).parsed

    merged, superseded = merge_sources(cricsheet, manual)

    assert [p.match.match_id for p in merged] == ["cs_1", "man_2024-03-09_alphaland_betaland"]
    assert superseded == ("man_2024-03-07_alphaland_betaland",)
