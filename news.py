"""News search through the GNews API, and downloading an article's full text."""

import os
from datetime import datetime

import httpx
import trafilatura
from pydantic import BaseModel

GNEWS_SEARCH_URL = "https://gnews.io/api/v4/search"
MIN_TEXT_LENGTH = 500  # shorter extracted "articles" are usually cookie banners or paywall teasers
MAX_TEXT_LENGTH = 20_000  # caps the size, and so the cost, of one AI call
# Many news sites refuse requests that don't look like they come from a browser.
BROWSER_HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                                 "(KHTML, like Gecko) Chrome/131.0 Safari/537.36"}


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


def fetch_article_text(url: str) -> str | None:
    """Download the article's page and extract its main text; None if that isn't possible."""
    try:
        response = httpx.get(url, headers=BROWSER_HEADERS, follow_redirects=True, timeout=10)
        response.raise_for_status()
    except httpx.HTTPError:
        return None
    text = trafilatura.extract(response.text)
    if text is None or len(text) < MIN_TEXT_LENGTH:
        return None
    return text[:MAX_TEXT_LENGTH]
