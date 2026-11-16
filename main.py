"""News Analyzer: search recent news, analyse an article with AI, store and list the results."""

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

import db
import news

load_dotenv()  # copy the settings from .env into os.environ (on Render there is no .env: it does nothing)
db.init_db()

app = FastAPI(title="News Analyzer")


class SearchResult(BaseModel):
    """One search hit, plus its saved analysis if the article was analysed before."""

    article: news.Article
    analysis: db.StoredAnalysis | None


@app.get("/api/health")
def health() -> dict[str, str]:
    """Tell the caller (me, or Render's health check) that the server is running."""
    return {"status": "ok", "service": "news analyzer"}


@app.get("/api/articles")
def search_news(q: str = Query(min_length=1, max_length=200)) -> list[SearchResult]:
    """Search recent news; each result says whether it has been analysed already."""
    try:
        articles = news.search_articles(q)
    except news.NewsError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    return [SearchResult(article=a, analysis=db.get_analysis_by_url(a.url)) for a in articles]
