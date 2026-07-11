"""SQLite registry of ingested sources (metadata, summaries, tags, content)."""
import json
import os
import sqlite3
import time

from .config import settings


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
                title        TEXT NOT NULL,
                source_type  TEXT NOT NULL,
                url          TEXT,
                summary      TEXT,
                tags         TEXT,            -- JSON array of strings
                content      TEXT,            -- full extracted text
                char_count   INTEGER,
                chunk_count  INTEGER,
                created_at   REAL
            )
            """
        )


def _row_to_dict(row: sqlite3.Row, include_content: bool = False) -> dict:
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
    }
    if include_content:
        d["content"] = row["content"]
    return d


def add_source(
    id: str,
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
               (id, title, source_type, url, summary, tags, content,
                char_count, chunk_count, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                id,
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
    return get_source(id)


def update_analysis(id: str, summary: str, tags: list[str]) -> None:
    with _conn() as c:
        c.execute(
            "UPDATE sources SET summary = ?, tags = ? WHERE id = ?",
            (summary, json.dumps(tags), id),
        )


def list_sources() -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM sources ORDER BY created_at DESC"
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_source(id: str, include_content: bool = False) -> dict | None:
    with _conn() as c:
        row = c.execute("SELECT * FROM sources WHERE id = ?", (id,)).fetchone()
    return _row_to_dict(row, include_content) if row else None


def delete_source(id: str) -> bool:
    with _conn() as c:
        cur = c.execute("DELETE FROM sources WHERE id = ?", (id,))
    return cur.rowcount > 0


def count_sources() -> int:
    with _conn() as c:
        return c.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
