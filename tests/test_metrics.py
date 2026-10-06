import math

import pytest

from cwc27.evaluation.metrics import (
    accuracy,
    brier_score,
    calibration_table,
    log_loss,
    summarise,
)


def test_brier_is_zero_for_perfect_predictions():
    assert brier_score([1.0, 0.0], [1.0, 0.0]) == 0.0


def test_brier_of_coin_flip_is_a_quarter():
    assert brier_score([0.5, 0.5], [1.0, 0.0]) == pytest.approx(0.25)


def test_brier_worked_example():
    assert brier_score([0.8, 0.3], [1.0, 0.0]) == pytest.approx((0.2**2 + 0.3**2) / 2)


def test_log_loss_of_coin_flip_is_ln2():
    assert log_loss([0.5, 0.5], [1.0, 0.0]) == pytest.approx(math.log(2))


def test_log_loss_stays_finite_for_confident_mistakes():
    assert math.isfinite(log_loss([1.0], [0.0]))


def test_log_loss_handles_ties():
    assert log_loss([0.5], [0.5]) == pytest.approx(math.log(2))


def test_accuracy_counts_favourite_wins_and_ignores_ties():
    probabilities = [0.8, 0.3, 0.6, 0.7]
    outcomes = [1.0, 0.0, 0.0, 0.5]

    assert accuracy(probabilities, outcomes) == pytest.approx(2 / 3)


def test_accuracy_gives_half_credit_for_even_predictions():
    assert accuracy([0.5, 0.5], [1.0, 0.0]) == pytest.approx(0.5)


def test_accuracy_is_nan_when_every_match_is_a_tie():
    assert math.isnan(accuracy([0.6], [0.5]))


@pytest.mark.parametrize(
    ("probabilities", "outcomes"),
    [([], []), ([0.5], [1.0, 0.0]), ([1.2], [1.0]), ([0.5], [0.7])],
)
def test_invalid_inputs_raise(probabilities, outcomes):
    with pytest.raises(ValueError):
        brier_score(probabilities, outcomes)


def test_calibration_table_uses_the_favourites_perspective():
    # Favourite probabilities: 0.55, 0.55 (team B favoured at 0.45), 0.85
    probabilities = [0.55, 0.45, 0.85]
    outcomes = [1.0, 1.0, 1.0]

    table = calibration_table(probabilities, outcomes)

    first = table[0]
    assert (first.lower, first.upper, first.count) == (0.5, 0.6, 2)
    assert first.mean_predicted == pytest.approx(0.55)
    assert first.observed_rate == pytest.approx(0.5)  # favourite won once out of two
    assert [b.count for b in table] == [2, 0, 0, 1, 0]


def test_summarise_bundles_all_scores():
    summary = summarise([0.8, 0.3], [1.0, 0.0])

    assert summary.n == 2
    assert summary.brier == pytest.approx(brier_score([0.8, 0.3], [1.0, 0.0]))
    assert summary.log_loss == pytest.approx(log_loss([0.8, 0.3], [1.0, 0.0]))
    assert summary.accuracy == pytest.approx(1.0)
