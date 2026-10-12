from datetime import date

import pytest

from cwc27.ingest.cricsheet import parse_match
from cwc27.players.picker import Candidate, SquadRules, pick_squad, selection_shares, skill
from cwc27.players.roles import Role
from cwc27.store import MatchStore
from tests.conftest import make_cricsheet_match


def cand(pid, role=Role.BATTER, style=None, batting=0.0, bowling=0.0, share=0.5):
    return Candidate(pid, pid.upper(), role, style, batting, bowling, share)


SMALL = SquadRules(size=5, keepers=1, spinners=1, pacers=1, bowling_options=2)


def test_skill_uses_the_rating_that_matches_the_role():
    rules = SquadRules(skill_scale=10.0)

    assert skill(cand("b", Role.BATTER, batting=20, bowling=99), rules) == 2.0
    assert skill(cand("k", Role.KEEPER, batting=10), rules) == 1.0
    assert skill(cand("w", Role.BOWLER, batting=99, bowling=30), rules) == 3.0
    assert skill(cand("a", Role.ALL_ROUNDER, batting=10, bowling=10), rules) == 2.0


def test_the_best_scoring_players_fill_the_squad():
    pool = [cand(f"p{i}", share=i / 10) for i in range(10)]
    rules = SquadRules(size=3, keepers=0, spinners=0, pacers=0, bowling_options=0)

    squad = pick_squad(pool, rules)

    assert [c.player_id for c in squad] == ["p9", "p8", "p7"]


def test_balance_rules_are_met_before_filling_by_score():
    pool = [cand(f"bat{i}", share=0.9) for i in range(6)] + [
        cand("keeper", Role.KEEPER, share=0.1),
        cand("spinner", Role.BOWLER, "spin", share=0.1),
        cand("pacer", Role.BOWLER, "pace", share=0.2),
    ]

    ids = {c.player_id for c in pick_squad(pool, SMALL)}

    assert {"keeper", "spinner", "pacer"} <= ids
    assert len(ids) == 5


def test_an_all_rounder_counts_as_a_bowling_option_and_by_style():
    pool = [
        cand("ar-spin", Role.ALL_ROUNDER, "spin", share=0.1),
        cand("pacer", Role.BOWLER, "pace", share=0.1),
        cand("keeper", Role.KEEPER, share=0.1),
    ] + [cand(f"bat{i}", share=0.9) for i in range(5)]

    ids = {c.player_id for c in pick_squad(pool, SMALL)}

    assert {"ar-spin", "pacer", "keeper"} <= ids


def test_unknown_styles_count_as_bowling_options_but_not_towards_style_quotas():
    pool = [
        cand("mystery", Role.BOWLER, None, share=0.8),
        cand("spinner", Role.BOWLER, "spin", share=0.1),
        cand("pacer", Role.BOWLER, "pace", share=0.1),
        cand("keeper", Role.KEEPER, share=0.1),
        cand("bat", share=0.9),
    ]

    ids = {c.player_id for c in pick_squad(pool, SMALL)}

    assert ids == {"mystery", "spinner", "pacer", "keeper", "bat"}


def test_a_small_pool_returns_everyone():
    pool = [cand("a"), cand("b")]

    assert len(pick_squad(pool, SMALL)) == 2


def test_skill_weight_can_outrank_selection():
    pool = [cand("regular", batting=-30, share=0.6), cand("star", batting=60, share=0.4)]
    rules = SquadRules(size=1, keepers=0, spinners=0, pacers=0, bowling_options=0,
                       skill_weight=1.0, skill_scale=30.0)  # fmt: skip

    assert [c.player_id for c in pick_squad(pool, rules)] == ["star"]


def test_selection_shares_are_xi_appearances_over_team_matches(tmp_path):
    store = MatchStore(tmp_path / "t.duckdb")
    store.save(
        [
            parse_match(make_cricsheet_match(date="2025-01-01"), "cs_1"),
            parse_match(make_cricsheet_match(date="2025-02-01"), "cs_2"),
            parse_match(make_cricsheet_match(date="2026-02-01"), "cs_3"),
        ]
    )

    shares = selection_shares(store, since=date(2025, 1, 1), until=date(2026, 1, 1))

    alpha = {pid: s for (team, pid), s in shares.items() if team == "Alphaland"}
    assert len(alpha) == 11
    assert all(s == pytest.approx(1.0) for s in alpha.values())
