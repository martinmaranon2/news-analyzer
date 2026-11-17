"""News Analyzer: search recent news, analyse articles with AI, store and list them, brief on a topic."""

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import analyzer
import db
import news

load_dotenv()  # copy the settings from .env into os.environ (on Render there is no .env: it does nothing)
db.init_db()

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="News Analyzer")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")  # static/app.js → /static/app.js


class SearchResult(BaseModel):
    """One search hit, plus its saved analysis if the article was analysed before."""

    article: news.Article
    analysis: db.StoredAnalysis | None


class BriefingRequest(BaseModel):
    """The JSON body of POST /api/briefings: which topic (search) to sum up."""

    topic: str = Field(max_length=200)


class Briefing(analyzer.TopicBriefing):
    """The AI's verdict, headline and briefing on a topic, plus what it was based on."""

    topic: str
    analysis_count: int


@app.get("/api/health")
def health() -> dict[str, str]:
    """Tell the caller (me, or Render's health check) that the server is running."""
    return {"status": "ok", "service": "news analyzer"}


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    """Serve the page; its JavaScript then calls the /api routes."""
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/articles")
def search_news(q: str = Query(min_length=1, max_length=200)) -> list[SearchResult]:
    """Search recent news; each result says whether it has been analysed already."""
    try:
        articles = news.search_articles(q)
    except news.NewsError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    return [SearchResult(article=a, analysis=db.get_analysis_by_url(a.url)) for a in articles]


@app.post("/api/analyses", status_code=201)
def create_analysis(
    article: news.Article, response: Response, topic: str | None = Query(default=None, max_length=200)
) -> db.StoredAnalysis:
    """Analyse an article with AI and save it (201); if it was analysed before, return that (200).

    ?topic= is the search that found the article, saved so the analyses can be filtered by topic later.
    """
    existing = db.get_analysis_by_url(article.url)
    if existing is not None:
        response.status_code = 200
        return existing
    try:
        new_analysis = _analyze_article(article, _normalise_topic(topic))
    except analyzer.AnalysisError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    analysis_id = db.save_analysis(new_analysis)
    response.headers["Location"] = f"/api/analyses/{analysis_id}"
    return db.get_analysis(analysis_id)


@app.get("/api/analyses")
def list_saved_analyses(sentiment: db.Sentiment | None = None, topic: str | None = None) -> list[db.StoredAnalysis]:
    """Return all saved analyses, newest article first; ?sentiment= and ?topic= narrow the list."""
    return db.list_analyses(sentiment, _normalise_topic(topic))


@app.get("/api/topics")
def list_saved_topics() -> list[db.Topic]:
    """Return the topics (searches) that have saved analyses, with how many each: feeds the topic filter."""
    return db.list_topics()


@app.get("/api/analyses/{analysis_id}")
def get_saved_analysis(analysis_id: int) -> db.StoredAnalysis:
    """Return one saved analysis, or 404 if there is none with this id."""
    analysis = db.get_analysis(analysis_id)
    if analysis is None:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return analysis


@app.post("/api/briefings")
def create_briefing(request: BriefingRequest) -> Briefing:
    """Sum up all saved analyses of one topic with AI; 404 if the topic has none.

    Not saved: each call asks the model again, so the briefing includes analyses added since the last one.
    """
    topic = _normalise_topic(request.topic)
    analyses = db.list_analyses(topic=topic) if topic else []  # only spaces means no topic, not "all topics"
    if not analyses:
        raise HTTPException(status_code=404, detail=f"No saved analyses for the topic {request.topic!r}")
    try:
        result = analyzer.brief(topic, analyses)
    except analyzer.AnalysisError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    return Briefing(**result.model_dump(), topic=topic, analysis_count=len(analyses))


def _normalise_topic(topic: str | None) -> str | None:
    """Trim and lower-case a topic, so "Nvidia " and "nvidia" are the same topic; empty means no topic."""
    if topic is None or not topic.strip():
        return None
    return topic.strip().lower()


def _analyze_article(article: news.Article, topic: str | None) -> db.NewAnalysis:
    """Get the article's text (the full page if possible, else the snippet) and analyse it with AI."""
    text = news.fetch_article_text(article.url)
    result = analyzer.analyze(article.title, text or article.description)
    return db.NewAnalysis(
        url=article.url,
        title=article.title,
        source=article.source,
        published_at=article.published_at,
        **result.model_dump(),  # summary, subject, sentiment, sentiment_score, reason, **unpacks dict
        text_source="full_text" if text else "snippet",
        model=os.environ["OPENAI_MODEL"],
        topic=topic,
    )
