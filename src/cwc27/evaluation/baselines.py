"""Simple reference models a real model has to beat."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from cwc27.models import Match
from cwc27.ratings.elo import actual_score


@dataclass(frozen=True, slots=True)
class CoinFlip:
    """Every match is 50/50."""

    def predict(self, team_a: str, team_b: str, home: str | None) -> float:
        return 0.5

    def learn(self, match: Match, home: str | None) -> "CoinFlip":
        return self


@dataclass(frozen=True, slots=True)
class WinRate:
    """Favour the team with the better win rate so far (Laplace-smoothed: (wins+1)/(played+2))."""

    wins: Mapping[str, float] = field(default_factory=lambda: MappingProxyType({}))
    played: Mapping[str, int] = field(default_factory=lambda: MappingProxyType({}))

    def predict(self, team_a: str, team_b: str, home: str | None) -> float:
        # Deliberately ignores `home`: the baseline is results-only.
        rate_a, rate_b = self._rate(team_a), self._rate(team_b)
        return rate_a / (rate_a + rate_b)

    def learn(self, match: Match, home: str | None) -> "WinRate":
        score_a = actual_score(match, match.team_a)
        if score_a is None:
            return self
        wins = dict(self.wins)
        played = dict(self.played)
        for team, points in ((match.team_a, score_a), (match.team_b, 1.0 - score_a)):
            wins[team] = wins.get(team, 0.0) + points
            played[team] = played.get(team, 0) + 1
        return WinRate(wins=MappingProxyType(wins), played=MappingProxyType(played))

    def _rate(self, team: str) -> float:
        return (self.wins.get(team, 0.0) + 1) / (self.played.get(team, 0) + 2)
