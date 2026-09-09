"""Local web library: browse books, resume where you left off, search."""

from __future__ import annotations

import mimetypes
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response

from .. import config as _config
from .. import db as _db

STATIC = Path(__file__).parent / "static"


def _range_response(path: Path, request: Request) -> Response:
    """Serve a file honouring HTTP Range, so the player can seek."""
    size = path.stat().st_size
    media = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    rng = request.headers.get("range")
    if not rng:
        return FileResponse(path, media_type=media)
    m = re.match(r"bytes=(\d*)-(\d*)", rng)
    if not m:
        return FileResponse(path, media_type=media)
    start = int(m.group(1)) if m.group(1) else 0
    end = int(m.group(2)) if m.group(2) else size - 1
    start, end = max(0, start), min(end, size - 1)
    if start > end:
        raise HTTPException(status_code=416, detail="range not satisfiable")
    with open(path, "rb") as fh:
        fh.seek(start)
        chunk = fh.read(end - start + 1)
    return Response(
        chunk,
        status_code=206,
        media_type=media,
        headers={
            "Content-Range": f"bytes {start}-{end}/{size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(len(chunk)),
        },
    )


def create_app(cfg: _config.Config) -> FastAPI:
    app = FastAPI(title="Lectern")

    def conn():
        if not cfg.available():
            raise HTTPException(
                status_code=503,
                detail=f"library unavailable at {cfg.library_root} "
                "(is the external drive mounted?)",
            )
        return _db.connect(cfg.db_path)

    @app.get("/", response_class=HTMLResponse)
    def index():
        return (STATIC / "index.html").read_text(encoding="utf-8")

    @app.get("/api/books")
    def books():
        c = conn()
        rows = c.execute(
            """SELECT b.id,b.slug,b.title,b.author,
                      COUNT(ch.id) AS n_chapters,
                      COALESCE(SUM(ch.duration),0) AS total,
                      p.chapter_id AS pos_chapter, p.offset_sec AS pos_offset
               FROM books b
               LEFT JOIN chapters ch ON ch.book_id = b.id
               LEFT JOIN positions p ON p.book_id = b.id
               GROUP BY b.id ORDER BY b.added_at DESC"""
        ).fetchall()
        out = []
        for r in rows:
            elapsed = 0.0
            if r["pos_chapter"]:
                prior = c.execute(
                    """SELECT COALESCE(SUM(duration),0) d FROM chapters
                       WHERE book_id=? AND idx < (SELECT idx FROM chapters WHERE id=?)""",
                    (r["id"], r["pos_chapter"]),
                ).fetchone()["d"]
                elapsed = prior + (r["pos_offset"] or 0)
            total = r["total"] or 0
            out.append(
                {
                    "slug": r["slug"],
                    "title": r["title"],
                    "author": r["author"],
                    "chapters": r["n_chapters"],
                    "total": total,
                    "elapsed": elapsed,
                    "progress": (elapsed / total) if total else 0.0,
                }
            )
        return out

    @app.get("/api/books/{slug}")
    def book(slug: str):
        c = conn()
        b = _db.book_by_slug(c, slug)
        if not b:
            raise HTTPException(404, "no such book")
        chapters = [
            {
                "id": r["id"],
                "idx": r["idx"],
                "title": r["title"],
                "duration": r["duration"] or 0,
                "has_audio": bool(r["audio_path"]),
                "page_start": r["page_start"],
            }
            for r in _db.chapters_for(c, b["id"])
        ]
        pos = c.execute("SELECT * FROM positions WHERE book_id=?", (b["id"],)).fetchone()
        return {
            "slug": b["slug"],
            "title": b["title"],
            "author": b["author"],
            "chapters": chapters,
            "position": (
                {"chapter_id": pos["chapter_id"], "offset": pos["offset_sec"]} if pos else None
            ),
        }

    @app.get("/api/audio/{slug}/{idx}")
    def audio(slug: str, idx: int, request: Request):
        c = conn()
        b = _db.book_by_slug(c, slug)
        if not b:
            raise HTTPException(404, "no such book")
        row = c.execute(
            "SELECT audio_path FROM chapters WHERE book_id=? AND idx=?", (b["id"], idx)
        ).fetchone()
        if not row or not row["audio_path"]:
            raise HTTPException(404, "chapter not rendered")
        path = Path(row["audio_path"])
        if not path.exists():
            raise HTTPException(404, "audio file missing")
        return _range_response(path, request)

    @app.post("/api/position/{slug}")
    async def set_position(slug: str, request: Request):
        payload = await request.json()
        c = conn()
        b = _db.book_by_slug(c, slug)
        if not b:
            raise HTTPException(404, "no such book")
        c.execute(
            """INSERT INTO positions (book_id,chapter_id,offset_sec,updated_at)
               VALUES (?,?,?,?)
               ON CONFLICT(book_id) DO UPDATE SET
                 chapter_id=excluded.chapter_id,
                 offset_sec=excluded.offset_sec,
                 updated_at=excluded.updated_at""",
            (b["id"], payload.get("chapter_id"), float(payload.get("offset", 0)), _db.now()),
        )
        c.commit()
        return JSONResponse({"ok": True})

    @app.get("/api/search")
    def search(q: str, limit: int = 20):
        if not q.strip():
            return []
        c = conn()
        try:
            hits = _db.search(c, q, limit)
        except Exception:
            return []
        return [dict(h) for h in hits]

    return app


def serve(cfg: _config.Config, host: str = "127.0.0.1", port: int = 8765) -> None:
    import uvicorn

    if host not in {"127.0.0.1", "localhost"}:
        print(f"  ! serving on {host} exposes your library to the local network")
    print(f"  Lectern library: http://{host}:{port}")
    uvicorn.run(create_app(cfg), host=host, port=port, log_level="warning")
