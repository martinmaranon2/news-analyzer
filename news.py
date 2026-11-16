"""News search through the GNews API."""

import os
from datetime import datetime

import httpx
from pydantic import BaseModel

GNEWS_SEARCH_URL = "https://gnews.io/api/v4/search"


class NewsError(Exception):
    """The news search failed: GNews unreachable, key rejected, or quota used up."""


class Article(BaseModel):
    """One news article from a search."""

    url: str
    title: str
    source: str
    published_at: datetime
    description: str


def search_articles(query: str, max_results: int = 10) -> list[Article]:
    """Return the newest English articles matching the query."""
    try:
        response = httpx.get(
            GNEWS_SEARCH_URL,
            params={"q": query, "lang": "en", "max": max_results, "sortby": "publishedAt"},
            headers={"X-Api-Key": os.environ["GNEWS_API_KEY"]},
            timeout=10,
        )
        response.raise_for_status()
    except httpx.HTTPError as error:
        raise NewsError(f"News search failed: {error}") from error
    # response.json() is a dict with int totalArticles and articles. Articles is a list of dicts
    return [_to_article(item) for item in response.json()["articles"]] 


def _to_article(item: dict) -> Article:
    """Convert one article from GNews's JSON format into our Article."""
    return Article(
        url=item["url"],
        title=item["title"],
        source=item["source"]["name"],
        published_at=item["publishedAt"],
        description=item["description"],
    )
