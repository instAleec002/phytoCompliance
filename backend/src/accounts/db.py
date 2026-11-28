"""Connection to the accounts schema and its migrations.

The accounts live in their own schema (``cuentas``) of the same PostgreSQL, apart from the AGE graph, which is derived
data and can be rebuilt; the accounts cannot, so ``make respaldo-cuentas`` dumps this schema alone. Migrations are the
numbered SQL files of ``migrations/``, applied once each in order and recorded in ``migraciones``.
"""
from __future__ import annotations

from pathlib import Path

import psycopg

from shared.settings import settings

SCHEMA = "cuentas"
MIGRATIONS = Path(__file__).parent / "migrations"


def connect(schema: str | None = None, url: str | None = None) -> psycopg.Connection:
    """``schema``: the accounts schema, by default ACCOUNTS_SCHEMA (``cuentas``)."""
    schema = schema or settings.accounts_schema
    if not schema.replace("_", "").isalnum():
        raise ValueError(f"invalid schema name: {schema}")
    conn = psycopg.connect(url or settings.database_url, autocommit=True)
    conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
    conn.execute(f'SET search_path = "{schema}"')
    return conn


def migrate(conn: psycopg.Connection) -> list[str]:
    """Applies the pending migrations in one transaction each; returns their names."""
    conn.execute("CREATE TABLE IF NOT EXISTS migraciones (nombre text PRIMARY KEY, aplicada timestamptz NOT NULL DEFAULT now())")
    done = {r[0] for r in conn.execute("SELECT nombre FROM migraciones").fetchall()}
    applied = []
    for path in sorted(MIGRATIONS.glob("*.sql")):
        if path.name in done:
            continue
        with conn.transaction():
            conn.execute(path.read_text(encoding="utf-8"))
            conn.execute("INSERT INTO migraciones (nombre) VALUES (%s)", (path.name,))
        applied.append(path.name)
    return applied
