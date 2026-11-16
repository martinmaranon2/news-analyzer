"""PostgreSQL access: create the table, save analyses, read them back."""

import os
from pathlib import Path

import psycopg

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def _connect() -> psycopg.Connection:
    """Open a new connection to the database named in the DATABASE_URL setting."""
    return psycopg.connect(os.environ["DATABASE_URL"])


def init_db() -> None:
    """Create the analyses table if it doesn't exist yet."""
    with _connect() as conn:
        conn.execute(SCHEMA_PATH.read_text())
