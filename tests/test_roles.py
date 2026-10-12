from datetime import date

import pytest

from cwc27.ingest.cricsheet import parse_match
from cwc27.players.roles import (
    Override,
    PlayerProfile,
    Role,
    apply_overrides,
    assign_roles,
    classify_role,
    guess_bowling_style,
    load_overrides,
    load_profiles,
)
from cwc27.store import MatchStore
from tests.conftest import ball, make_cricsheet_match


def profile(**changes):
    base = dict(
        player_id="p",
        name="P",
        team="Alphaland",
        appearances=20,
        last_played=date(2026, 1, 1),
        balls_bowled=0,
        powerplay_share=0.0,
        death_share=0.0,
        stumping_wickets=0,
        stumpings=0,
        batting_position=4.0,
    )
    return PlayerProfile(**{**base, **changes})


# --- classify_role ----------------------------------------------------------


def test_a_top_order_player_who_rarely_bowls_is_a_batter():
    assert classify_role(profile(balls_bowled=40)) is Role.BATTER


def test_a_player_with_stumpings_who_does_not_bowl_is_a_keeper():
    assert classify_role(profile(stumpings=3)) is Role.KEEPER


def test_a_regular_bowler_batting_in_the_top_seven_is_an_all_rounder():
    assert classify_role(profile(balls_bowled=20 * 36, batting_position=6.5)) is Role.ALL_ROUNDER


def test_a_regular_bowler_batting_lower_is_a_bowler():
    assert classify_role(profile(balls_bowled=20 * 50, batting_position=9.5)) is Role.BOWLER


def test_a_bowler_who_never_batted_is_a_bowler():
    assert classify_role(profile(balls_bowled=20 * 50, batting_position=None)) is Role.BOWLER


# --- guess_bowling_style ------------------------------------------------------


def test_stumpings_off_a_bowler_mark_a_spinner():
    p = profile(balls_bowled=1200, stumping_wickets=2, powerplay_share=0.15, death_share=0.1)

    assert guess_bowling_style(p) == "spin"


def test_opening_the_bowling_marks_a_pacer():
    p = profile(balls_bowled=1200, powerplay_share=0.35, death_share=0.2)

    assert guess_bowling_style(p) == "pace"


def test_rarely_bowling_in_the_powerplay_marks_a_spinner_even_at_the_death():
    p = profile(balls_bowled=1200, powerplay_share=0.02, death_share=0.2)

    assert guess_bowling_style(p) == "spin"


def test_a_powerplay_share_in_between_is_left_for_an_override():
    assert guess_bowling_style(profile(balls_bowled=1200, powerplay_share=0.18)) is None


def test_a_lower_order_all_rounder_batting_at_seven_and_a_half_still_counts():
    assert classify_role(profile(balls_bowled=20 * 50, batting_position=7.4)) is Role.ALL_ROUNDER


def test_too_few_balls_gives_no_guess():
    assert guess_bowling_style(profile(balls_bowled=100, powerplay_share=0.4)) is None


def test_non_bowlers_have_no_style():
    assert guess_bowling_style(profile(balls_bowled=0)) is None


# --- overrides ----------------------------------------------------------------


def test_overrides_replace_the_guessed_role_and_style(tmp_path):
    path = tmp_path / "overrides.csv"
    path.write_text("player_id,name,role,bowling_style\np,P,keeper,\nq,Q,,spin\n")

    overrides = load_overrides(path)

    assert apply_overrides("p", Role.BATTER, None, overrides) == (Role.KEEPER, None)
    assert apply_overrides("q", Role.BOWLER, "pace", overrides) == (Role.BOWLER, "spin")
    assert apply_overrides("r", Role.BOWLER, "pace", overrides) == (Role.BOWLER, "pace")


def test_overrides_reject_unknown_roles_and_styles(tmp_path):
    path = tmp_path / "overrides.csv"
    path.write_text("player_id,name,role,bowling_style\np,P,captain,\n")

    with pytest.raises(ValueError, match="overrides.csv:2"):
        load_overrides(path)


def test_missing_overrides_file_means_no_overrides(tmp_path):
    assert load_overrides(tmp_path / "nope.csv") == {}


# --- load_profiles --------------------------------------------------------------


def test_profiles_are_built_from_appearances_and_deliveries(tmp_path):
    stumped = {"kind": "stumped", "player_out": "A Player3", "fielders": [{"name": "B Player11"}]}
    innings = [
        {
            "team": "Alphaland",
            "overs": [
                {"over": 0, "deliveries": [ball("A Player1", "B Player1", runs=1)]},
                {"over": 1, "deliveries": [ball("A Player2", "B Player1", runs=1)]},
                {"over": 20, "deliveries": [ball("A Player3", "B Player2", wicket=stumped)]},
            ],
        }
    ]
    store = MatchStore(tmp_path / "t.duckdb")
    data = make_cricsheet_match(date="2025-05-01", innings=innings)
    store.save([parse_match(data, "cs_1", with_deliveries=True)])

    profiles = {p.name: p for p in load_profiles(store, since=date(2025, 1, 1))}

    opener, keeper, spinner = profiles["A Player1"], profiles["B Player11"], profiles["B Player2"]
    assert (opener.team, opener.appearances, opener.batting_position) == ("Alphaland", 1, 1.0)
    assert profiles["A Player3"].batting_position == 3.0
    assert keeper.stumpings == 1
    assert (spinner.balls_bowled, spinner.stumping_wickets) == (1, 1)
    assert profiles["B Player1"].powerplay_share == 1.0
    assert profiles["B Player5"].batting_position is None  # in the XI, never batted


def test_assign_roles_uses_recent_role_and_full_history_for_keeping_and_style():
    recent = [
        profile(player_id="pant", name="Pant", stumpings=0, appearances=10),
        profile(player_id="bumrah", name="Bumrah", balls_bowled=10 * 50, batting_position=10.0),
    ]
    history = [
        profile(player_id="pant", name="Pant", stumpings=5, appearances=40),
        profile(player_id="bumrah", name="Bumrah", balls_bowled=2000, powerplay_share=0.45),
    ]

    roles = assign_roles(recent, history, {})

    assert (roles["pant"].role, roles["pant"].bowling_style) == (Role.KEEPER, None)
    assert (roles["bumrah"].role, roles["bumrah"].bowling_style) == (Role.BOWLER, "pace")
    assert roles["bumrah"].team == "Alphaland"


def test_assign_roles_applies_overrides_last():
    overrides = {"p": Override(Role.ALL_ROUNDER, "spin")}

    roles = assign_roles([profile()], [profile()], overrides)

    assert (roles["p"].role, roles["p"].bowling_style) == (Role.ALL_ROUNDER, "spin")
