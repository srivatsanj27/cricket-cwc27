"""Specification for cwc27.players.ratings. Written before the implementation (TDD)."""

from datetime import date

import pytest

from cwc27.players.balls import BowledBall, FacedBall, PhaseAverage
from cwc27.players.ratings import (
    RatingConfig,
    batting_value,
    bowling_value,
    rate_players,
    recency_weight,
    shrunk_per_100,
)

TODAY = date(2026, 10, 1)


def faced(pid, runs, out=False, day=TODAY, phase="middle", name=None):
    return FacedBall("m", day, phase, pid, name or pid, runs, out)


def bowled(pid, conceded, wicket=False, day=TODAY, phase="middle", name=None):
    return BowledBall("m", day, phase, pid, name or pid, conceded, wicket)


# --- recency_weight -------------------------------------------------------


def test_a_ball_on_the_rating_date_counts_fully():
    assert recency_weight(TODAY, TODAY, 365) == 1.0


def test_weight_halves_every_half_life():
    assert recency_weight(date(2025, 10, 1), TODAY, 365) == pytest.approx(0.5)
    assert recency_weight(date(2024, 10, 1), TODAY, 365) == pytest.approx(0.25, rel=1e-2)


def test_a_match_after_the_rating_date_is_rejected():
    with pytest.raises(ValueError):
        recency_weight(date(2026, 10, 2), TODAY, 365)


# --- batting_value and bowling_value ---------------------------------------

AVERAGE_BAT = PhaseAverage(runs=0.8, wickets=0.025)
AVERAGE_BOWL = PhaseAverage(runs=0.84, wickets=0.024)


def test_a_boundary_is_worth_its_runs_above_average_plus_survival():
    assert batting_value(faced("p", 4), AVERAGE_BAT, 25) == pytest.approx(3.2 + 25 * 0.025)


def test_getting_out_costs_the_value_of_a_wicket():
    value = batting_value(faced("p", 0, out=True), AVERAGE_BAT, 25)

    assert value == pytest.approx(-0.8 - 25 * (1 - 0.025))


def test_a_wicket_maiden_ball_is_worth_a_lot_to_the_bowler():
    value = bowling_value(bowled("b", 0, wicket=True), AVERAGE_BOWL, 25)

    assert value == pytest.approx(0.84 + 25 * (1 - 0.024))


def test_conceding_a_six_costs_the_bowler():
    value = bowling_value(bowled("b", 6), AVERAGE_BOWL, 25)

    assert value == pytest.approx(0.84 - 6 - 25 * 0.024)


# --- shrunk_per_100 --------------------------------------------------------


def test_shrinkage_adds_prior_balls_of_average_play():
    assert shrunk_per_100(30, 300, 300) == pytest.approx(5.0)


def test_without_a_prior_it_is_the_plain_rate():
    assert shrunk_per_100(30, 300, 0) == pytest.approx(10.0)


def test_no_balls_and_no_prior_gives_zero():
    assert shrunk_per_100(0, 0, 0) == 0.0


# --- rate_players ----------------------------------------------------------

NO_PRIOR = RatingConfig(wicket_value=25, half_life_days=365, prior_balls=0)


def test_batting_ratings_are_runs_above_average_per_100_balls():
    balls = [faced("hitter", 4), faced("blocker", 0)]  # average: 2 runs a ball, no wickets

    ratings = rate_players(balls, [], NO_PRIOR, TODAY)

    assert ratings["hitter"].batting == pytest.approx(200.0)
    assert ratings["blocker"].batting == pytest.approx(-200.0)


def test_bowling_ratings_reward_wickets_and_economy():
    balls = [bowled("strike", 0, wicket=True), bowled("leaky", 6)]

    ratings = rate_players([], balls, NO_PRIOR, TODAY)

    assert ratings["strike"].bowling > 0 > ratings["leaky"].bowling


def test_a_batter_who_never_bowled_has_a_zero_bowling_rating():
    ratings = rate_players([faced("p", 4), faced("q", 0)], [bowled("b", 1)], NO_PRIOR, TODAY)

    assert ratings["p"].bowling == 0.0
    assert (ratings["p"].balls_faced, ratings["p"].balls_bowled) == (1, 0)
    assert ratings["b"].batting == 0.0


def test_recent_form_counts_more_than_old_form():
    old_day = date(2024, 10, 1)
    balls = [
        faced("recent", 6),
        faced("old", 6, day=old_day),
        faced("filler", 0),
        faced("filler", 0, day=old_day),
    ]

    ratings = rate_players(balls, [], RatingConfig(prior_balls=10), TODAY)

    assert ratings["recent"].batting > ratings["old"].batting > 0


def test_shrinkage_pulls_small_samples_towards_zero():
    balls = [faced("one-ball", 6)] + [faced("regular", 6) for _ in range(500)]
    balls += [faced("filler", 0) for _ in range(501)]

    ratings = rate_players(balls, [], RatingConfig(prior_balls=300), TODAY)

    assert 0 < ratings["one-ball"].batting < ratings["regular"].batting


def test_players_are_matched_by_id_and_keep_their_latest_name_and_date():
    balls = [
        faced("p1", 1, day=date(2025, 1, 1), name="J Smith"),
        faced("p1", 1, day=date(2026, 5, 1), name="John Smith"),
    ]
    bowling = [bowled("p1", 0, day=date(2026, 6, 1), name="John Smith")]

    ratings = rate_players(balls, bowling, NO_PRIOR, TODAY)

    assert list(ratings) == ["p1"]
    rating = ratings["p1"]
    assert rating.name == "John Smith"
    assert rating.last_played == date(2026, 6, 1)
    assert (rating.balls_faced, rating.balls_bowled) == (2, 1)


def test_batting_is_judged_against_what_everyone_did_against_the_same_attack():
    # Everyone scores 3 a ball against the weak attack and 1 against the strong one.
    balls = [
        FacedBall("m", TODAY, "middle", "flat-track", "F", 2, False, opponent="Weak"),
        FacedBall("m", TODAY, "middle", "x", "X", 4, False, opponent="Weak"),
        FacedBall("m", TODAY, "middle", "tough", "T", 2, False, opponent="Strong"),
        FacedBall("m", TODAY, "middle", "y", "Y", 0, False, opponent="Strong"),
    ]

    ratings = rate_players(balls, [], NO_PRIOR, TODAY)

    assert ratings["flat-track"].batting < 0 < ratings["tough"].batting


def test_opponent_adjustment_can_be_switched_off():
    balls = [
        FacedBall("m", TODAY, "middle", "flat-track", "F", 2, False, opponent="Weak"),
        FacedBall("m", TODAY, "middle", "x", "X", 4, False, opponent="Weak"),
        FacedBall("m", TODAY, "middle", "tough", "T", 2, False, opponent="Strong"),
        FacedBall("m", TODAY, "middle", "y", "Y", 0, False, opponent="Strong"),
    ]
    plain = RatingConfig(prior_balls=0, opponent_adjusted=False)

    ratings = rate_players(balls, [], plain, TODAY)

    assert ratings["flat-track"].batting == pytest.approx(ratings["tough"].batting)
