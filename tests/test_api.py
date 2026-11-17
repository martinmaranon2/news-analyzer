"""API tests on a separate test database, with GNews and OpenAI replaced by fakes: free, fast, same result every run.

Run from the project folder: createdb news_analyzer_test (once), then .venv/bin/python -m pytest
"""

import os

import psycopg
import pytest
from fastapi.testclient import TestClient

# Set before main is imported, because main connects to the database as soon as it is imported. main's
# load_dotenv() never overwrites a variable that is already set, so the tests can't touch the real data.
os.environ["DATABASE_URL"] = "postgresql://localhost/news_analyzer_test"
os.environ["OPENAI_MODEL"] = "fake-model"

import analyzer  # noqa: E402  (these imports must come after the settings above)
import db  # noqa: E402
import main  # noqa: E402
import news  # noqa: E402

ARTICLE = {
    "url": "https://example.com/nvidia-record-revenue",
    "title": "Nvidia posts record revenue",
    "source": "Example News",
    "published_at": "2026-11-16T09:00:00Z",
    "description": "Nvidia's quarterly revenue beat expectations.",
}


def fake_search(query: str) -> list[news.Article]:
    """GNews stand-in: every search finds the same one article."""
    return [news.Article(**ARTICLE)]


def fake_analyze(title: str, text: str) -> analyzer.ArticleAnalysis:
    """OpenAI stand-in for one article."""
    return analyzer.ArticleAnalysis(summary="Nvidia beat expectations.", subject="Nvidia", sentiment="positive",
                                    sentiment_score=0.8, reason="Record revenue is good for Nvidia.")


def fake_brief(topic: str, analyses: list) -> analyzer.TopicBriefing:
    """OpenAI stand-in for a topic briefing."""
    return analyzer.TopicBriefing(verdict="positive", headline=f"Good news for {topic}", briefing="All good.")


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """The app on an empty test database, with the fakes above instead of GNews and OpenAI."""
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        conn.execute("TRUNCATE analyses")  # every test starts from an empty table
    monkeypatch.setattr(news, "search_articles", fake_search)  # undone automatically after each test
    monkeypatch.setattr(news, "fetch_article_text", lambda url: "The full article text.")
    monkeypatch.setattr(analyzer, "analyze", fake_analyze)
    monkeypatch.setattr(analyzer, "brief", fake_brief)
    return TestClient(main.app)  # sends requests straight to the app, no server needed


# ---- R1: search the news ----

def test_search_returns_articles(client: TestClient) -> None:
    response = client.get("/api/articles", params={"q": "nvidia"})
    assert response.status_code == 200
    [result] = response.json()
    assert result["article"]["title"] == ARTICLE["title"]
    assert result["analysis"] is None  # not analysed yet


def test_search_fails_with_502_when_gnews_fails(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def failing_search(query: str) -> list[news.Article]:
        raise news.NewsError("News search failed: fake outage")

    monkeypatch.setattr(news, "search_articles", failing_search)
    assert client.get("/api/articles", params={"q": "nvidia"}).status_code == 502


# ---- R2 + R4: analyse an article and store the result ----

def test_analyze_saves_analysis(client: TestClient) -> None:
    response = client.post("/api/analyses", params={"topic": " Nvidia "}, json=ARTICLE)
    assert response.status_code == 201
    analysis = response.json()
    assert (analysis["sentiment"], analysis["text_source"], analysis["topic"]) == ("positive", "full_text", "nvidia")
    assert client.get(response.headers["Location"]).json() == analysis  # stored: it can be read back
    [result] = client.get("/api/articles", params={"q": "nvidia"}).json()
    assert result["analysis"]["id"] == analysis["id"]  # a new search shows it as already analysed


def test_analyze_falls_back_to_snippet(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(news, "fetch_article_text", lambda url: None)  # e.g. a paywall
    assert client.post("/api/analyses", json=ARTICLE).json()["text_source"] == "snippet"


def test_analyze_fails_with_502_when_ai_fails(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def failing_analyze(title: str, text: str) -> analyzer.ArticleAnalysis:
        raise analyzer.AnalysisError("AI analysis failed: fake outage")

    monkeypatch.setattr(analyzer, "analyze", failing_analyze)
    assert client.post("/api/analyses", json=ARTICLE).status_code == 502
    assert client.get("/api/analyses").json() == []  # nothing half-saved


def test_analyze_rejects_non_web_url(client: TestClient) -> None:
    assert client.post("/api/analyses", json={**ARTICLE, "url": "javascript:alert(1)"}).status_code == 422


# ---- R3: analysing all (or twice) never duplicates ----

def test_analyze_same_url_returns_200(client: TestClient) -> None:
    first = client.post("/api/analyses", json=ARTICLE).json()
    second = client.post("/api/analyses", json=ARTICLE)
    assert second.status_code == 200
    assert second.json()["id"] == first["id"]
    assert len(client.get("/api/analyses").json()) == 1


def test_saving_same_url_twice_keeps_the_first(client: TestClient) -> None:
    # Two requests analysing one article at the same time both pass the "analysed before?" check and both save.
    first = client.post("/api/analyses", json=ARTICLE).json()
    db.save_analysis(db.NewAnalysis(**{**first, "summary": "A second analysis."}))  # extra keys (id) are ignored
    [saved] = client.get("/api/analyses").json()
    assert saved["summary"] == first["summary"]


# ---- R5: display saved analyses, filtered by sentiment and topic ----

def test_list_filters_by_sentiment_and_topic(client: TestClient) -> None:
    client.post("/api/analyses", params={"topic": "nvidia"}, json=ARTICLE)
    assert len(client.get("/api/analyses", params={"sentiment": "positive", "topic": "Nvidia"}).json()) == 1
    assert client.get("/api/analyses", params={"sentiment": "negative"}).json() == []
    assert client.get("/api/topics").json() == [{"topic": "nvidia", "count": 1}]


def test_get_unknown_analysis_returns_404(client: TestClient) -> None:
    assert client.get("/api/analyses/999999").status_code == 404


# ---- Topic briefing ----

def test_briefing_sums_up_a_topic(client: TestClient) -> None:
    client.post("/api/analyses", params={"topic": "nvidia"}, json=ARTICLE)
    response = client.post("/api/briefings", json={"topic": "Nvidia"})
    assert response.status_code == 200
    assert (response.json()["verdict"], response.json()["analysis_count"]) == ("positive", 1)


def test_briefing_on_topic_without_analyses_returns_404(client: TestClient) -> None:
    assert client.post("/api/briefings", json={"topic": "nvidia"}).status_code == 404
