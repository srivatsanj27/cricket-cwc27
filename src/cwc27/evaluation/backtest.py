"""Walk-forward backtesting: predict each match using only the matches before it."""

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol, Self

from cwc27.evaluation.metrics import Summary, summarise
from cwc27.models import Match
from cwc27.ratings.elo import actual_score


class Model(Protocol):
    """Anything that can predict a match and learn from a result, immutably."""

    def predict(self, team_a: str, team_b: str, home: str | None) -> float:
        """Probability that team_a beats team_b."""
        ...

    def learn(self, match: Match, home: str | None) -> Self:
        """A new model that has also seen `match`; the original is unchanged."""
        ...


@dataclass(frozen=True, slots=True)
class Prediction:
    """A model's pre-match probability for team A, next to what actually happened."""

    match: Match
    home: str | None
    p_team_a: float
    actual_a: float


def walk_forward(
    matches: Iterable[Match],
    model: Model,
    home_of: Callable[[Match], str | None],
) -> tuple[Prediction, ...]:
    """Predict every decided match in date order, learning from each only after predicting it.

    No-result matches are passed to `learn` but not scored.
    """
    predictions = []
    for match in sorted(matches, key=lambda m: (m.date, m.match_id)):
        home = home_of(match)
        actual = actual_score(match, match.team_a)
        if actual is not None:
            p = model.predict(match.team_a, match.team_b, home)
            predictions.append(Prediction(match=match, home=home, p_team_a=p, actual_a=actual))
        model = model.learn(match, home)
    return tuple(predictions)


def score(predictions: Sequence[Prediction]) -> Summary:
    """Brier, log loss and accuracy for a set of predictions (ValueError if empty)."""
    return summarise([p.p_team_a for p in predictions], [p.actual_a for p in predictions])
