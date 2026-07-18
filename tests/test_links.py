import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("QUEUE_DB", str(tmp_path / "queue.db"))
    monkeypatch.setenv("QUEUE_AUTH_MODE", "disabled")
    from app.main import create_app

    return TestClient(create_app())


def capture(client, url, **extra):
    return client.post("/links", json={"url": url, **extra})


class TestCapture:
    def test_capture_creates_pending_link(self, client):
        resp = capture(client, "https://example.com/post", note="looks cool", source="iphone")
        assert resp.status_code == 201
        body = resp.json()
        assert body["url"] == "https://example.com/post"
        assert body["status"] == "pending"
        assert body["note"] == "looks cool"
        assert body["source"] == "iphone"

    def test_capture_dedups_on_normalized_url(self, client):
        first = capture(client, "https://example.com/post?utm_source=share&utm_medium=ios")
        dupe = capture(client, "https://Example.com/post/")
        assert dupe.status_code == 200  # existing link returned, not created
        assert dupe.json()["id"] == first.json()["id"]

    def test_distinct_urls_are_not_deduped(self, client):
        a = capture(client, "https://example.com/a")
        b = capture(client, "https://example.com/b")
        assert a.json()["id"] != b.json()["id"]

    def test_capture_rejects_non_http_urls(self, client):
        assert capture(client, "not a url").status_code == 422
        assert capture(client, "ftp://example.com/x").status_code == 422


class TestListing:
    def test_list_filters_by_status(self, client):
        capture(client, "https://example.com/a")
        capture(client, "https://example.com/b")
        pending = client.get("/links", params={"status": "pending"}).json()
        assert len(pending) == 2
        done = client.get("/links", params={"status": "done"}).json()
        assert done == []


class TestClaim:
    def test_claim_marks_links_processing_with_lease(self, client):
        capture(client, "https://example.com/a")
        claimed = client.post("/links/claim", json={"limit": 5}).json()
        assert len(claimed) == 1
        assert claimed[0]["status"] == "processing"
        assert claimed[0]["lease_expires_at"] is not None

    def test_claimed_links_are_not_claimable_again(self, client):
        capture(client, "https://example.com/a")
        client.post("/links/claim", json={"limit": 5})
        second = client.post("/links/claim", json={"limit": 5}).json()
        assert second == []

    def test_claim_respects_limit(self, client):
        for i in range(3):
            capture(client, f"https://example.com/{i}")
        claimed = client.post("/links/claim", json={"limit": 2}).json()
        assert len(claimed) == 2

    def test_expired_lease_is_claimable_again(self, client):
        capture(client, "https://example.com/a")
        client.post("/links/claim", json={"limit": 5, "lease_seconds": -1})
        reclaimed = client.post("/links/claim", json={"limit": 5}).json()
        assert len(reclaimed) == 1


class TestOutcome:
    def test_done_records_note_path(self, client):
        link_id = capture(client, "https://example.com/a").json()["id"]
        client.post("/links/claim", json={"limit": 5})
        resp = client.patch(
            f"/links/{link_id}",
            json={"status": "done", "note_path": "ML & Deep Learning/Some Note.md"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "done"
        assert resp.json()["note_path"] == "ML & Deep Learning/Some Note.md"

    def test_failed_records_error_and_retry_requeues(self, client):
        link_id = capture(client, "https://example.com/a").json()["id"]
        client.post("/links/claim", json={"limit": 5})
        failed = client.patch(f"/links/{link_id}", json={"status": "failed", "error": "dead URL"})
        assert failed.json()["error"] == "dead URL"
        retried = client.patch(f"/links/{link_id}", json={"status": "pending"})
        assert retried.json()["status"] == "pending"
        assert retried.json()["error"] is None

    def test_unknown_link_404s(self, client):
        assert client.patch("/links/999", json={"status": "done"}).status_code == 404

    def test_delete_removes_link(self, client):
        link_id = capture(client, "https://example.com/a").json()["id"]
        assert client.delete(f"/links/{link_id}").status_code == 204
        assert client.get("/links").json() == []


class TestDashboard:
    def test_dashboard_lists_links(self, client):
        capture(client, "https://example.com/interesting-post")
        resp = client.get("/")
        assert resp.status_code == 200
        assert "interesting-post" in resp.text

    def test_dashboard_capture_form_queues_link(self, client):
        resp = client.post(
            "/dashboard/capture",
            data={"url": "https://example.com/from-form"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        links = client.get("/links").json()
        assert [link["url"] for link in links] == ["https://example.com/from-form"]
        assert links[0]["source"] == "dashboard"


class TestAuth:
    def test_cloudflare_mode_rejects_requests_without_assertion(self, tmp_path, monkeypatch):
        monkeypatch.setenv("QUEUE_DB", str(tmp_path / "queue.db"))
        monkeypatch.setenv("QUEUE_AUTH_MODE", "cloudflare")
        monkeypatch.setenv("CF_TEAM_DOMAIN", "example.cloudflareaccess.com")
        monkeypatch.setenv("CF_POLICY_AUD", "aud-value")
        from app.main import create_app

        client = TestClient(create_app())
        assert client.get("/links").status_code == 403
