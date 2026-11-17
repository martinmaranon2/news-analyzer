"""PostgreSQL access: create the table, save analyses, read them back."""

import os
from datetime import datetime
from pathlib import Path
from typing import Literal

import psycopg
from psycopg.rows import class_row
from pydantic import BaseModel # To make sure we have all data in format we want

SCHEMA_PATH = Path(__file__).parent / "schema.sql"

Sentiment = Literal["positive", "neutral", "negative"]


class NewAnalysis(BaseModel):
    """An analysis ready to be saved; Postgres adds id and created_at."""

    url: str
    title: str
    source: str
    published_at: datetime
    summary: str
    subject: str
    sentiment: Sentiment
    sentiment_score: float
    reason: str
    text_source: Literal["full_text", "snippet"]
    model: str


class StoredAnalysis(NewAnalysis):
    """A saved analysis: one row of the analyses table."""

    id: int
    created_at: datetime


def _connect() -> psycopg.Connection:
    """Open a new connection to the database named in the DATABASE_URL setting."""
    return psycopg.connect(os.environ["DATABASE_URL"])


def init_db() -> None:
    """Create the analyses table if it doesn't exist yet."""
    with _connect() as conn:
        conn.execute(SCHEMA_PATH.read_text()) # We read all of schema.sql and execute it


def save_analysis(analysis: NewAnalysis) -> int:
    """Insert one analysis and return the id Postgres gave it."""
    with _connect() as conn:
        row = conn.execute(
            """
            INSERT INTO analyses (url, title, source, published_at, summary, subject,
                                  sentiment, sentiment_score, reason, text_source, model)
            VALUES (%(url)s, %(title)s, %(source)s, %(published_at)s, %(summary)s, %(subject)s,
                    %(sentiment)s, %(sentiment_score)s, %(reason)s, %(text_source)s, %(model)s)
            RETURNING id
            """,
            analysis.model_dump(), # turns analysis into dictionary to fill into VALUES
        ).fetchone() # execute returns cursor holding a table, in this case 1x1; pick first row with fetchone(): (new_id,)
    return row[0]


def get_analysis(analysis_id: int) -> StoredAnalysis | None:
    """Return the analysis with this id, or None if there is none."""
    with _connect() as conn:
        cursor = conn.cursor(row_factory=class_row(StoredAnalysis)) # turn SQL rows back into stored analysis object
        return cursor.execute("SELECT * FROM analyses WHERE id = %s", (analysis_id,)).fetchone()


def get_analysis_by_url(url: str) -> StoredAnalysis | None:
    """Return the analysis of this article URL, or None if it wasn't analysed yet."""
    with _connect() as conn:
        cursor = conn.cursor(row_factory=class_row(StoredAnalysis))
        return cursor.execute("SELECT * FROM analyses WHERE url = %s", (url,)).fetchone()


def list_analyses(sentiment: Sentiment | None = None) -> list[StoredAnalysis]:
    """Return saved analyses, newest article first; only those with one sentiment if given."""
    with _connect() as conn:
        cursor = conn.cursor(row_factory=class_row(StoredAnalysis))
        if sentiment is None:
            return cursor.execute("SELECT * FROM analyses ORDER BY published_at DESC").fetchall()
        return cursor.execute(
            "SELECT * FROM analyses WHERE sentiment = %s ORDER BY published_at DESC", (sentiment,)
        ).fetchall()
