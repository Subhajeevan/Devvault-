"""SQLite registry of ingested sources, scoped by owner (a per-device id).

Each source has an `owner`. The web UI sends an anonymous per-browser id, so a
user only sees their own sources plus the shared "public" ones (seeded samples).
"""
import json
import os
import sqlite3
import time

from .config import settings

PUBLIC = "public"


def _conn() -> sqlite3.Connection:
    os.makedirs(settings.DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(settings.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _conn() as c:
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS sources (
                id           TEXT PRIMARY KEY,
                owner        TEXT,
                title        TEXT NOT NULL,
                source_type  TEXT NOT NULL,
                url          TEXT,
                summary      TEXT,
                tags         TEXT,
                content      TEXT,
                char_count   INTEGER,
                chunk_count  INTEGER,
                created_at   REAL
            )
            """
        )
        # Migrate older tables that predate the owner column.
        cols = [r[1] for r in c.execute("PRAGMA table_info(sources)").fetchall()]
        if "owner" not in cols:
            c.execute("ALTER TABLE sources ADD COLUMN owner TEXT")
        c.execute(
            "UPDATE sources SET owner = ? WHERE owner IS NULL OR owner = ''", (PUBLIC,)
        )


def _row_to_dict(row: sqlite3.Row, owner: str | None = None, include_content: bool = False) -> dict:
    d = {
        "id": row["id"],
        "title": row["title"],
        "source_type": row["source_type"],
        "url": row["url"],
        "summary": row["summary"],
        "tags": json.loads(row["tags"]) if row["tags"] else [],
        "char_count": row["char_count"],
        "chunk_count": row["chunk_count"],
        "created_at": row["created_at"],
        # True when the requester owns it (i.e. not a shared/public sample).
        "owned": owner is not None and row["owner"] == owner,
    }
    if include_content:
        d["content"] = row["content"]
    return d


def add_source(
    id: str,
    owner: str,
    title: str,
    source_type: str,
    url: str | None,
    summary: str,
    tags: list[str],
    content: str,
    chunk_count: int,
) -> dict:
    with _conn() as c:
        c.execute(
            """INSERT INTO sources
               (id, owner, title, source_type, url, summary, tags, content,
                char_count, chunk_count, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                id,
                owner,
                title,
                source_type,
                url,
                summary,
                json.dumps(tags),
                content,
                len(content),
                chunk_count,
                time.time(),
            ),
        )
    return get_source(id, owner)


def update_analysis(id: str, summary: str, tags: list[str]) -> None:
    with _conn() as c:
        c.execute(
            "UPDATE sources SET summary = ?, tags = ? WHERE id = ?",
            (summary, json.dumps(tags), id),
        )


def list_sources(owner: str) -> list[dict]:
    """Sources visible to `owner`: their own plus shared public ones."""
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM sources WHERE owner IN (?, ?) ORDER BY created_at DESC",
            (owner, PUBLIC),
        ).fetchall()
    return [_row_to_dict(r, owner) for r in rows]


def list_source_ids(owner: str) -> list[str]:
    """Ids of sources `owner` may retrieve from (own + public)."""
    with _conn() as c:
        rows = c.execute(
            "SELECT id FROM sources WHERE owner IN (?, ?)", (owner, PUBLIC)
        ).fetchall()
    return [r["id"] for r in rows]


def get_source(id: str, owner: str | None = None, include_content: bool = False) -> dict | None:
    with _conn() as c:
        row = c.execute("SELECT * FROM sources WHERE id = ?", (id,)).fetchone()
    if not row:
        return None
    # Enforce visibility when an owner is supplied.
    if owner is not None and row["owner"] not in (owner, PUBLIC):
        return None
    return _row_to_dict(row, owner, include_content)


def delete_source(id: str, owner: str) -> bool:
    """Delete only if the caller owns it (public samples can't be deleted)."""
    with _conn() as c:
        cur = c.execute("DELETE FROM sources WHERE id = ? AND owner = ?", (id, owner))
    return cur.rowcount > 0


def count_sources(owner: str | None = None) -> int:
    with _conn() as c:
        if owner is None:
            return c.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
        return c.execute(
            "SELECT COUNT(*) FROM sources WHERE owner = ?", (owner,)
        ).fetchone()[0]
