from datetime import date

import pytest

from cwc27.ratings.elo import EloConfig, win_probability
from cwc27.ratings.model import EloModel
from tests.test_backtest import make_match

CONFIG = EloConfig()


def test_new_model_predicts_from_initial_ratings():
    model = EloModel(CONFIG)

    assert model.predict("India", "Namibia", None) == pytest.approx(
        win_probability({}, "India", "Namibia", CONFIG)
    )


def test_learning_a_win_raises_the_winners_chances():
    model = EloModel(CONFIG).learn(
        make_match("India", "Australia", "India", date(2024, 1, 1)), None
    )

    assert model.predict("India", "Australia", None) > 0.5


def test_learn_leaves_the_original_model_unchanged():
    original = EloModel(CONFIG)

    original.learn(make_match("India", "Australia", "India", date(2024, 1, 1)), None)

    assert original.predict("India", "Australia", None) == pytest.approx(0.5)


def test_predict_passes_home_side_through():
    model = EloModel(CONFIG)

    assert model.predict("India", "Australia", "India") > 0.5
