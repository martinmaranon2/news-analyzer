"""News Analyzer: search recent news, analyse an article with AI, store and list the results."""

from fastapi import FastAPI

app = FastAPI(title="News Analyzer")


@app.get("/api/health")
def health() -> dict[str, str]:
    """Tell the caller (me, or Render's health check) that the server is running."""
    return {"status": "ok", "service": "news analyzer"}
