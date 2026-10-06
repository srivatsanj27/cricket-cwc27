from datetime import date

from cwc27.ingest.cricsheet import parse_match
from cwc27.models import ResultType
from cwc27.store import MatchStore
from tests.conftest import make_cricsheet_match


def _parsed(match_id, day, outcome=None):
    return parse_match(make_cricsheet_match(date=day, outcome=outcome), match_id=match_id)


def test_round_trips_matches_in_date_order(tmp_path):
    store = MatchStore(tmp_path / "test.duckdb")
    store.save([_parsed("cs_2", "2024-03-01"), _parsed("cs_1", "2024-01-01")])

    matches = store.load_matches()

    assert [m.match_id for m in matches] == ["cs_1", "cs_2"]
    assert matches[0].date == date(2024, 1, 1)
    assert matches[0].result_type is ResultType.NORMAL


def test_saving_same_match_twice_replaces_it(tmp_path):
    store = MatchStore(tmp_path / "test.duckdb")
    store.save([_parsed("cs_1", "2024-01-01")])
    store.save([_parsed("cs_1", "2024-01-01", outcome={"result": "no result"})])

    matches = store.load_matches()

    assert len(matches) == 1
    assert matches[0].result_type is ResultType.NO_RESULT
    assert store.count_appearances() == 22


def test_load_matches_since_filters_by_date(tmp_path):
    store = MatchStore(tmp_path / "test.duckdb")
    store.save([_parsed("cs_1", "2023-06-01"), _parsed("cs_2", "2023-11-20")])

    matches = store.load_matches(since=date(2023, 11, 19))

    assert [m.match_id for m in matches] == ["cs_2"]


def test_data_persists_across_store_instances(tmp_path):
    path = tmp_path / "test.duckdb"
    MatchStore(path).save([_parsed("cs_1", "2024-01-01")])

    assert len(MatchStore(path).load_matches()) == 1
