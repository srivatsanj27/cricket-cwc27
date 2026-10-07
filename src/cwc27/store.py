"""DuckDB-backed storage for matches, playing XIs and ball-by-ball deliveries."""

import csv
import os
import tempfile
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from datetime import date
from pathlib import Path

import duckdb

from cwc27.ingest.cricsheet import ParsedMatch
from cwc27.ingest.deliveries import Delivery
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
_CREATE_DELIVERIES = """
CREATE TABLE IF NOT EXISTS deliveries (
    match_id      VARCHAR NOT NULL,
    innings       INTEGER NOT NULL,
    batting_team  VARCHAR NOT NULL,
    bowling_team  VARCHAR NOT NULL,
    over_no       INTEGER NOT NULL,
    ball          INTEGER NOT NULL,
    phase         VARCHAR NOT NULL,
    batter        VARCHAR NOT NULL,
    batter_id     VARCHAR NOT NULL,
    bowler        VARCHAR NOT NULL,
    bowler_id     VARCHAR NOT NULL,
    non_striker   VARCHAR NOT NULL,
    runs_batter   INTEGER NOT NULL,
    runs_extras   INTEGER NOT NULL,
    runs_total    INTEGER NOT NULL,
    wides         INTEGER NOT NULL,
    noballs       INTEGER NOT NULL,
    byes          INTEGER NOT NULL,
    legbyes       INTEGER NOT NULL,
    wickets       INTEGER NOT NULL,
    wicket_kind   VARCHAR,
    player_out    VARCHAR,
    player_out_id VARCHAR,
    fielder       VARCHAR
)
"""
MATCH_COLUMNS = (
    "match_id", "date", "team_a", "team_b", "venue", "city", "toss_winner", "toss_decision",
    "winner", "result_type", "margin_runs", "margin_wickets", "event", "source",
)  # fmt: skip
APPEARANCE_COLUMNS = ("match_id", "team", "player_name", "player_id")
DELIVERY_COLUMNS = (
    "match_id", "innings", "batting_team", "bowling_team", "over_no", "ball", "phase",
    "batter", "batter_id", "bowler", "bowler_id", "non_striker", "runs_batter",
    "runs_extras", "runs_total", "wides", "noballs", "byes", "legbyes", "wickets", "wicket_kind",
    "player_out", "player_out_id", "fielder",
)  # fmt: skip
# Child tables first, so a condition that reads `matches` still sees the rows it targets.
_TABLES_BY_DELETE_ORDER = ("appearances", "deliveries", "matches")


class MatchStore:
    def __init__(self, path: Path):
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as con:
            con.execute(_CREATE_MATCHES)
            con.execute(_CREATE_APPEARANCES)
            con.execute(_CREATE_DELIVERIES)

    def save(self, parsed: Iterable[ParsedMatch], replace_source: str | None = None) -> None:
        """Insert matches with their XIs and deliveries, replacing any with the same match_id.

        With `replace_source`, every stored match from that source is removed first, so
        rows edited out of (or superseded in) that source don't linger. All in one transaction.
        """
        items = list(parsed)
        with self._transaction() as con:
            if replace_source is not None:
                _delete_matches(
                    con,
                    "match_id IN (SELECT match_id FROM matches WHERE source = ?)",
                    [replace_source],
                )
            if not items:
                return
            con.execute("CREATE OR REPLACE TEMP TABLE _saving (match_id VARCHAR)")
            self._bulk_insert(con, "_saving", ("match_id",), [(p.match.match_id,) for p in items])
            _delete_matches(con, "match_id IN (SELECT match_id FROM _saving)", [])
            self._bulk_insert(con, "matches", MATCH_COLUMNS, [_match_row(p.match) for p in items])
            self._bulk_insert(
                con,
                "appearances",
                APPEARANCE_COLUMNS,
                [
                    (a.match_id, a.team, a.player_name, a.player_id)
                    for p in items
                    for a in p.appearances
                ],
            )
            self._bulk_insert(
                con,
                "deliveries",
                DELIVERY_COLUMNS,
                [_delivery_row(d) for p in items for d in p.deliveries],
            )

    def load_matches(self, since: date | None = None) -> list[Match]:
        query = f"SELECT {', '.join(MATCH_COLUMNS)} FROM matches"
        params: list[object] = []
        if since is not None:
            query += " WHERE date >= ?"
            params.append(since)
        query += " ORDER BY date, match_id"
        with self._connect() as con:
            rows = con.execute(query, params).fetchall()
        return [_row_to_match(row) for row in rows]

    def fetch(self, sql: str, params: Sequence[object] = ()) -> list[tuple]:
        """Run a read-only query (parameters bound with ?) and return its rows."""
        with self._connect() as con:
            return con.execute(sql, list(params)).fetchall()

    def count_appearances(self) -> int:
        return self._count("appearances")

    def count_deliveries(self) -> int:
        return self._count("deliveries")

    def _count(self, table: str) -> int:
        with self._connect() as con:
            return con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]

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

    def _bulk_insert(
        self,
        con: duckdb.DuckDBPyConnection,
        table: str,
        columns: Sequence[str],
        rows: Sequence[tuple],
    ) -> None:
        """Load rows through a temporary CSV and COPY: far faster than row-by-row inserts.

        None is written as an empty field, which COPY reads back as NULL.
        """
        if not rows:
            return
        fd, name = tempfile.mkstemp(suffix=".csv", dir=self._path.parent)
        try:
            with os.fdopen(fd, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerows(rows)
            quoted = name.replace("'", "''")
            con.execute(
                f"COPY {table} ({', '.join(columns)}) FROM '{quoted}' (FORMAT csv, HEADER false)"
            )
        finally:
            os.unlink(name)

    def _connect(self) -> duckdb.DuckDBPyConnection:
        return duckdb.connect(str(self._path))


def _delete_matches(con: duckdb.DuckDBPyConnection, condition: str, params: list) -> None:
    for table in _TABLES_BY_DELETE_ORDER:
        con.execute(f"DELETE FROM {table} WHERE {condition}", params)


def _match_row(m: Match) -> tuple:
    return (
        m.match_id,
        m.date.isoformat(),
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


def _delivery_row(d: Delivery) -> tuple:
    return (
        d.match_id, d.innings, d.batting_team, d.bowling_team, d.over, d.ball, d.phase,
        d.batter, d.batter_id, d.bowler, d.bowler_id, d.non_striker, d.runs_batter,
        d.runs_extras, d.runs_total, d.wides, d.noballs, d.byes, d.legbyes, d.wickets,
        d.wicket_kind, d.player_out, d.player_out_id, d.fielder,
    )  # fmt: skip


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
