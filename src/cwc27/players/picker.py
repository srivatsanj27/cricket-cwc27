"""Pick a squad of 15: the best-scoring players, subject to balance rules.

A player's score mixes how often selectors have picked them lately (their share of the
team's recent XIs) with how good they are (their rating for their role). Balance rules
(keepers, spinners, pacers, bowling options) are met first, by score, then the rest of
the squad is filled by score. Certain picks (stars who play whenever fit) go in before all
of that, and count towards the balance rules.
"""

from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from cwc27.players.roles import Role
from cwc27.store import MatchStore

BOWLING_ROLES = (Role.BOWLER, Role.ALL_ROUNDER)


@dataclass(frozen=True, slots=True)
class Candidate:
    player_id: str
    name: str
    role: Role
    style: str | None  # "pace", "spin" or None
    batting: float  # runs above average per 100 balls
    bowling: float
    selection_share: float  # share of the team's recent ODIs this player was in the XI for


@dataclass(frozen=True, slots=True)
class SquadRules:
    size: int = 15
    keepers: int = 2
    spinners: int = 2
    pacers: int = 4
    bowling_options: int = 7  # bowlers plus all-rounders
    selection_weight: float = 1.0
    skill_weight: float = (
        0.2  # tuned on the 2023 WC squads (11.67/15), confirmed on 2025 CT (11.43/15)
    )
    skill_scale: float = 30.0  # rating points that count as one unit of skill


def skill(c: Candidate, rules: SquadRules) -> float:
    if c.role is Role.BOWLER:
        value = c.bowling
    elif c.role is Role.ALL_ROUNDER:
        value = c.batting + c.bowling
    else:
        value = c.batting
    return value / rules.skill_scale


def squad_score(c: Candidate, rules: SquadRules) -> float:
    return rules.selection_weight * c.selection_share + rules.skill_weight * skill(c, rules)


def pick_squad(
    candidates: Iterable[Candidate], rules: SquadRules, certain: Collection[str] = frozenset()
) -> tuple[Candidate, ...]:
    """The squad, best score first. Balance rules are met as far as the pool allows."""
    ranked = sorted(candidates, key=lambda c: -squad_score(c, rules))
    requirements: Sequence[tuple[Callable[[Candidate], bool], int]] = (
        (lambda c: c.role is Role.KEEPER, rules.keepers),
        (lambda c: c.role in BOWLING_ROLES and c.style == "spin", rules.spinners),
        (lambda c: c.role in BOWLING_ROLES and c.style == "pace", rules.pacers),
        (lambda c: c.role in BOWLING_ROLES, rules.bowling_options),
        (lambda c: True, rules.size),
    )
    chosen = [c for c in ranked if c.player_id in certain][: rules.size]
    for wanted, count in requirements:
        have = sum(1 for c in chosen if wanted(c))
        for c in ranked:
            if have >= count or len(chosen) >= rules.size:
                break
            if wanted(c) and c not in chosen:
                chosen.append(c)
                have += 1
    return tuple(sorted(chosen, key=lambda c: -squad_score(c, rules)))


_SHARES_SQL = """
WITH window_xi AS (
    SELECT a.team, a.player_id, a.match_id
    FROM appearances a JOIN matches m USING (match_id)
    WHERE m.date >= ? AND m.date < ?),
team_matches AS (SELECT team, count(DISTINCT match_id) AS n FROM window_xi GROUP BY team)
SELECT w.team, w.player_id, count(*) * 1.0 / t.n
FROM window_xi w JOIN team_matches t USING (team)
GROUP BY w.team, w.player_id, t.n
"""


def selection_shares(
    store: MatchStore, since: date, until: date
) -> Mapping[tuple[str, str], float]:
    """(team, player_id) -> share of the team's ODIs in [since, until) the player played."""
    return {(team, pid): share for team, pid, share in store.fetch(_SHARES_SQL, [since, until])}
