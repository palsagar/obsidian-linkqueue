"""Thin client for the deployed Queue API, authenticated by CF service token."""

import httpx


def build_http_client(queue_url: str, client_id: str, client_secret: str) -> httpx.Client:
    return httpx.Client(
        base_url=queue_url,
        headers={
            "CF-Access-Client-Id": client_id,
            "CF-Access-Client-Secret": client_secret,
        },
        timeout=30,
    )


class QueueClient:
    def __init__(self, http: httpx.Client):
        self.http = http

    def claim(self, limit: int, lease_seconds: int = 900) -> list[dict]:
        resp = self.http.post(
            "/links/claim", json={"limit": limit, "lease_seconds": lease_seconds}
        )
        resp.raise_for_status()
        return resp.json()

    def done(self, link_id: int, note_path: str) -> None:
        self.http.patch(
            f"/links/{link_id}", json={"status": "done", "note_path": note_path}
        ).raise_for_status()

    def failed(self, link_id: int, error: str) -> None:
        self.http.patch(
            f"/links/{link_id}", json={"status": "failed", "error": error}
        ).raise_for_status()
