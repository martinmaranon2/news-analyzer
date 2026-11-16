"""PostgreSQL access: create the table, save analyses, read them back."""

import os
from datetime import datetime
from pathlib import Path
from typing import Literal

import psycopg
from pydantic import BaseModel

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
            analysis.model_dump(),
        ).fetchone()
    return row[0]
