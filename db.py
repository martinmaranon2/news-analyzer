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
    topic: str | None = None  # the search that found the article; None for older analyses


class Topic(BaseModel):
    """A search topic and how many saved analyses came from it."""

    topic: str
    count: int


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


def save_analysis(analysis: NewAnalysis) -> None:
    """Insert one analysis. If its URL was saved meanwhile (two requests at once), keep that one."""
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO analyses (url, title, source, published_at, summary, subject,
                                  sentiment, sentiment_score, reason, text_source, model, topic)
            VALUES (%(url)s, %(title)s, %(source)s, %(published_at)s, %(summary)s, %(subject)s,
                    %(sentiment)s, %(sentiment_score)s, %(reason)s, %(text_source)s, %(model)s, %(topic)s)
            ON CONFLICT (url) DO NOTHING
            """,
            analysis.model_dump(), # turns analysis into dictionary to fill into VALUES
        )


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


def list_analyses(sentiment: Sentiment | None = None, topic: str | None = None) -> list[StoredAnalysis]:
    """Return saved analyses, newest article first; each filter that is given narrows the list."""
    with _connect() as conn:
        cursor = conn.cursor(row_factory=class_row(StoredAnalysis))
        return cursor.execute(
            """
            SELECT * FROM analyses
            WHERE (%(sentiment)s::text IS NULL OR sentiment = %(sentiment)s)  -- no filter given: true for every row
              AND (%(topic)s::text IS NULL OR topic = %(topic)s)
            ORDER BY published_at DESC
            """,
            {"sentiment": sentiment, "topic": topic},
        ).fetchall()


def list_topics() -> list[Topic]:
    """Return every topic that has saved analyses, with how many each, the biggest first."""
    with _connect() as conn:
        cursor = conn.cursor(row_factory=class_row(Topic))
        return cursor.execute(
            """
            SELECT topic, count(*) AS count FROM analyses
            WHERE topic IS NOT NULL
            GROUP BY topic
            ORDER BY count DESC, topic
            """
        ).fetchall()
