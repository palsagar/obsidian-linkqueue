import json
import os
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
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


def create_app() -> FastAPI:
    app = FastAPI(title="linkqueue")
    db_path = os.environ.get("QUEUE_DB", "queue.db")

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
        return Response(
            content=dict_json(row), status_code=201 if created else 200,
            media_type="application/json",
        )

    @app.get("/links")
    def list_links(status: str | None = None, conn=Depends(get_db)):
        return [dict(r) for r in db.list_links(conn, status)]

    @app.post("/links/claim")
    def claim_links(body: ClaimIn, conn=Depends(get_db)):
        return [dict(r) for r in db.claim(conn, body.limit, body.lease_seconds)]

    @app.patch("/links/{link_id}")
    def set_outcome(link_id: int, body: OutcomeIn, conn=Depends(get_db)):
        row = db.set_outcome(conn, link_id, body.status, body.note_path, body.error)
        if row is None:
            raise HTTPException(status_code=404)
        return dict(row)

    @app.delete("/links/{link_id}", status_code=204)
    def delete_link(link_id: int, conn=Depends(get_db)):
        if not db.delete_link(conn, link_id):
            raise HTTPException(status_code=404)

    @app.get("/", response_class=HTMLResponse)
    def dashboard(request: Request, conn=Depends(get_db)):
        links = [dict(r) for r in db.list_links(conn, None)]
        return templates.TemplateResponse(
            request, "dashboard.html", {"links": links}
        )

    @app.post("/dashboard/capture")
    async def dashboard_capture(request: Request, conn=Depends(get_db)):
        form = await request.form()
        body = CaptureIn(url=str(form["url"]), source="dashboard")
        db.capture(conn, body.url, body.note, body.source)
        return RedirectResponse("/", status_code=303)

    @app.post("/dashboard/links/{link_id}/retry")
    def dashboard_retry(link_id: int, conn=Depends(get_db)):
        db.set_outcome(conn, link_id, "pending", None, None)
        return RedirectResponse("/", status_code=303)

    @app.post("/dashboard/links/{link_id}/delete")
    def dashboard_delete(link_id: int, conn=Depends(get_db)):
        db.delete_link(conn, link_id)
        return RedirectResponse("/", status_code=303)

    return app


def dict_json(row) -> str:
    return json.dumps(dict(row))
