"""Pre-fetch: one plain HTTP GET per Link, no scraping pipeline.

Whatever the page serves (title, meta/OG description, readable text) is all
the model gets — X/YouTube deliberately yield only thin metadata.
"""

from dataclasses import dataclass

import httpx
from bs4 import BeautifulSoup

TEXT_LIMIT = 8000  # bound prompt size; articles rarely need more to summarize


@dataclass
class Page:
    title: str | None = None
    description: str | None = None
    text: str = ""
    error: str | None = None


def parse_page(html: str) -> Page:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer"]):
        tag.decompose()
    title = soup.title.get_text(strip=True) if soup.title else None
    description = None
    og = soup.find("meta", attrs={"property": "og:description"})
    meta = soup.find("meta", attrs={"name": "description"})
    if og and og.get("content"):
        description = og["content"]
    elif meta and meta.get("content"):
        description = meta["content"]
    root = soup.find("article") or soup.body or soup
    text = " ".join(root.get_text(separator=" ").split())
    return Page(title=title, description=description, text=text[:TEXT_LIMIT])


def fetch(url: str, client: httpx.Client) -> Page:
    try:
        resp = client.get(url, follow_redirects=True, timeout=20)
    except httpx.HTTPError as e:
        return Page(error=f"fetch failed: {e}")
    if resp.status_code >= 400:
        return Page(error=f"HTTP {resp.status_code}")
    return parse_page(resp.text)
