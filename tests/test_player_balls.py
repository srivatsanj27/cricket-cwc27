from datetime import date

import pytest

from cwc27.ingest.cricsheet import parse_match
from cwc27.players.balls import (
    BowledBall,
    FacedBall,
    bowled_averages,
    faced_averages,
    load_bowled,
    load_faced,
)
from cwc27.store import MatchStore
from tests.conftest import ball, make_cricsheet_match

INNINGS = [
    {
        "team": "Alphaland",
        "overs": [
            {
                "over": 0,
                "deliveries": [
                    ball("A Player1", "B Player1", runs=4),
                    ball("A Player1", "B Player1", extras={"wides": 1}),
                    ball("A Player1", "B Player1", runs=1, extras={"noballs": 1}),
                    ball("A Player1", "B Player1", extras={"legbyes": 2}),
                ],
            },
            {
                "over": 45,
                "deliveries": [
                    ball(
                        "A Player1",
                        "B Player2",
                        wicket={
                            "kind": "caught",
                            "player_out": "A Player1",
                            "fielders": [{"name": "B Player3"}],
                        },
                    ),
                    ball(
                        "A Player2",
                        "B Player2",
                        non_striker="A Player3",
                        wicket={"kind": "run out", "player_out": "A Player2"},
                    ),
                    ball(
                        "A Player3",
                        "B Player2",
                        wicket={"kind": "retired hurt", "player_out": "A Player3"},
                    ),
                ],
            },
        ],
    }
]


@pytest.fixture
def store(tmp_path):
    s = MatchStore(tmp_path / "test.duckdb")
    old = make_cricsheet_match(date="2018-06-01", innings=INNINGS)
    new = make_cricsheet_match(date="2024-03-10", innings=INNINGS)
    s.save(
        [
            parse_match(old, "cs_old", with_deliveries=True),
            parse_match(new, "cs_new", with_deliveries=True),
        ]
    )
    return s


def test_faced_balls_exclude_wides(store):
    faced = load_faced(store, since=date(2024, 1, 1))

    assert len(faced) == 6  # 7 deliveries, one of them a wide
    first = faced[0]
    assert isinstance(first, FacedBall)
    assert (first.match_id, first.date, first.phase) == ("cs_new", date(2024, 3, 10), "powerplay")
    assert (first.batter, first.runs, first.out) == ("A Player1", 4, False)


def test_a_no_ball_counts_as_faced_and_leg_byes_are_not_the_batters_runs(store):
    faced = load_faced(store, since=date(2024, 1, 1))

    assert [f.runs for f in faced[:3]] == [4, 1, 0]


def test_batter_is_out_when_dismissed_but_not_when_retired_hurt(store):
    faced = load_faced(store, since=date(2024, 1, 1))

    outs = {(f.batter, f.out) for f in faced[3:]}
    assert outs == {("A Player1", True), ("A Player2", True), ("A Player3", False)}


def test_bowled_balls_include_every_delivery(store):
    bowled = load_bowled(store, since=date(2024, 1, 1))

    assert len(bowled) == 7
    assert isinstance(bowled[0], BowledBall)
    # Off the bat + wides + no-balls; byes and leg-byes aren't the bowler's fault.
    assert [b.conceded for b in bowled[:4]] == [4, 1, 2, 0]


def test_only_bowler_dismissals_count_as_wickets(store):
    bowled = load_bowled(store, since=date(2024, 1, 1))

    assert [b.wicket for b in bowled[4:]] == [True, False, False]  # caught, run out, retired


def test_since_filters_by_match_date(store):
    assert {f.match_id for f in load_faced(store, since=date(2018, 1, 1))} == {"cs_old", "cs_new"}
    assert {f.match_id for f in load_faced(store, since=date(2024, 1, 1))} == {"cs_new"}


def test_phase_averages_are_means_per_ball():
    faced = [
        FacedBall("m", date(2024, 1, 1), "powerplay", "p1", "P1", 4, False),
        FacedBall("m", date(2024, 1, 1), "powerplay", "p1", "P1", 0, True),
        FacedBall("m", date(2024, 1, 1), "death", "p1", "P1", 6, False),
    ]
    bowled = [
        BowledBall("m", date(2024, 1, 1), "middle", "b1", "B1", 1, False),
        BowledBall("m", date(2024, 1, 1), "middle", "b1", "B1", 0, True),
        BowledBall("m", date(2024, 1, 1), "middle", "b1", "B1", 2, False),
        BowledBall("m", date(2024, 1, 1), "middle", "b1", "B1", 1, False),
    ]

    bat = faced_averages(faced)
    bowl = bowled_averages(bowled)

    assert (bat["powerplay"].runs, bat["powerplay"].wickets) == (2.0, 0.5)
    assert (bat["death"].runs, bat["death"].wickets) == (6.0, 0.0)
    assert (bowl["middle"].runs, bowl["middle"].wickets) == (1.0, 0.25)


def test_averages_need_at_least_one_ball():
    with pytest.raises(ValueError):
        faced_averages([])
