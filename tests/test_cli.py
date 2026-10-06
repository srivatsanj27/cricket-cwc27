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
    assert "Loaded 2 matches (1 since 2023-11-19)" in out
    assert "Skipped 1 file" in out
    assert "3.json" in out
    assert len(MatchStore(tmp_path / "data" / "processed" / "cwc27.duckdb").load_matches()) == 2


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
