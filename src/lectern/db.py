"""SQLite access. One connection factory, schema applied on open."""

from __future__ import annotations

import datetime as _dt
import sqlite3
from importlib import resources
from pathlib import Path


def now() -> str:
    return _dt.datetime.now().isoformat(timespec="seconds")


def connect(db_path: Path) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    schema = resources.files("lectern").joinpath("schema.sql").read_text(encoding="utf-8")
    conn.executescript(schema)
    return conn


def book_by_slug(conn: sqlite3.Connection, slug: str):
    return conn.execute("SELECT * FROM books WHERE slug = ?", (slug,)).fetchone()


def book_by_hash(conn: sqlite3.Connection, source_hash: str):
    return conn.execute("SELECT * FROM books WHERE source_hash = ?", (source_hash,)).fetchone()


def chapters_for(conn: sqlite3.Connection, book_id: int):
    return conn.execute(
        "SELECT * FROM chapters WHERE book_id = ? ORDER BY idx", (book_id,)
    ).fetchall()


def search(conn: sqlite3.Connection, query: str, limit: int = 20):
    """Full-text search across chapter text, with the book each hit belongs to."""
    return conn.execute(
        """
        SELECT b.slug, b.title AS book_title, c.idx, c.title AS chapter_title,
               c.page_start, snippet(chapters_fts, 1, '[', ']', ' ... ', 18) AS snippet
        FROM chapters_fts
        JOIN chapters c ON c.id = chapters_fts.rowid
        JOIN books    b ON b.id = c.book_id
        WHERE chapters_fts MATCH ?
        ORDER BY rank
        LIMIT ?
        """,
        (query, limit),
    ).fetchall()
