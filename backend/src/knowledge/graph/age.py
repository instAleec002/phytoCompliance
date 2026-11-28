"""Thin access layer to Apache AGE through psycopg.

AGE takes Cypher parameters as one JSON map passed as the third argument of ``cypher()``; psycopg sends it as a
server-side parameter, which is what AGE requires.
"""
from __future__ import annotations

import json
from collections.abc import Iterator

import psycopg

from shared.settings import settings

from .schema import GRAPH


class AgeGraph:
    def __init__(self, conn: psycopg.Connection, graph: str = GRAPH):
        self.conn = conn
        self.graph = graph
        conn.execute("LOAD 'age'")
        conn.execute('SET search_path = ag_catalog, "$user", public')

    @classmethod
    def connect(cls, url: str | None = None, graph: str = GRAPH) -> AgeGraph:
        return cls(psycopg.connect(url or settings.database_url, autocommit=True), graph)

    def close(self) -> None:
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def run(self, cypher: str, params: dict | None = None, columns: tuple[str, ...] = ("result",)) -> list[tuple]:
        """Runs a Cypher statement and returns the rows, each value decoded from agtype to Python."""
        if "$$" in cypher:
            raise ValueError("Cypher text must not contain $$")
        cols = ", ".join(f"{c} agtype" for c in columns)
        if params is None:
            sql = f"SELECT * FROM cypher('{self.graph}', $$ {cypher} $$) AS ({cols})"
            rows = self.conn.execute(sql).fetchall()
        else:
            sql = f"SELECT * FROM cypher('{self.graph}', $$ {cypher} $$, %s) AS ({cols})"
            rows = self.conn.execute(sql, (json.dumps(params, default=str),)).fetchall()
        return [tuple(_decode(v) for v in row) for row in rows]

    def run_batches(self, cypher: str, rows: list[dict], size: int = 500) -> int:
        """Runs ``cypher`` (which must ``UNWIND $rows AS r``) over the rows in batches; returns the number of rows."""
        for batch in _chunks(rows, size):
            self.run(cypher, {"rows": batch})
        return len(rows)

    def count(self, label: str) -> int:
        return int(self.run(f"MATCH (n:{label}) RETURN count(n)")[0][0])


def _decode(value):
    if value is None:
        return None
    text = str(value)
    for suffix in ("::vertex", "::edge", "::path"):
        text = text.removesuffix(suffix)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def _chunks(rows: list, size: int) -> Iterator[list]:
    for i in range(0, len(rows), size):
        yield rows[i:i + size]
