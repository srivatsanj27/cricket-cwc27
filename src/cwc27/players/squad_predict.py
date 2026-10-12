"""Predict squads as of a date, and score predictions against squads that were announced."""

import csv
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from cwc27 import config
from cwc27.players.balls import load_bowled, load_faced
from cwc27.players.picker import Candidate, SquadRules, pick_squad, selection_shares
from cwc27.players.ratings import PlayerRating, RatingConfig, rate_players
from cwc27.players.roles import Override, PlayerRole, assign_roles, load_profiles
from cwc27.store import MatchStore

ROLE_WINDOW_DAYS = 730  # roles come from the last two years of play
SELECTION_WINDOW_DAYS = 365  # selection share comes from the last year


@dataclass(frozen=True, slots=True)
class SquadInputs:
    roles: Mapping[str, PlayerRole]
    ratings: Mapping[str, PlayerRating]
    shares: Mapping[tuple[str, str], float]


@dataclass(frozen=True, slots=True)
class AnnouncedPlayer:
    team: str
    name: str
    player_id: str | None  # None when the player couldn't be matched (e.g. Afghanistan)
    keeper: bool
    role: str
    bowling_style: str
    withdrawn: bool


@dataclass(frozen=True, slots=True)
class BacktestCase:
    name: str
    as_of: date  # squads were announced around this date
    squads: str  # file in data/squads
    style_sources: tuple[str, ...]  # earlier squad files whose bowling styles may be used


BACKTEST_CASES = (
    BacktestCase("2023 World Cup", date(2023, 9, 1), "2023_world_cup.csv", ()),
    BacktestCase(
        "2025 Champions Trophy",
        date(2025, 1, 12),
        "2025_champions_trophy.csv",
        ("2023_world_cup.csv",),
    ),
)


def squad_inputs(
    store: MatchStore,
    as_of: date,
    overrides: Mapping[str, Override],
    known_styles: Mapping[str, str],
) -> SquadInputs:
    """Roles, ratings and selection shares from matches before `as_of` only."""
    roles = assign_roles(
        load_profiles(store, as_of - timedelta(days=ROLE_WINDOW_DAYS), as_of),
        load_profiles(store, config.RATINGS_START, as_of),
        overrides,
        known_styles,
    )
    ratings = rate_players(
        load_faced(store, config.RATINGS_START, as_of),
        load_bowled(store, config.RATINGS_START, as_of),
        RatingConfig(),
        as_of - timedelta(days=1),
    )
    shares = selection_shares(store, as_of - timedelta(days=SELECTION_WINDOW_DAYS), as_of)
    return SquadInputs(roles, ratings, shares)


def team_candidates(team: str, inputs: SquadInputs) -> tuple[Candidate, ...]:
    """Everyone whose latest team is `team`, with their ratings and selection share."""
    out = []
    for pid, role in inputs.roles.items():
        if role.team != team:
            continue
        rating = inputs.ratings.get(pid)
        out.append(
            Candidate(
                player_id=pid,
                name=role.name,
                role=role.role,
                style=role.bowling_style,
                batting=rating.batting if rating else 0.0,
                bowling=rating.bowling if rating else 0.0,
                selection_share=inputs.shares.get((team, pid), 0.0),
            )
        )
    return tuple(out)


def predict_squad(team: str, inputs: SquadInputs, rules: SquadRules) -> tuple[Candidate, ...]:
    return pick_squad(team_candidates(team, inputs), rules)


def load_announced(path: Path) -> tuple[AnnouncedPlayer, ...]:
    with path.open(newline="", encoding="utf-8") as f:
        return tuple(
            AnnouncedPlayer(
                team=r["team"],
                name=r["wiki_name"],
                player_id=r["player_id"] or None,
                keeper=r["keeper"] == "True",
                role=r["role"],
                bowling_style=r["bowling_style"],
                withdrawn=r["withdrawn"] == "True",
            )
            for r in csv.DictReader(f)
        )


def announced_ids(players: Iterable[AnnouncedPlayer]) -> Mapping[str, set[str]]:
    """Team -> ids of everyone named, withdrawn included (they were picked too)."""
    teams: dict[str, set[str]] = {}
    for p in players:
        if p.player_id:
            teams.setdefault(p.team, set()).add(p.player_id)
    return teams


def fallback_squad(team: str, players: Iterable[AnnouncedPlayer]) -> tuple[AnnouncedPlayer, ...]:
    """A team's last announced squad, without players who withdrew."""
    return tuple(p for p in players if p.team == team and not p.withdrawn)


def squad_hits(predicted: Sequence[Candidate], announced: set[str]) -> int:
    return len({c.player_id for c in predicted} & announced)
