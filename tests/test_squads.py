# ruff: noqa: E501  (sample wiki rows must stay on one line, as on the real pages)
from cwc27.players.squads import (
    SquadEntry,
    load_known_styles,
    match_players,
    parse_squads,
    style_from_text,
)

TEMPLATE_PAGE = """
== Key ==
Some text.
==Alphaland==
Coach: [[Someone]]
{{National cricket ODI squad start}}
{{National cricket ODI squad player |sn=45 |player=[[Rohit Sharma]] |other=[[Captain (cricket)|c]] |age={{Birth date|1987}} |role=Batsman |bowling style=Right-arm [[off spin]] |domestic team=[[Mumbai]]}}
{{National cricket ODI squad player |sn=1 |player=[[K. L. Rahul|KL Rahul]] |other=[[Wicket-keeper|wk]] |role=Wicket keeper |bowling style=– }}
{{National cricket ODI squad player |sn=20 |player=<s>[[Axar Patel]]</s> |age=
{{Birth date|1994}} |role=All-rounder |bowling style=[[Slow left-arm orthodox]]}}
|}
==Statistics==
{{National cricket ODI squad player |player=[[Not A Squad]] |role=Bowler}}
"""

TABLE_PAGE = """
==Group A==
===Betaland===
{| border="0"
!Player
|-
| 93 || <s>[[Jasprit Bumrah]]</s> || {{Birth date|1993}} || 89 || Right || Right-arm [[fast bowling|medium-fast]] || {{flagicon|IND}} [[Gujarat]]
|-
| 17 || [[Rishabh Pant]] ([[Wicket-Keeper|wk]]) || {{Birth date|1997}} || 31 || Left || – || [[Delhi]]
|-
| 2 || [[Arshdeep Singh (cricketer)|Arshdeep Singh]] || {{Birth date|1999}} || 8 || Left || Left-arm [[fast bowling|medium-fast]] || [[Punjab]]
|}
== References ==
"""


def test_template_rows_are_parsed_per_team():
    entries = parse_squads(TEMPLATE_PAGE, known_teams={"Alphaland"})

    assert [e.name for e in entries] == ["Rohit Sharma", "KL Rahul", "Axar Patel"]
    rohit, rahul, axar = entries
    assert (rohit.team, rohit.role, rohit.bowling_style, rohit.keeper) == (
        "Alphaland",
        "Batsman",
        "spin",
        False,
    )
    assert (rahul.keeper, rahul.bowling_style) == (True, None)
    assert (axar.withdrawn, axar.role, axar.bowling_style) == (True, "All-rounder", "spin")


def test_table_rows_are_parsed_under_team_subheadings():
    entries = parse_squads(TABLE_PAGE, known_teams={"Betaland"})

    assert [(e.name, e.withdrawn, e.keeper, e.bowling_style) for e in entries] == [
        ("Jasprit Bumrah", True, False, "pace"),
        ("Rishabh Pant", False, True, None),
        ("Arshdeep Singh", False, False, "pace"),
    ]
    assert entries[0].role is None  # this layout has no role column


def test_rows_outside_known_team_sections_are_ignored():
    assert all(e.team == "Alphaland" for e in parse_squads(TEMPLATE_PAGE, {"Alphaland"}))


def test_bowling_style_text_maps_to_pace_or_spin():
    assert style_from_text("Right-arm leg break googly") == "spin"
    assert style_from_text("Left-arm wrist spin") == "spin"
    assert style_from_text("Slow left arm orthodox") == "spin"
    assert style_from_text("Right-arm fast-medium") == "pace"
    assert style_from_text("Right-arm medium") == "pace"
    assert style_from_text("–") is None
    assert style_from_text("") is None


def entry(name, team="India"):
    return SquadEntry(team, name, False, None, None, False)


CANDIDATES = {
    "India": [
        ("id1", "RG Sharma"),
        ("id2", "Shubman Gill"),
        ("id3", "KL Rahul"),
        ("id4", "Mohammed Shami"),
        ("id5", "Mohammed Siraj"),
        ("id6", "AR Patel"),
        ("id7", "HH Pandya"),
        ("id8", "KH Pandya"),
    ]
}


def test_exact_names_match_first():
    matched, unmatched = match_players([entry("Shubman Gill"), entry("KL Rahul")], CANDIDATES)

    assert [m.player_id for m in matched] == ["id2", "id3"]
    assert unmatched == ()


def test_full_names_match_initials_and_surname():
    matched, _ = match_players([entry("Rohit Sharma"), entry("Axar Patel")], CANDIDATES)

    assert [(m.wiki_name, m.player_id, m.cricsheet_name) for m in matched] == [
        ("Rohit Sharma", "id1", "RG Sharma"),
        ("Axar Patel", "id6", "AR Patel"),
    ]


def test_ambiguous_or_unknown_names_are_left_unmatched():
    # Two Pandyas with initial H/K: Hardik matches HH; "Ravi Pandya" matches neither.
    matched, unmatched = match_players(
        [entry("Hardik Pandya"), entry("Ravi Pandya"), entry("Nobody Here")], CANDIDATES
    )

    assert [m.player_id for m in matched] == ["id7"]
    assert [u.name for u in unmatched] == ["Ravi Pandya", "Nobody Here"]


def test_a_team_with_no_candidates_leaves_everyone_unmatched():
    matched, unmatched = match_players([entry("Rashid Khan", team="Afghanistan")], CANDIDATES)

    assert matched == () and [u.name for u in unmatched] == ["Rashid Khan"]


SRI_LANKA = {
    "Sri Lanka": [("k1", "BKG Mendis"), ("k2", "PHKD Mendis"), ("a1", "KIC Asalanka")],
    "Pakistan": [("w1", "Mohammad Wasim"), ("s1", "Agha Salman")],
}


def test_a_unique_surname_in_the_team_matches_despite_different_initials():
    matched, unmatched = match_players([entry("Charith Asalanka", "Sri Lanka")], SRI_LANKA)

    assert [m.player_id for m in matched] == ["a1"] and unmatched == ()


def test_a_shared_surname_with_no_initial_match_stays_unmatched():
    _, unmatched = match_players([entry("Kusal Mendis", "Sri Lanka")], SRI_LANKA)

    assert [u.name for u in unmatched] == ["Kusal Mendis"]


def test_junior_and_senior_suffixes_are_ignored():
    matched, _ = match_players([entry("Mohammad Wasim Jr.", "Pakistan")], SRI_LANKA)

    assert [m.player_id for m in matched] == ["w1"]


def test_aliases_resolve_names_in_a_different_order():
    aliases = {("Pakistan", "Salman Ali Agha"): "Agha Salman"}

    matched, _ = match_players([entry("Salman Ali Agha", "Pakistan")], SRI_LANKA, aliases)

    assert [(m.player_id, m.cricsheet_name) for m in matched] == [("s1", "Agha Salman")]


def test_known_styles_come_from_squad_files_with_later_files_winning(tmp_path):
    old, new = tmp_path / "a.csv", tmp_path / "b.csv"
    header = (
        "tournament,team,wiki_name,player_id,cricsheet_name,keeper,role,bowling_style,withdrawn\n"
    )
    old.write_text(header + "t,X,P,p1,P,False,,spin,False\nt,X,Q,q1,Q,False,,pace,False\n")
    new.write_text(header + "t,X,P,p1,P,False,,pace,False\nt,X,R,r1,R,False,,,False\n")

    styles = load_known_styles([old, new])

    assert styles == {"p1": "pace", "q1": "pace"}
