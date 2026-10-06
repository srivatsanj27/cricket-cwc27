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


def test_tune_reports_best_setting(tmp_path, monkeypatch, cricsheet_zip, capsys):
    monkeypatch.setenv("CWC27_DATA_DIR", str(tmp_path / "data"))
    zip_path = cricsheet_zip(
        {
            "1": make_cricsheet_match(teams=("India", "Australia"), date="2022-03-01"),
            "2": make_cricsheet_match(teams=("India", "Australia"), date="2022-04-01"),
            "3": make_cricsheet_match(teams=("India", "Australia"), date="2024-01-01"),
        }
    )
    main(["ingest", "--zip", str(zip_path)])
    capsys.readouterr()

    exit_code = main(["tune", "--k-values", "10,40", "--home-values", "0,60", "--top", "3"])

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "Top 3 of 4 settings" in out
    assert "Best: k=" in out
    assert "(current defaults)" in out


@pytest.mark.parametrize(
    "args",
    [
        ["--k-values", "10,abc"],
        ["--k-values", "0,10"],
        ["--k-values", "inf"],
        ["--home-values", "-5"],
        ["--top", "0"],
    ],
)
def test_tune_rejects_invalid_grids(args):
    with pytest.raises(SystemExit) as exit_info:
        main(["tune", *args])

    assert exit_info.value.code == 2


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


FIXTURES_HEADER = "date,series,match_no,team_a,team_b,venue,city\n"


def _setup_live(tmp_path, monkeypatch, cricsheet_zip):
    """A data dir with past India v Australia ODIs and a two-match series in Mumbai."""
    data = tmp_path / "data"
    monkeypatch.setenv("CWC27_DATA_DIR", str(data))
    data.mkdir()
    (data / "fixtures.csv").write_text(
        FIXTURES_HEADER
        + "2026-10-12,Australia tour of India,1,India,Australia,Wankhede Stadium,Mumbai\n"
        + "2026-10-15,Australia tour of India,2,India,Australia,Wankhede Stadium,Mumbai\n"
    )
    return cricsheet_zip(
        {
            "1": make_cricsheet_match(teams=("India", "Australia"), date="2024-01-01"),
            "2": make_cricsheet_match(teams=("Australia", "India"), date="2024-02-01"),
        }
    )


def test_result_records_a_match_using_the_fixture_venue(
    tmp_path, monkeypatch, cricsheet_zip, capsys
):
    _setup_live(tmp_path, monkeypatch, cricsheet_zip)

    exit_code = main(
        ["result", "2026-10-12", "India", "Australia", "--winner", "India", "--runs", "25"]
    )

    assert exit_code == 0
    assert "Recorded" in capsys.readouterr().out
    recent = (tmp_path / "data" / "manual" / "recent.csv").read_text()
    assert "2026-10-12,India,Australia,India,normal,25,,Wankhede Stadium,Mumbai" in recent
    assert "Australia tour of India" in recent


def test_result_rejects_a_duplicate(tmp_path, monkeypatch, cricsheet_zip, capsys):
    _setup_live(tmp_path, monkeypatch, cricsheet_zip)
    args = ["result", "2026-10-12", "India", "Australia", "--tie"]
    main(args)

    exit_code = main(args)

    assert exit_code == 1
    assert "already" in capsys.readouterr().err


def test_result_rejects_a_winner_who_did_not_play(tmp_path, monkeypatch, cricsheet_zip, capsys):
    _setup_live(tmp_path, monkeypatch, cricsheet_zip)

    exit_code = main(["result", "2026-10-12", "India", "Australia", "--winner", "England"])

    assert exit_code == 1
    assert "winner" in capsys.readouterr().err


def test_result_needs_exactly_one_outcome():
    with pytest.raises(SystemExit) as exit_info:
        main(["result", "2026-10-12", "India", "Australia"])

    assert exit_info.value.code == 2


def test_update_predicts_then_scores_after_a_result(tmp_path, monkeypatch, cricsheet_zip, capsys):
    zip_path = _setup_live(tmp_path, monkeypatch, cricsheet_zip)
    log_path = tmp_path / "data" / "predictions_log.csv"

    first = main(["update", "--zip", str(zip_path), "--today", "2026-10-10", "--sims", "500"])

    out = capsys.readouterr().out
    assert first == 0
    assert "Upcoming" in out and "India" in out
    assert "Australia tour of India" in out
    assert log_path.read_text().count("\n") == 3  # header + two predictions

    main(["result", "2026-10-12", "India", "Australia", "--winner", "India", "--wickets", "5"])
    capsys.readouterr()
    second = main(["update", "--zip", str(zip_path), "--today", "2026-10-13", "--sims", "500"])

    out = capsys.readouterr().out
    assert second == 0
    assert "Scored" in out
    assert "Track record: 1 match" in out
    assert "1-0" in out  # series score so far
