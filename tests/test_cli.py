import pytest

from cwc27.cli import main
from cwc27.store import MatchStore
from tests.conftest import make_cricsheet_match


def test_ingest_from_local_zip_loads_matches(tmp_path, monkeypatch, cricsheet_zip, capsys):
    monkeypatch.setenv("CWC27_DATA_DIR", str(tmp_path / "data"))
    bad = make_cricsheet_match()
    del bad["info"]["toss"]
    zip_path = cricsheet_zip(
        {
            "1": make_cricsheet_match(date="2023-06-01"),
            "2": make_cricsheet_match(date="2024-01-01"),
            "3": bad,
        }
    )

    exit_code = main(["ingest", "--zip", str(zip_path)])

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "Loaded 2 matches (2 Cricsheet, 0 manual; 1 since 2023-11-20)" in out
    assert "Skipped 1 file" in out
    assert "3.json" in out
    assert len(MatchStore(tmp_path / "data" / "processed" / "cwc27.duckdb").load_matches()) == 2


def test_ingest_merges_manual_results(tmp_path, monkeypatch, cricsheet_zip, capsys):
    data = tmp_path / "data"
    monkeypatch.setenv("CWC27_DATA_DIR", str(data))
    (data / "manual").mkdir(parents=True)
    (data / "manual" / "extra.csv").write_text(
        "date,team_a,team_b,winner,result_type,margin_runs,margin_wickets,"
        "venue,city,toss_winner,toss_decision,event,ref\n"
        "2024-01-01,Alphaland,Betaland,Betaland,normal,,2,,,,,,\n"  # Cricsheet has this one
        "2024-02-01,Gammaland,Betaland,Gammaland,normal,9,,,,,,,\n"
    )
    zip_path = cricsheet_zip({"1": make_cricsheet_match(date="2024-01-01")})

    exit_code = main(["ingest", "--zip", str(zip_path)])

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "1 manual" in out
    assert "1 manual result(s) now covered by Cricsheet" in out
    matches = MatchStore(data / "processed" / "cwc27.duckdb").load_matches()
    assert [m.source for m in matches] == ["cricsheet", "manual"]


def test_backtest_reports_each_model(tmp_path, monkeypatch, cricsheet_zip, capsys):
    monkeypatch.setenv("CWC27_DATA_DIR", str(tmp_path / "data"))
    zip_path = cricsheet_zip(
        {
            "1": make_cricsheet_match(teams=("India", "Australia"), date="2023-12-01"),
            "2": make_cricsheet_match(teams=("India", "Australia"), date="2024-01-01"),
        }
    )
    main(["ingest", "--zip", str(zip_path)])
    capsys.readouterr()

    exit_code = main(["backtest", "--k", "20", "--home-advantage", "50"])

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "k=20" in out and "home advantage=50" in out
    for name in ("Coin flip", "Win rate", "Elo"):
        assert name in out
    assert "Since 2023 WC final" in out


@pytest.mark.parametrize("args", [["--k", "0"], ["--k", "-5"], ["--home-advantage", "-1"]])
def test_backtest_rejects_invalid_elo_settings(args):
    with pytest.raises(SystemExit) as exit_info:
        main(["backtest", *args])

    assert exit_info.value.code == 2


def test_backtest_fails_cleanly_without_data(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CWC27_DATA_DIR", str(tmp_path / "data"))

    exit_code = main(["backtest"])

    assert exit_code == 1
    assert "cwc27 ingest" in capsys.readouterr().err


def test_ingest_fails_cleanly_on_corrupt_zip(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CWC27_DATA_DIR", str(tmp_path / "data"))
    corrupt = tmp_path / "corrupt.zip"
    corrupt.write_bytes(b"not a zip")

    exit_code = main(["ingest", "--zip", str(corrupt)])

    assert exit_code == 1
    assert "Could not read" in capsys.readouterr().err


def test_ingest_fails_when_nothing_parses(tmp_path, monkeypatch, cricsheet_zip, capsys):
    monkeypatch.setenv("CWC27_DATA_DIR", str(tmp_path / "data"))
    bad = make_cricsheet_match()
    del bad["info"]["teams"]

    exit_code = main(["ingest", "--zip", str(cricsheet_zip({"1": bad}))])

    assert exit_code == 1
    assert "No matches parsed" in capsys.readouterr().err


def test_ingest_fails_cleanly_when_zip_missing(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CWC27_DATA_DIR", str(tmp_path / "data"))

    exit_code = main(["ingest", "--zip", str(tmp_path / "nope.zip")])

    assert exit_code == 1
    assert "not found" in capsys.readouterr().err
