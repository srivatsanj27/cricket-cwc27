import random

from cwc27.simulate.multiseries import rank_teams


def test_more_points_ranks_higher():
    points = {"A": 2, "B": 6, "C": 4}

    assert rank_teams(points, {}, random.Random(1)) == ["B", "C", "A"]


def test_two_way_tie_is_broken_by_head_to_head():
    points = {"A": 4, "B": 4, "C": 0}
    wins_against = {("B", "A"): 1, ("A", "B"): 0}

    assert rank_teams(points, wins_against, random.Random(1)) == ["B", "A", "C"]


def test_three_way_tie_uses_wins_within_the_tied_group():
    points = {"A": 4, "B": 4, "C": 4}
    wins_against = {("A", "B"): 2, ("B", "C"): 1, ("C", "A"): 1}

    assert rank_teams(points, wins_against, random.Random(1))[0] == "A"


def test_level_head_to_head_falls_back_to_a_reproducible_random_draw():
    points = {"A": 4, "B": 4}
    wins_against = {("A", "B"): 1, ("B", "A"): 1}

    first = rank_teams(points, wins_against, random.Random(7))
    again = rank_teams(points, wins_against, random.Random(7))
    orders = {tuple(rank_teams(points, wins_against, random.Random(s))) for s in range(50)}

    assert first == again
    assert orders == {("A", "B"), ("B", "A")}
