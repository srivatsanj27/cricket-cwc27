from datetime import date, timedelta

import pytest

from cwc27.evaluation.report import Segment
from cwc27.evaluation.tuning import format_results, grid_search
from tests.test_backtest import make_match

TUNE = Segment("tune", lambda m: m.date.year == 2022)
CONFIRM = Segment("confirm", lambda m: m.date.year == 2024)


def _alternating(year: int, n: int):
    """A and B take turns winning: pure noise, so the best Elo barely reacts (small K)."""
    start = date(year, 1, 1)
    return [
        make_match("A", "B", "A" if i % 2 == 0 else "B", start + timedelta(days=i))
        for i in range(n)
    ]


def _search(matches, k_values=(30.0,), home_values=(60.0,)):
    return grid_search(
        matches,
        home_of=lambda m: None,
        k_values=list(k_values),
        home_values=list(home_values),
        tune=TUNE,
        confirm=CONFIRM,
    )


def test_returns_one_result_per_setting_sorted_by_tuning_brier():
    results = _search(
        _alternating(2022, 20) + _alternating(2024, 10),
        k_values=[5.0, 40.0],
        home_values=[0.0, 60.0],
    )

    assert len(results) == 4
    briers = [r.tune.brier for r in results]
    assert briers == sorted(briers)


def test_noisy_results_favour_a_small_k():
    (best, *_) = _search(_alternating(2022, 30), k_values=[5.0, 20.0, 60.0], home_values=[0.0])

    assert best.config.k == 5.0


def test_tune_and_confirm_are_scored_separately():
    (result,) = _search(_alternating(2022, 20) + _alternating(2024, 10))

    assert result.tune.n == 20
    assert result.confirm is not None and result.confirm.n == 10


def test_confirm_is_none_when_its_segment_is_empty():
    (result,) = _search(_alternating(2022, 10))

    assert result.confirm is None


def test_empty_tuning_segment_raises():
    with pytest.raises(ValueError, match="tune"):
        _search(_alternating(2024, 10))


@pytest.mark.parametrize(("k_values", "home_values"), [([], [60.0]), ([30.0], [])])
def test_empty_grid_raises(k_values, home_values):
    with pytest.raises(ValueError, match="grid"):
        _search(_alternating(2022, 10), k_values=k_values, home_values=home_values)


def test_format_results_names_the_best_setting_and_compares_with_defaults():
    results = _search(
        _alternating(2022, 20) + _alternating(2024, 10), k_values=[5.0, 40.0], home_values=[0.0]
    )

    text = format_results(results, top=1, baseline=results[-1])

    assert "Best: k=5, home advantage=0" in text
    assert "k=40, home advantage=0 (current defaults)" in text
    assert text.count("  k=") == 1  # only the top row is listed in the table
