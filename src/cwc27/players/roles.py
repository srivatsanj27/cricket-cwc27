"""Player roles (batter, keeper, all-rounder, bowler) and bowling style, from the data.

Cricsheet doesn't label roles, so they're inferred: a keeper is whoever takes stumpings,
a bowler or all-rounder bowls regularly, and spinners are told from pacers by when they
bowl and whether keepers stump batters off them. config/player_overrides.csv corrects
any player the rules get wrong.
"""

import csv
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType

from cwc27.store import MatchStore

OVERRIDES_CSV = Path(__file__).resolve().parents[3] / "config" / "player_overrides.csv"
OVERRIDE_COLUMNS = ("player_id", "name", "role", "bowling_style")
STYLES = ("pace", "spin")

REGULAR_BOWLER_BALLS_PER_MATCH = 18  # three overs a match on average
KEEPER_MAX_BALLS_PER_MATCH = 6
TOP_ORDER = 7.5  # average batting position for an all-rounder
MIN_BALLS_FOR_STYLE = 120
# Keepers stand up to spinners, so stumpings off a bowler mark a spinner. Otherwise the
# powerplay share separates them: spinners bowl 0-7% of their balls there, pacers 30%+.
# Death overs don't help: in ODIs spinners bowl at the death too.
SPIN_STUMPING_WICKETS = 1
PACE_POWERPLAY_SHARE = 0.25
SPIN_POWERPLAY_MAX = 0.10


class Role(StrEnum):
    BATTER = "batter"
    KEEPER = "keeper"
    ALL_ROUNDER = "all-rounder"
    BOWLER = "bowler"


@dataclass(frozen=True, slots=True)
class PlayerProfile:
    """What a player has done since a given date, for working out their role."""

    player_id: str
    name: str  # latest name
    team: str  # latest team
    appearances: int
    last_played: date
    balls_bowled: int  # legal deliveries
    powerplay_share: float  # share of their deliveries bowled in overs 1-10
    death_share: float  # share bowled in overs 41-50
    stumping_wickets: int  # batters stumped off their bowling
    stumpings: int  # stumpings they took as keeper
    batting_position: float | None  # average order they came in to bat; None if never batted


@dataclass(frozen=True, slots=True)
class PlayerRole:
    player_id: str
    name: str
    team: str
    role: Role
    bowling_style: str | None


@dataclass(frozen=True, slots=True)
class Override:
    role: Role | None
    bowling_style: str | None


def classify_role(p: PlayerProfile) -> Role:
    per_match = p.balls_bowled / p.appearances if p.appearances else 0.0
    if p.stumpings and per_match < KEEPER_MAX_BALLS_PER_MATCH:
        return Role.KEEPER
    if per_match >= REGULAR_BOWLER_BALLS_PER_MATCH:
        top_order = p.batting_position is not None and p.batting_position <= TOP_ORDER
        return Role.ALL_ROUNDER if top_order else Role.BOWLER
    return Role.BATTER


def guess_bowling_style(p: PlayerProfile) -> str | None:
    """'pace', 'spin', or None when there are too few balls or the signs disagree."""
    if p.balls_bowled < MIN_BALLS_FOR_STYLE:
        return None
    if p.stumping_wickets >= SPIN_STUMPING_WICKETS or p.powerplay_share < SPIN_POWERPLAY_MAX:
        return "spin"
    if p.powerplay_share >= PACE_POWERPLAY_SHARE:
        return "pace"
    return None


def assign_roles(
    recent: Sequence[PlayerProfile],
    history: Sequence[PlayerProfile],
    overrides: Mapping[str, Override],
) -> Mapping[str, PlayerRole]:
    """Role from recent play; keeping and bowling style from the full history.

    A player who has kept wicket before and barely bowls now is a keeper, even if someone
    else has had the gloves lately. Overrides are applied last.
    """
    past = {p.player_id: p for p in history}
    roles: dict[str, PlayerRole] = {}
    for p in recent:
        long_view = past.get(p.player_id, p)
        role = classify_role(p)
        if role is Role.BATTER and long_view.stumpings:
            role = Role.KEEPER
        style = guess_bowling_style(long_view) if role in (Role.BOWLER, Role.ALL_ROUNDER) else None
        role, style = apply_overrides(p.player_id, role, style, overrides)
        roles[p.player_id] = PlayerRole(p.player_id, p.name, p.team, role, style)
    return MappingProxyType(roles)


def load_overrides(path: Path = OVERRIDES_CSV) -> Mapping[str, Override]:
    """Hand corrections keyed by player id; a missing file means none. Bad rows raise."""
    if not path.exists():
        return {}
    overrides: dict[str, Override] = {}
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if tuple(reader.fieldnames or ()) != OVERRIDE_COLUMNS:
            raise ValueError(f"{path.name}: header must be {','.join(OVERRIDE_COLUMNS)}")
        for row in reader:
            role, style = (row["role"] or "").strip(), (row["bowling_style"] or "").strip()
            if role and role not in {r.value for r in Role}:
                raise ValueError(f"{path.name}:{reader.line_num}: unknown role {role!r}")
            if style and style not in STYLES:
                raise ValueError(f"{path.name}:{reader.line_num}: unknown style {style!r}")
            overrides[row["player_id"].strip()] = Override(
                Role(role) if role else None, style or None
            )
    return MappingProxyType(overrides)


def apply_overrides(
    player_id: str, role: Role, style: str | None, overrides: Mapping[str, Override]
) -> tuple[Role, str | None]:
    override = overrides.get(player_id)
    if override is None:
        return role, style
    return override.role or role, override.bowling_style or style


_PROFILES_SQL = """
WITH recent AS (SELECT match_id, date FROM matches WHERE date >= ?),
apps AS (
    SELECT a.player_id, arg_max(a.player_name, r.date) AS name, arg_max(a.team, r.date) AS team,
           count(*) AS appearances, max(r.date) AS last_played
    FROM appearances a JOIN recent r USING (match_id) GROUP BY a.player_id),
bowl AS (
    SELECT d.bowler_id AS player_id,
           count(*) FILTER (WHERE d.wides = 0 AND d.noballs = 0) AS balls,
           count(*) FILTER (WHERE d.phase = 'powerplay') AS powerplay,
           count(*) FILTER (WHERE d.phase = 'death') AS death,
           count(*) AS deliveries,
           count(*) FILTER (WHERE d.wicket_kind = 'stumped') AS stumping_wickets
    FROM deliveries d JOIN recent r USING (match_id) GROUP BY 1),
keep AS (
    SELECT a.player_id, count(*) AS stumpings
    FROM deliveries d JOIN recent r USING (match_id)
    JOIN appearances a
      ON a.match_id = d.match_id AND a.team = d.bowling_team AND a.player_name = d.fielder
    WHERE d.wicket_kind = 'stumped' GROUP BY 1),
first_faced AS (
    SELECT d.match_id, d.innings, d.batter_id, min(d.over_no * 1000 + d.ball) AS seq
    FROM deliveries d JOIN recent r USING (match_id) GROUP BY 1, 2, 3),
positions AS (
    SELECT batter_id AS player_id, avg(position) AS batting_position
    FROM (SELECT batter_id,
                 row_number() OVER (PARTITION BY match_id, innings ORDER BY seq) AS position
          FROM first_faced)
    GROUP BY 1)
SELECT apps.player_id, apps.name, apps.team, apps.appearances, apps.last_played,
       coalesce(bowl.balls, 0),
       coalesce(bowl.powerplay / nullif(bowl.deliveries, 0), 0.0),
       coalesce(bowl.death / nullif(bowl.deliveries, 0), 0.0),
       coalesce(bowl.stumping_wickets, 0), coalesce(keep.stumpings, 0),
       positions.batting_position
FROM apps
LEFT JOIN bowl USING (player_id)
LEFT JOIN keep USING (player_id)
LEFT JOIN positions USING (player_id)
ORDER BY apps.team, apps.name
"""


def load_profiles(store: MatchStore, since: date) -> Sequence[PlayerProfile]:
    """One profile per player who appeared in a playing XI on or after `since`."""
    return tuple(PlayerProfile(*row) for row in store.fetch(_PROFILES_SQL, [since]))
