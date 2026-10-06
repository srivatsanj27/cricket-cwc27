"""Core domain types shared across ingest, ratings and prediction."""

from dataclasses import dataclass
from datetime import date
from enum import StrEnum


class ResultType(StrEnum):
    NORMAL = "normal"
    DLS = "dls"
    TIE = "tie"
    NO_RESULT = "no_result"


@dataclass(frozen=True, slots=True)
class Match:
    match_id: str
    date: date
    team_a: str
    team_b: str
    venue: str | None
    city: str | None
    toss_winner: str | None
    toss_decision: str | None
    winner: str | None
    result_type: ResultType
    margin_runs: int | None
    margin_wickets: int | None
    event: str | None
    source: str


@dataclass(frozen=True, slots=True)
class Appearance:
    """One player in one team's playing XI for one match."""

    match_id: str
    team: str
    player_name: str
    player_id: str
