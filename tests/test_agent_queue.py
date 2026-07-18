import pytest
from fastapi.testclient import TestClient

from agent.queue_client import QueueClient, build_http_client


@pytest.fixture()
def http(tmp_path, monkeypatch):
    """Real Queue API app in-process — TestClient is a sync httpx.Client."""
    monkeypatch.setenv("QUEUE_DB", str(tmp_path / "queue.db"))
    monkeypatch.setenv("QUEUE_AUTH_MODE", "disabled")
    from app.main import create_app

    return TestClient(create_app())


@pytest.fixture()
def client(http):
    return QueueClient(http)


def seed(http, url):
    return http.post("/links", json={"url": url}).json()


class TestQueueClient:
    def test_claim_returns_pending_links(self, http, client):
        seed(http, "https://example.com/a")
        seed(http, "https://example.com/b")
        links = client.claim(limit=10)
        assert [link["url"] for link in links] == [
            "https://example.com/a",
            "https://example.com/b",
        ]
        assert all(link["status"] == "processing" for link in links)

    def test_done_reports_note_path(self, http, client):
        link = seed(http, "https://example.com/a")
        client.claim(limit=1)
        client.done(link["id"], note_path="AI Engineering/Note.md")
        got = http.get("/links").json()[0]
        assert got["status"] == "done"
        assert got["note_path"] == "AI Engineering/Note.md"

    def test_failed_reports_error(self, http, client):
        link = seed(http, "https://example.com/a")
        client.claim(limit=1)
        client.failed(link["id"], error="HTTP 404")
        got = http.get("/links").json()[0]
        assert got["status"] == "failed"
        assert got["error"] == "HTTP 404"


class TestBuildHttpClient:
    def test_sets_base_url_and_service_token_headers(self):
        c = build_http_client(
            "https://queue.example.dev", "id.access", "secret123"
        )
        assert c.base_url == "https://queue.example.dev"
        assert c.headers["CF-Access-Client-Id"] == "id.access"
        assert c.headers["CF-Access-Client-Secret"] == "secret123"
