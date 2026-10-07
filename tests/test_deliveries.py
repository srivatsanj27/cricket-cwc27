from datetime import date

import pytest

from cwc27.ingest.cricsheet import ParseError, parse_match, parse_zip
from cwc27.ingest.deliveries import phase_of
from cwc27.store import MatchStore
from tests.conftest import ball, make_cricsheet_match


def two_innings():
    return [
        {
            "team": "Alphaland",
            "overs": [
                {
                    "over": 0,
                    "deliveries": [
                        ball("A Player1", "B Player1", runs=4, non_striker="A Player2"),
                        ball("A Player1", "B Player1", extras={"wides": 1}),
                    ],
                },
                {
                    "over": 44,
                    "deliveries": [
                        ball(
                            "A Player2",
                            "B Player2",
                            wicket={
                                "kind": "stumped",
                                "player_out": "A Player2",
                                "fielders": [{"name": "B Player3"}],
                            },
                        )
                    ],
                },
            ],
        },
        {
            "team": "Betaland",
            "overs": [
                {
                    "over": 12,
                    "deliveries": [
                        ball("B Player1", "A Player5", runs=1, extras={"legbyes": 1}),
                        ball(
                            "B Player2",
                            "A Player5",
                            non_striker="B Player1",
                            wicket={"kind": "run out", "player_out": "B Player1"},
                        ),
                    ],
                }
            ],
        },
    ]


def parsed(innings=None):
    data = make_cricsheet_match(innings=innings if innings is not None else two_innings())
    return data, parse_match(data, match_id="cs_1", with_deliveries=True)


def test_one_delivery_per_ball_with_teams_and_position():
    data, p = parsed()

    first = p.deliveries[0]
    assert len(p.deliveries) == 5
    assert (first.match_id, first.innings) == ("cs_1", 1)
    assert (first.batting_team, first.bowling_team) == ("Alphaland", "Betaland")
    assert (first.over, first.ball, first.phase) == (0, 1, "powerplay")
    assert (first.batter, first.bowler, first.non_striker) == (
        "A Player1",
        "B Player1",
        "A Player2",
    )
    assert first.batter_id == data["info"]["registry"]["people"]["A Player1"]
    assert first.bowler_id == data["info"]["registry"]["people"]["B Player1"]
    assert (first.runs_batter, first.runs_extras, first.runs_total) == (4, 0, 4)
    assert first.is_legal


def test_balls_are_numbered_within_each_over():
    _, p = parsed()

    assert [d.ball for d in p.deliveries[:2]] == [1, 2]


def test_second_innings_swaps_the_teams():
    _, p = parsed()

    last = p.deliveries[-1]
    assert (last.innings, last.batting_team, last.bowling_team) == (2, "Betaland", "Alphaland")
    assert last.phase == "middle"


def test_extras_are_recorded_and_wides_are_not_legal_balls():
    _, p = parsed()

    wide, legbye = p.deliveries[1], p.deliveries[3]
    assert (wide.wides, wide.runs_extras, wide.is_legal) == (1, 1, False)
    assert (legbye.legbyes, legbye.runs_batter, legbye.runs_total, legbye.is_legal) == (
        1,
        1,
        2,
        True,
    )


def test_wickets_record_the_kind_who_was_out_and_the_fielder():
    data, p = parsed()

    stumping, run_out = p.deliveries[2], p.deliveries[4]
    assert (stumping.wicket_kind, stumping.player_out, stumping.fielder) == (
        "stumped",
        "A Player2",
        "B Player3",
    )
    assert stumping.player_out_id == data["info"]["registry"]["people"]["A Player2"]
    assert stumping.phase == "death"
    assert (run_out.wicket_kind, run_out.player_out, run_out.fielder) == (
        "run out",
        "B Player1",
        None,
    )
    assert p.deliveries[0].wicket_kind is None


def test_every_dismissal_is_counted_and_every_fielder_kept():
    two_out = {
        "batter": "A Player1",
        "bowler": "B Player1",
        "non_striker": "A Player2",
        "runs": {"batter": 0, "extras": 0, "total": 0},
        "wickets": [
            {
                "kind": "run out",
                "player_out": "A Player1",
                "fielders": [{"name": "B Player4"}, {"name": "B Player5"}],
            },
            {"kind": "retired hurt", "player_out": "A Player2"},
        ],
    }
    innings = [{"team": "Alphaland", "overs": [{"over": 3, "deliveries": [two_out]}]}]

    _, p = parsed(innings)

    (d,) = p.deliveries
    assert d.wickets == 2
    assert (d.wicket_kind, d.player_out) == ("run out", "A Player1")
    assert d.fielder == "B Player4 / B Player5"


def test_a_ball_without_a_wicket_counts_zero():
    _, p = parsed()

    assert p.deliveries[0].wickets == 0
    assert p.deliveries[2].wickets == 1


@pytest.mark.parametrize(
    ("over", "phase"),
    [(0, "powerplay"), (9, "powerplay"), (10, "middle"), (39, "middle"), (40, "death")],
)
def test_phases_follow_odi_powerplay_overs(over, phase):
    assert phase_of(over) == phase


def test_super_over_innings_are_skipped():
    innings = [*two_innings(), {"team": "Alphaland", "super_over": True, "overs": []}]
    innings[-1]["overs"] = [{"over": 0, "deliveries": [ball("A Player1", "B Player1", runs=6)]}]

    _, p = parsed(innings)

    assert len(p.deliveries) == 5


def test_a_player_missing_from_the_registry_is_an_error():
    innings = [
        {"team": "Alphaland", "overs": [{"over": 0, "deliveries": [ball("Ghost", "B Player1")]}]}
    ]

    with pytest.raises(ParseError, match="Ghost"):
        parsed(innings)


def test_deliveries_are_only_parsed_when_asked_for():
    data = make_cricsheet_match(innings=two_innings())

    assert parse_match(data, match_id="cs_1").deliveries == ()


def test_parse_zip_loads_deliveries_only_from_the_given_date(cricsheet_zip):
    path = cricsheet_zip(
        {
            "1": make_cricsheet_match(date="2018-06-01", innings=two_innings()),
            "2": make_cricsheet_match(date="2019-06-01", innings=two_innings()),
        }
    )

    result = parse_zip(path, deliveries_since=date(2019, 1, 1))

    assert [len(p.deliveries) for p in result.parsed] == [0, 5]


def test_store_saves_and_replaces_deliveries(tmp_path):
    store = MatchStore(tmp_path / "test.duckdb")
    _, p = parsed()

    store.save([p])
    store.save([p])

    assert store.count_deliveries() == 5
