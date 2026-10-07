"""Ball-by-ball deliveries from a Cricsheet file's innings."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from cwc27.ingest.errors import ParseError
from cwc27.teams import normalise_team

# ODI phases by over (0-based): the first powerplay is overs 1-10, the death overs 41-50.
POWERPLAY_OVERS = 10
DEATH_FROM_OVER = 40


@dataclass(frozen=True, slots=True)
class Delivery:
    """One ball. `over` is 0-based as in Cricsheet; `ball` counts every delivery in the over."""

    match_id: str
    innings: int
    batting_team: str
    bowling_team: str
    over: int
    ball: int
    phase: str
    batter: str
    batter_id: str
    bowler: str
    bowler_id: str
    non_striker: str
    runs_batter: int
    runs_extras: int
    runs_total: int
    wides: int
    noballs: int
    byes: int
    legbyes: int
    wickets: int  # dismissals on this ball (rarely 2, e.g. a catch plus a retirement)
    wicket_kind: str | None  # the first dismissal's details, as listed by Cricsheet
    player_out: str | None
    player_out_id: str | None
    fielder: str | None  # every fielder involved, joined with " / "

    @property
    def is_legal(self) -> bool:
        """Counts as a ball faced and bowled (wides and no-balls are re-bowled)."""
        return self.wides == 0 and self.noballs == 0


def phase_of(over: int) -> str:
    if over < POWERPLAY_OVERS:
        return "powerplay"
    if over < DEATH_FROM_OVER:
        return "middle"
    return "death"


def parse_deliveries(
    innings: Sequence[Mapping[str, Any]],
    people: Mapping[str, str],
    teams: tuple[str, str],
    match_id: str,
) -> tuple[Delivery, ...]:
    """Every delivery of the regular innings, in order. Super overs are skipped."""
    deliveries: list[Delivery] = []
    regular = [inn for inn in innings if not inn.get("super_over")]
    for number, inn in enumerate(regular, start=1):
        batting = normalise_team(inn["team"])
        if batting not in teams:
            raise ParseError(f"innings {number} batting team {batting!r} did not play")
        bowling = teams[1] if batting == teams[0] else teams[0]
        for over in inn["overs"]:
            over_no = int(over["over"])
            for ball_no, raw in enumerate(over["deliveries"], start=1):
                deliveries.append(
                    _delivery(raw, people, match_id, number, (batting, bowling), over_no, ball_no)
                )
    return tuple(deliveries)


def _delivery(
    raw: Mapping[str, Any],
    people: Mapping[str, str],
    match_id: str,
    innings: int,
    sides: tuple[str, str],
    over: int,
    ball: int,
) -> Delivery:
    runs = raw["runs"]
    extras = raw.get("extras") or {}
    all_wickets = raw.get("wickets") or []
    wicket = all_wickets[0] if all_wickets else None
    fielders = [f["name"] for f in (wicket or {}).get("fielders") or [] if f.get("name")]
    player_out = wicket["player_out"] if wicket else None
    return Delivery(
        match_id=match_id,
        innings=innings,
        batting_team=sides[0],
        bowling_team=sides[1],
        over=over,
        ball=ball,
        phase=phase_of(over),
        batter=raw["batter"],
        batter_id=_registry_id(people, raw["batter"]),
        bowler=raw["bowler"],
        bowler_id=_registry_id(people, raw["bowler"]),
        non_striker=raw["non_striker"],
        runs_batter=int(runs["batter"]),
        runs_extras=int(runs["extras"]),
        runs_total=int(runs["total"]),
        wides=int(extras.get("wides", 0)),
        noballs=int(extras.get("noballs", 0)),
        byes=int(extras.get("byes", 0)),
        legbyes=int(extras.get("legbyes", 0)),
        wickets=len(all_wickets),
        wicket_kind=wicket["kind"] if wicket else None,
        player_out=player_out,
        player_out_id=_registry_id(people, player_out) if player_out else None,
        fielder=" / ".join(fielders) or None,
    )


def _registry_id(people: Mapping[str, str], name: str) -> str:
    if name not in people:
        raise ParseError(f"player {name!r} missing from registry")
    return people[name]
