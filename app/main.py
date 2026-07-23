import asyncio
import json
import os
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, field_validator

from app import db
from app.auth import install_cloudflare_auth

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


class CaptureIn(BaseModel):
    url: str
    note: str | None = None
    source: str | None = None

    @field_validator("url")
    @classmethod
    def must_be_http(cls, v: str) -> str:
        parts = urlparse(v)
        if parts.scheme not in ("http", "https") or not parts.netloc:
            raise ValueError("must be an http(s) URL")
        return v


class ClaimIn(BaseModel):
    limit: int = 10
    lease_seconds: int = 600


class OutcomeIn(BaseModel):
    status: Literal["done", "failed", "pending"]
    note_path: str | None = None
    error: str | None = None


class RunIn(BaseModel):
    started_at: float
    finished_at: float
    outcome: str
    done: int = 0
    failed: int = 0
    error: str | None = None


class Bus:
    """In-process pub/sub for dashboard live updates. Mutating endpoints run
    in threadpool threads, so publish hops onto the event loop."""

    def __init__(self):
        self.listeners: set[asyncio.Queue] = set()
        self.loop: asyncio.AbstractEventLoop | None = None

    def publish(self) -> None:
        if self.loop is None:
            return
        for q in list(self.listeners):
            self.loop.call_soon_threadsafe(q.put_nowait, "update")

    async def stream(self):
        self.loop = asyncio.get_running_loop()
        q: asyncio.Queue = asyncio.Queue()
        self.listeners.add(q)
        try:
            yield "retry: 3000\n\n"
            while True:
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=25)
                    yield f"data: {msg}\n\n"
                except TimeoutError:
                    yield ": keepalive\n\n"  # hold the connection through proxies
        finally:
            self.listeners.discard(q)


def create_app() -> FastAPI:
    app = FastAPI(title="linkqueue")
    db_path = os.environ.get("QUEUE_DB", "queue.db")
    bus = Bus()

    if os.environ.get("QUEUE_AUTH_MODE", "cloudflare") == "cloudflare":
        install_cloudflare_auth(
            app,
            team_domain=os.environ["CF_TEAM_DOMAIN"],
            policy_aud=os.environ["CF_POLICY_AUD"],
        )

    def get_db():
        conn = db.connect(db_path)
        try:
            yield conn
        finally:
            conn.close()

    @app.post("/links")
    def capture_link(body: CaptureIn, conn=Depends(get_db)):
        row, created = db.capture(conn, body.url, body.note, body.source)
        bus.publish()
        return Response(
            content=dict_json(row), status_code=201 if created else 200,
            media_type="application/json",
        )

    @app.get("/links")
    def list_links(status: str | None = None, conn=Depends(get_db)):
        return [dict(r) for r in db.list_links(conn, status)]

    @app.post("/links/claim")
    def claim_links(body: ClaimIn, conn=Depends(get_db)):
        claimed = [dict(r) for r in db.claim(conn, body.limit, body.lease_seconds)]
        if claimed:
            bus.publish()
        return claimed

    @app.patch("/links/{link_id}")
    def set_outcome(link_id: int, body: OutcomeIn, conn=Depends(get_db)):
        row = db.set_outcome(conn, link_id, body.status, body.note_path, body.error)
        if row is None:
            raise HTTPException(status_code=404)
        bus.publish()
        return dict(row)

    @app.delete("/links/{link_id}", status_code=204)
    def delete_link(link_id: int, conn=Depends(get_db)):
        if not db.delete_link(conn, link_id):
            raise HTTPException(status_code=404)
        bus.publish()

    @app.post("/runs", status_code=201)
    def report_run(body: RunIn, conn=Depends(get_db)):
        row = db.record_run(
            conn, body.started_at, body.finished_at, body.outcome,
            body.done, body.failed, body.error,
        )
        bus.publish()
        return dict(row)

    @app.get("/dashboard/events")
    async def dashboard_events():
        return StreamingResponse(
            bus.stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/", response_class=HTMLResponse)
    def dashboard(request: Request, conn=Depends(get_db)):
        links = [dict(r) for r in db.list_links(conn, None)]
        run = db.last_run(conn)
        return templates.TemplateResponse(
            request,
            "dashboard.html",
            {"links": links, "last_run": dict(run) if run else None},
        )

    @app.post("/dashboard/capture")
    async def dashboard_capture(request: Request, conn=Depends(get_db)):
        form = await request.form()
        body = CaptureIn(url=str(form["url"]), source="dashboard")
        db.capture(conn, body.url, body.note, body.source)
        bus.publish()
        return RedirectResponse("/", status_code=303)

    @app.post("/dashboard/links/{link_id}/retry")
    def dashboard_retry(link_id: int, conn=Depends(get_db)):
        db.set_outcome(conn, link_id, "pending", None, None)
        bus.publish()
        return RedirectResponse("/", status_code=303)

    @app.post("/dashboard/links/{link_id}/delete")
    def dashboard_delete(link_id: int, conn=Depends(get_db)):
        db.delete_link(conn, link_id)
        bus.publish()
        return RedirectResponse("/", status_code=303)

    return app


def dict_json(row) -> str:
    return json.dumps(dict(row))
