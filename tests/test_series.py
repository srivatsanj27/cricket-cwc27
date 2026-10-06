"""Specification for cwc27.simulate.series. Written before the implementation (TDD)."""

import pytest

from cwc27.simulate.series import simulate_series

MANY = 100_000  # enough simulations that results land within ~0.01 of the exact answer
TOLERANCE = 0.01


def test_scoreline_probabilities_sum_to_one():
    forecast = simulate_series([0.6, 0.55, 0.7], n_sims=5_000, seed=1)

    assert sum(forecast.scorelines.values()) == pytest.approx(1.0)


def test_every_scoreline_accounts_for_every_match():
    forecast = simulate_series([0.6, 0.55, 0.7], n_sims=5_000, seed=1)

    assert forecast.n_matches == 3
    assert all(a + b == 3 for a, b in forecast.scorelines)


def test_a_certain_winner_wins_every_match():
    forecast = simulate_series([1.0, 1.0, 1.0], n_sims=1_000, seed=1)

    assert forecast.scorelines == {(3, 0): 1.0}
    assert forecast.p_a_wins_series == 1.0
    assert forecast.p_b_wins_series == 0.0


def test_even_three_match_series_matches_the_binomial_odds():
    forecast = simulate_series([0.5, 0.5, 0.5], n_sims=MANY, seed=7)

    assert forecast.scorelines[(3, 0)] == pytest.approx(1 / 8, abs=TOLERANCE)
    assert forecast.scorelines[(2, 1)] == pytest.approx(3 / 8, abs=TOLERANCE)
    assert forecast.scorelines[(1, 2)] == pytest.approx(3 / 8, abs=TOLERANCE)
    assert forecast.scorelines[(0, 3)] == pytest.approx(1 / 8, abs=TOLERANCE)


def test_series_win_probability_for_a_60_percent_favourite():
    forecast = simulate_series([0.6, 0.6, 0.6], n_sims=MANY, seed=7)

    exact = 0.6**3 + 3 * 0.6**2 * 0.4  # win all three, or exactly two
    assert forecast.p_a_wins_series == pytest.approx(exact, abs=TOLERANCE)
    assert forecast.p_drawn_series == 0.0


def test_two_match_series_can_be_drawn():
    forecast = simulate_series([0.5, 0.5], n_sims=MANY, seed=7)

    assert forecast.p_drawn_series == pytest.approx(0.5, abs=TOLERANCE)
    total = forecast.p_a_wins_series + forecast.p_b_wins_series + forecast.p_drawn_series
    assert total == pytest.approx(1.0)


def test_each_match_uses_its_own_probability():
    # A always wins at home (match 1) and always loses away (match 2).
    forecast = simulate_series([1.0, 0.0], n_sims=1_000, seed=1)

    assert forecast.scorelines == {(1, 1): 1.0}
    assert forecast.p_drawn_series == 1.0


def test_same_seed_gives_the_same_forecast():
    first = simulate_series([0.6, 0.4, 0.55], n_sims=2_000, seed=42)
    second = simulate_series([0.6, 0.4, 0.55], n_sims=2_000, seed=42)

    assert first == second


@pytest.mark.parametrize(
    ("probabilities", "n_sims"),
    [([], 1_000), ([0.5, 1.2], 1_000), ([0.5, -0.1], 1_000), ([0.5], 0)],
)
def test_invalid_input_raises(probabilities, n_sims):
    with pytest.raises(ValueError):
        simulate_series(probabilities, n_sims=n_sims, seed=1)
