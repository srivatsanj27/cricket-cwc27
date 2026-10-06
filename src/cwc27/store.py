"""DuckDB-backed storage for matches and playing XIs."""

from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import date
from pathlib import Path

import duckdb

from cwc27.ingest.cricsheet import ParsedMatch
from cwc27.models import Match, ResultType

_CREATE_MATCHES = """
CREATE TABLE IF NOT EXISTS matches (
    match_id       VARCHAR PRIMARY KEY,
    date           DATE NOT NULL,
    team_a         VARCHAR NOT NULL,
    team_b         VARCHAR NOT NULL,
    venue          VARCHAR,
    city           VARCHAR,
    toss_winner    VARCHAR,
    toss_decision  VARCHAR,
    winner         VARCHAR,
    result_type    VARCHAR NOT NULL,
    margin_runs    INTEGER,
    margin_wickets INTEGER,
    event          VARCHAR,
    source         VARCHAR NOT NULL
)
"""
_CREATE_APPEARANCES = """
CREATE TABLE IF NOT EXISTS appearances (
    match_id    VARCHAR NOT NULL,
    team        VARCHAR NOT NULL,
    player_name VARCHAR NOT NULL,
    player_id   VARCHAR NOT NULL,
    PRIMARY KEY (match_id, team, player_id)
)
"""
_MATCH_COLUMNS = (
    "match_id, date, team_a, team_b, venue, city, toss_winner, toss_decision, winner, "
    "result_type, margin_runs, margin_wickets, event, source"
)


class MatchStore:
    def __init__(self, path: Path):
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as con:
            con.execute(_CREATE_MATCHES)
            con.execute(_CREATE_APPEARANCES)

    def save(self, parsed: Iterable[ParsedMatch], replace_source: str | None = None) -> None:
        """Insert matches, replacing any already stored with the same match_id.

        With `replace_source`, every stored match from that source is removed first, so
        rows edited out of (or superseded in) that source don't linger. All in one transaction.
        """
        items = list(parsed)
        ids = [(p.match.match_id,) for p in items]
        match_rows = [_match_to_row(p.match) for p in items]
        appearance_rows = [
            (a.match_id, a.team, a.player_name, a.player_id) for p in items for a in p.appearances
        ]
        with self._transaction() as con:
            if replace_source is not None:
                con.execute(
                    "DELETE FROM appearances WHERE match_id IN "
                    "(SELECT match_id FROM matches WHERE source = ?)",
                    [replace_source],
                )
                con.execute("DELETE FROM matches WHERE source = ?", [replace_source])
            if not items:
                return
            con.executemany("DELETE FROM appearances WHERE match_id = ?", ids)
            con.executemany("DELETE FROM matches WHERE match_id = ?", ids)
            placeholders = ", ".join("?" * len(match_rows[0]))
            con.executemany(
                f"INSERT INTO matches ({_MATCH_COLUMNS}) VALUES ({placeholders})", match_rows
            )
            if appearance_rows:
                con.executemany(
                    "INSERT INTO appearances (match_id, team, player_name, player_id) "
                    "VALUES (?, ?, ?, ?)",
                    appearance_rows,
                )

    @contextmanager
    def _transaction(self) -> Iterator[duckdb.DuckDBPyConnection]:
        with self._connect() as con:
            con.execute("BEGIN TRANSACTION")
            try:
                yield con
            except BaseException:
                con.execute("ROLLBACK")
                raise
            con.execute("COMMIT")

    def load_matches(self, since: date | None = None) -> list[Match]:
        query = f"SELECT {_MATCH_COLUMNS} FROM matches"
        params: list[object] = []
        if since is not None:
            query += " WHERE date >= ?"
            params.append(since)
        query += " ORDER BY date, match_id"
        with self._connect() as con:
            rows = con.execute(query, params).fetchall()
        return [_row_to_match(row) for row in rows]

    def count_appearances(self) -> int:
        with self._connect() as con:
            return con.execute("SELECT count(*) FROM appearances").fetchone()[0]

    def _connect(self) -> duckdb.DuckDBPyConnection:
        return duckdb.connect(str(self._path))


def _match_to_row(m: Match) -> tuple:
    return (
        m.match_id,
        m.date,
        m.team_a,
        m.team_b,
        m.venue,
        m.city,
        m.toss_winner,
        m.toss_decision,
        m.winner,
        m.result_type.value,
        m.margin_runs,
        m.margin_wickets,
        m.event,
        m.source,
    )


def _row_to_match(row: tuple) -> Match:
    (match_id, day, team_a, team_b, venue, city, toss_winner, toss_decision, winner,
     result_type, margin_runs, margin_wickets, event, source) = row  # fmt: skip
    return Match(
        match_id=match_id,
        date=day,
        team_a=team_a,
        team_b=team_b,
        venue=venue,
        city=city,
        toss_winner=toss_winner,
        toss_decision=toss_decision,
        winner=winner,
        result_type=ResultType(result_type),
        margin_runs=margin_runs,
        margin_wickets=margin_wickets,
        event=event,
        source=source,
    )
