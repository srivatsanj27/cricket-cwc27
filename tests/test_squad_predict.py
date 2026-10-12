from datetime import date

import pytest

from cwc27.players.picker import Candidate, SquadRules
from cwc27.players.ratings import PlayerRating
from cwc27.players.roles import PlayerRole, Role
from cwc27.players.squad_predict import (
    CertainPick,
    SquadInputs,
    announced_ids,
    fallback_squad,
    load_announced,
    load_certain_picks,
    missing_certain_picks,
    predict_squad,
    squad_hits,
    team_candidates,
)

TEAMS = ("Alphaland", "Betaland")
HEADER = "tournament,team,wiki_name,player_id,cricsheet_name,keeper,role,bowling_style,withdrawn\n"


def inputs():
    roles = {
        "a": PlayerRole("a", "A One", "Alphaland", Role.BATTER, None),
        "k": PlayerRole("k", "K Keeper", "Alphaland", Role.KEEPER, None),
        "b": PlayerRole("b", "B Other", "Betaland", Role.BOWLER, "pace"),
    }
    ratings = {"a": PlayerRating("a", "A One", 12.0, 0.0, 300, 0, date(2026, 1, 1))}
    shares = {("Alphaland", "a"): 0.8}
    return SquadInputs(roles, ratings, shares)


def test_candidates_are_the_teams_players_with_ratings_and_shares():
    cands = {c.player_id: c for c in team_candidates("Alphaland", inputs())}

    assert set(cands) == {"a", "k"}
    assert (cands["a"].batting, cands["a"].selection_share) == (12.0, 0.8)
    assert (cands["k"].batting, cands["k"].selection_share) == (0.0, 0.0)  # no rating yet


def test_predict_squad_picks_from_the_team_only():
    squad = predict_squad("Alphaland", inputs(), SquadRules(size=15))

    assert {c.player_id for c in squad} == {"a", "k"}


def test_announced_squads_keep_unmatched_players_and_withdrawals(tmp_path):
    path = tmp_path / "squads.csv"
    path.write_text(
        HEADER
        + "ct,Alphaland,A One,a,A One,False,,,False\n"
        + "ct,Alphaland,Hurt Guy,h,H Guy,False,,pace,True\n"
        + "ct,Afghanistan,Rashid Khan,,,False,,spin,False\n"
    )

    players = load_announced(path)

    assert announced_ids(players) == {"Alphaland": {"a", "h"}}
    assert [p.name for p in fallback_squad("Afghanistan", players)] == ["Rashid Khan"]
    assert [p.name for p in fallback_squad("Alphaland", players)] == ["A One"]


def test_squad_hits_count_the_overlap():
    predicted = [
        Candidate("a", "A", Role.BATTER, None, 0, 0, 0),
        Candidate("x", "X", Role.BATTER, None, 0, 0, 0),
    ]

    assert squad_hits(predicted, {"a", "b"}) == 1


def test_certain_picks_load_from_csv(tmp_path):
    path = tmp_path / "certain.csv"
    path.write_text("player_id,name,team\nk,K Keeper,Alphaland\n")

    assert load_certain_picks(TEAMS, path) == (CertainPick("k", "K Keeper", "Alphaland"),)


def test_certain_picks_need_the_right_columns(tmp_path):
    path = tmp_path / "certain.csv"
    path.write_text("id,name\nk,K Keeper\n")

    with pytest.raises(ValueError, match="header"):
        load_certain_picks(TEAMS, path)


@pytest.mark.parametrize(
    "row", ["k,K Keeper", "k,K Keeper,", ",K Keeper,Alphaland", "k,K,Alphalnd"]
)
def test_certain_picks_with_a_blank_field_or_unknown_team_are_rejected(tmp_path, row):
    path = tmp_path / "certain.csv"
    path.write_text(f"player_id,name,team\n{row}\n")

    with pytest.raises(ValueError, match=":2:"):
        load_certain_picks(TEAMS, path)


def test_a_missing_certain_picks_file_means_none(tmp_path):
    assert load_certain_picks(TEAMS, tmp_path / "nope.csv") == ()


def test_predict_squad_puts_certain_picks_in_first():
    squad = predict_squad("Alphaland", inputs(), SquadRules(size=1), certain={"k"})

    assert [c.player_id for c in squad] == ["k"]


def test_certain_picks_with_no_recent_odis_are_reported():
    picks = (
        CertainPick("k", "K Keeper", "Alphaland"),
        CertainPick("gone", "Long Gone", "Alphaland"),
        CertainPick("b", "B Other", "Betaland"),
    )

    assert missing_certain_picks("Alphaland", inputs(), picks) == ("Long Gone",)
