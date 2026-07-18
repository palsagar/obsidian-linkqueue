import asyncio
import threading

import pytest
from fastapi.testclient import TestClient

from app.main import Bus


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("QUEUE_DB", str(tmp_path / "queue.db"))
    monkeypatch.setenv("QUEUE_AUTH_MODE", "disabled")
    from app.main import create_app

    return create_app()


class TestBus:
    def test_stream_delivers_publish_from_another_thread(self):
        """Mutating endpoints run in threadpool threads — publish must cross
        safely into the event loop the stream runs on."""

        async def scenario():
            bus = Bus()
            stream = bus.stream()
            assert (await anext(stream)).startswith("retry:")
            t = threading.Thread(target=bus.publish)
            t.start()
            event = await asyncio.wait_for(anext(stream), timeout=5)
            t.join()
            await stream.aclose()
            return event

        assert asyncio.run(scenario()) == "data: update\n\n"

    def test_publish_with_no_listeners_is_a_noop(self):
        Bus().publish()  # must not raise


# NOTE: the /dashboard/events endpoint itself is exercised against a live
# uvicorn (TestClient deadlocks on unbounded SSE streams); the Bus above
# carries all the logic.


def test_dashboard_page_subscribes_to_events(app):
    resp = TestClient(app).get("/")
    assert "EventSource" in resp.text
    assert "/dashboard/events" in resp.text
