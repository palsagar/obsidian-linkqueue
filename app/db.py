import sqlite3
import time
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

SCHEMA = """
CREATE TABLE IF NOT EXISTS links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL,
    url_normalized TEXT NOT NULL UNIQUE,
    note TEXT,
    source TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    lease_expires_at REAL,
    note_path TEXT,
    error TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at REAL NOT NULL,
    finished_at REAL NOT NULL,
    outcome TEXT NOT NULL,
    done INTEGER NOT NULL DEFAULT 0,
    failed INTEGER NOT NULL DEFAULT 0,
    error TEXT
);
"""


def connect(path: str) -> sqlite3.Connection:
    # check_same_thread=False: FastAPI opens the connection in a threadpool
    # thread but async endpoints use it from the event loop thread. Safe here
    # because each request gets its own connection.
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    return conn


def normalize_url(url: str) -> str:
    parts = urlparse(url)
    query = [(k, v) for k, v in parse_qsl(parts.query) if not k.startswith("utm_")]
    return urlunparse(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            parts.path.rstrip("/") or "/",
            parts.params,
            urlencode(query),
            "",  # drop fragment
        )
    )


def capture(conn: sqlite3.Connection, url: str, note: str | None, source: str | None):
    """Insert a link, or return the existing one with the same normalized URL.

    Returns (row, created)."""
    normalized = normalize_url(url)
    existing = conn.execute(
        "SELECT * FROM links WHERE url_normalized = ?", (normalized,)
    ).fetchone()
    if existing:
        return existing, False
    now = time.time()
    row = conn.execute(
        "INSERT INTO links (url, url_normalized, note, source, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?) RETURNING *",
        (url, normalized, note, source, now, now),
    ).fetchone()
    conn.commit()
    return row, True


def list_links(conn: sqlite3.Connection, status: str | None):
    if status:
        return conn.execute(
            "SELECT * FROM links WHERE status = ? ORDER BY id DESC", (status,)
        ).fetchall()
    return conn.execute("SELECT * FROM links ORDER BY id DESC").fetchall()


def claim(conn: sqlite3.Connection, limit: int, lease_seconds: int):
    """Atomically move up to `limit` claimable links to processing with a lease.

    Claimable: pending, or processing with an expired lease (crashed run)."""
    now = time.time()
    rows = conn.execute(
        """
        UPDATE links SET status = 'processing', lease_expires_at = ?, updated_at = ?
        WHERE id IN (
            SELECT id FROM links
            WHERE status = 'pending'
               OR (status = 'processing' AND lease_expires_at < ?)
            ORDER BY id LIMIT ?
        )
        RETURNING *
        """,
        (now + lease_seconds, now, now, limit),
    ).fetchall()
    conn.commit()
    return rows


def set_outcome(
    conn: sqlite3.Connection,
    link_id: int,
    status: str,
    note_path: str | None,
    error: str | None,
):
    if status == "pending":  # retry: clear the failure state
        error = None
    row = conn.execute(
        "UPDATE links SET status = ?, note_path = COALESCE(?, note_path), error = ?,"
        " lease_expires_at = NULL, updated_at = ? WHERE id = ? RETURNING *",
        (status, note_path, error, time.time(), link_id),
    ).fetchone()
    conn.commit()
    return row


def record_run(
    conn: sqlite3.Connection,
    started_at: float,
    finished_at: float,
    outcome: str,
    done: int,
    failed: int,
    error: str | None,
):
    row = conn.execute(
        "INSERT INTO runs (started_at, finished_at, outcome, done, failed, error)"
        " VALUES (?, ?, ?, ?, ?, ?) RETURNING *",
        (started_at, finished_at, outcome, done, failed, error),
    ).fetchone()
    conn.commit()
    return row


def last_run(conn: sqlite3.Connection):
    return conn.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 1").fetchone()


def delete_link(conn: sqlite3.Connection, link_id: int) -> bool:
    deleted = conn.execute("DELETE FROM links WHERE id = ?", (link_id,)).rowcount > 0
    conn.commit()
    return deleted
