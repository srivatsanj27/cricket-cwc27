"""Elo ratings wrapped as a backtestable model (see cwc27.evaluation.backtest.Model)."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from cwc27.models import Match
from cwc27.ratings.elo import EloConfig, update, win_probability


@dataclass(frozen=True, slots=True)
class EloModel:
    """Current Elo ratings plus the settings that produced them. Immutable."""

    config: EloConfig
    ratings: Mapping[str, float] = field(default_factory=lambda: MappingProxyType({}))

    def predict(self, team_a: str, team_b: str, home: str | None) -> float:
        """Probability that team_a beats team_b, from the ratings so far."""
        return win_probability(self.ratings, team_a, team_b, self.config, home)

    def learn(self, match: Match, home: str | None) -> "EloModel":
        """A new model with ratings updated for `match`; this one is unchanged."""
        new_ratings = update(self.ratings, match, self.config, home)
        return EloModel(self.config, MappingProxyType(new_ratings))
