import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("QUEUE_DB", str(tmp_path / "queue.db"))
    monkeypatch.setenv("QUEUE_AUTH_MODE", "disabled")
    from app.main import create_app

    return TestClient(create_app())


def report(client, **overrides):
    body = {
        "started_at": 1000.0,
        "finished_at": 1060.0,
        "outcome": "ok",
        "done": 2,
        "failed": 1,
        **overrides,
    }
    return client.post("/runs", json=body)


class TestRuns:
    def test_report_run_records_heartbeat(self, client):
        resp = report(client)
        assert resp.status_code == 201
        body = resp.json()
        assert body["outcome"] == "ok"
        assert body["done"] == 2
        assert body["failed"] == 1
        assert body["error"] is None

    def test_dashboard_shows_latest_run(self, client):
        report(client)
        report(client, outcome="sync_failed", error="no session", done=0, failed=0)
        html = client.get("/").text
        assert "sync_failed" in html
        assert "no session" in html

    def test_dashboard_without_runs_omits_heartbeat(self, client):
        html = client.get("/").text
        assert "Agent last ran" not in html
