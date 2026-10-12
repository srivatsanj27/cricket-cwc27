"""Real squads from Wikipedia squad pages, matched to Cricsheet player ids.

Two page layouts are handled: the 2023 World Cup page's player templates, and the plain
tables used for the 2025 Champions Trophy. Struck-through players withdrew (usually
injured); their replacements are listed as ordinary rows.
"""

import csv
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from cwc27.store import MatchStore
from cwc27.teams import normalise_team

_HEADING = re.compile(r"^(={2,})\s*(.*?)\s*\1\s*$")
_LINK = re.compile(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]")
_TEMPLATE = re.compile(r"\{\{[^{}]*\}\}")
_PLAYER_TEMPLATE = "{{National cricket ODI squad player"
_SPIN_WORDS = ("spin", "break", "orthodox", "googly", "chinaman")
_PACE_WORDS = ("fast", "medium")
_SUFFIXES = frozenset({"jr.", "jr", "sr.", "sr"})
SQUAD_COLUMNS = (
    "tournament", "team", "wiki_name", "player_id", "cricsheet_name",
    "keeper", "role", "bowling_style", "withdrawn",
)  # fmt: skip


@dataclass(frozen=True, slots=True)
class SquadEntry:
    team: str
    name: str
    keeper: bool
    role: str | None  # as Wikipedia states it, when the page has a role column
    bowling_style: str | None  # "pace", "spin" or None
    withdrawn: bool  # struck through: named, then replaced


@dataclass(frozen=True, slots=True)
class MatchedPlayer:
    entry: SquadEntry
    player_id: str
    cricsheet_name: str

    @property
    def wiki_name(self) -> str:
        return self.entry.name


def style_from_text(text: str) -> str | None:
    lowered = text.lower()
    if any(word in lowered for word in _SPIN_WORDS):
        return "spin"
    if any(word in lowered for word in _PACE_WORDS):
        return "pace"
    return None


def parse_squads(wikitext: str, known_teams: Iterable[str]) -> tuple[SquadEntry, ...]:
    """Every squad row that sits under a heading naming a known team."""
    teams = set(known_teams)
    entries: list[SquadEntry] = []
    team: str | None = None
    for line in _flatten_templates(wikitext).splitlines():
        heading = _HEADING.match(line.strip())
        if heading:
            name = _clean(heading.group(2))
            team = normalise_team(name) if name and normalise_team(name) in teams else None
            continue
        if team is None:
            continue
        entry = _template_row(line, team) or _table_row(line, team)
        if entry is not None:
            entries.append(entry)
    return tuple(entries)


def match_players(
    entries: Iterable[SquadEntry],
    candidates: Mapping[str, Sequence[tuple[str, str]]],
    aliases: Mapping[tuple[str, str], str] | None = None,
) -> tuple[tuple[MatchedPlayer, ...], tuple[SquadEntry, ...]]:
    """Match each Wikipedia name to one (player_id, Cricsheet name) of the same team.

    In order: an alias for (team, Wikipedia name); the exact name; surname plus first
    initial ("Rohit Sharma" -> "RG Sharma"); a surname no one else in the team has
    ("Charith Asalanka" -> "KIC Asalanka"). Anything ambiguous is left unmatched.
    """
    matched: list[MatchedPlayer] = []
    unmatched: list[SquadEntry] = []
    for entry in entries:
        name = (aliases or {}).get((entry.team, entry.name), entry.name)
        found = _find(name, candidates.get(entry.team, ()))
        if found is None:
            unmatched.append(entry)
        else:
            matched.append(MatchedPlayer(entry, *found))
    return tuple(matched), tuple(unmatched)


def squad_candidates(store: MatchStore, since: date) -> Mapping[str, list[tuple[str, str]]]:
    """Each team's players (id, latest name) from playing XIs on or after `since`."""
    rows = store.fetch(
        "SELECT a.team, a.player_id, arg_max(a.player_name, m.date) "
        "FROM appearances a JOIN matches m USING (match_id) "
        "WHERE m.date >= ? GROUP BY 1, 2 ORDER BY 1, 3",
        [since],
    )
    candidates: dict[str, list[tuple[str, str]]] = {}
    for team, player_id, name in rows:
        candidates.setdefault(team, []).append((player_id, name))
    return candidates


def write_squads(path: Path, tournament: str, matched: Iterable[MatchedPlayer]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(SQUAD_COLUMNS)
        for m in matched:
            e = m.entry
            writer.writerow(
                [tournament, e.team, e.name, m.player_id, m.cricsheet_name, e.keeper,
                 e.role or "", e.bowling_style or "", e.withdrawn]
            )  # fmt: skip


def _find(name: str, pool: Sequence[tuple[str, str]]) -> tuple[str, str] | None:
    exact = [c for c in pool if c[1].casefold() == name.casefold()]
    if len(exact) == 1:
        return exact[0]
    tokens = [t for t in name.split() if t.casefold() not in _SUFFIXES]
    if not tokens:
        return None
    if len(tokens) < len(name.split()):
        return _find(" ".join(tokens), pool)
    surname, initial = tokens[-1].casefold(), tokens[0][0].casefold()
    same_surname = [c for c in pool if c[1].split()[-1].casefold() == surname]
    same_initial = [c for c in same_surname if c[1][0].casefold() == initial]
    if len(same_initial) == 1:
        return same_initial[0]
    return same_surname[0] if len(same_surname) == 1 else None


def _template_row(line: str, team: str) -> SquadEntry | None:
    if _PLAYER_TEMPLATE not in line:
        return None
    fields = _template_fields(line[line.index(_PLAYER_TEMPLATE) + 2 : line.rindex("}}")])
    raw_player = fields.get("player", "")
    name = _clean(raw_player)
    if not name:
        return None
    markers = _clean(fields.get("other", "")).lower()
    return SquadEntry(
        team=team,
        name=name,
        keeper="wk" in markers,
        role=_clean(fields.get("role", "")) or None,
        bowling_style=style_from_text(_clean(fields.get("bowling style", ""))),
        withdrawn="<s>" in raw_player,
    )


def _table_row(line: str, team: str) -> SquadEntry | None:
    stripped = line.strip()
    if not stripped.startswith("|") or stripped.startswith(("|-", "|}")) or "||" not in stripped:
        return None
    cells = [c.strip() for c in stripped.lstrip("|").split("||")]
    if len(cells) < 6:
        return None
    raw_player = cells[1]
    shown = _LINK.sub(r"\1", raw_player)
    markers = " ".join(re.findall(r"\(([^)]*)\)", shown)).lower()
    name = _clean(raw_player)
    if not name:
        return None
    return SquadEntry(
        team=team,
        name=name,
        keeper="wk" in markers,
        role=None,
        bowling_style=style_from_text(_clean(cells[5])),
        withdrawn="<s>" in raw_player,
    )


def _clean(text: str) -> str:
    text = re.sub(r"</?s>", "", text)
    text = _LINK.sub(r"\1", text)
    while _TEMPLATE.search(text):
        text = _TEMPLATE.sub("", text)
    text = re.sub(r"\([^)]*\)", "", text)
    return text.replace("'''", "").strip()


def _template_fields(body: str) -> dict[str, str]:
    """Split a template body on top-level '|' and read key=value pairs."""
    parts, depth, current = [], 0, []
    i = 0
    while i < len(body):
        pair = body[i : i + 2]
        if pair in ("[[", "{{"):
            depth += 1
            current.append(pair)
            i += 2
            continue
        if pair in ("]]", "}}"):
            depth -= 1
            current.append(pair)
            i += 2
            continue
        if body[i] == "|" and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(body[i])
        i += 1
    parts.append("".join(current))
    fields = {}
    for part in parts:
        key, sep, value = part.partition("=")
        if sep:
            fields[key.strip()] = value.strip()
    return fields


def _flatten_templates(text: str) -> str:
    """Put each player template on one line (some span several)."""
    out, i = [], 0
    while True:
        start = text.find(_PLAYER_TEMPLATE, i)
        if start == -1:
            out.append(text[i:])
            return "".join(out)
        out.append(text[i:start])
        depth, j = 0, start
        while j < len(text):
            if text.startswith("{{", j):
                depth += 1
                j += 2
            elif text.startswith("}}", j):
                depth -= 1
                j += 2
                if depth == 0:
                    break
            else:
                j += 1
        out.append(text[start:j].replace("\n", " "))
        i = j


def load_known_styles(paths: Iterable[Path]) -> Mapping[str, str]:
    """Bowling style by player id from saved squad files; later files win."""
    styles: dict[str, str] = {}
    for path in paths:
        with path.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row["bowling_style"]:
                    styles[row["player_id"]] = row["bowling_style"]
    return styles
