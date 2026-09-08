"""Library operations: add, propose structure, confirm, render, search, tidy.

Filing rules live here so that no other module invents a path -- every location comes
from :mod:`lectern.naming`.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from .. import config as _config
from .. import db as _db
from .. import naming
from ..clean import chapter_text
from ..ingest import Document, load as ingest_load
from ..package import Track, build_m4b
from ..structure import detect as _detect
from ..tts import Job, render as tts_render


class DuplicateSource(RuntimeError):
    def __init__(self, slug: str):
        super().__init__(f"already in the library as {slug!r}")
        self.slug = slug


@dataclass
class Added:
    slug: str
    title: str
    structure: _detect.Structure
    document: Document


def add(cfg: _config.Config, target: str | Path, *, title: str | None = None,
        move: bool = False) -> Added:
    """Ingest a source, propose a chapter structure, and record both (unconfirmed)."""
    _config.require_library(cfg)
    doc = ingest_load(target)
    if title:
        doc.title = title

    conn = _db.connect(cfg.db_path)
    existing = _db.book_by_hash(conn, doc.source_hash) if doc.source_hash else None
    if existing:
        raise DuplicateSource(existing["slug"])

    slug = naming.slugify(doc.title)
    n = 1
    while _db.book_by_slug(conn, slug):
        n += 1
        slug = f"{naming.slugify(doc.title)}-{n}"

    bdir = naming.book_dir(cfg.library_root, slug)
    bdir.mkdir(parents=True, exist_ok=True)

    stored_source = str(doc.source_path) if doc.source_path else ""
    if doc.source_path and move:
        dest = naming.source_path(cfg.library_root, slug, doc.source_path.suffix)
        shutil.move(str(doc.source_path), dest)
        stored_source = str(dest)
        doc.source_path = dest

    naming.pages_path(cfg.library_root, slug).write_text(
        json.dumps(doc.pages), encoding="utf-8"
    )

    pdf_for_outline = doc.source_path if doc.fmt == "pdf" else None
    structure = _detect.detect(doc.pages, pdf_for_outline)

    conn.execute(
        """INSERT INTO books (slug,title,author,source_path,source_hash,format,
               printed_offset,structure_src,n_pages,word_count,confirmed,added_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,0,?)""",
        (slug, doc.title, doc.author, stored_source, doc.source_hash, doc.fmt,
         structure.printed_offset, structure.source, len(doc.pages), doc.word_count,
         _db.now()),
    )
    book_id = conn.execute("SELECT id FROM books WHERE slug = ?", (slug,)).fetchone()["id"]
    _write_chapters(conn, cfg, book_id, slug, doc, structure)
    conn.commit()
    return Added(slug, doc.title, structure, doc)


def _write_chapters(conn, cfg, book_id: int, slug: str, doc: Document,
                    structure: _detect.Structure) -> None:
    conn.execute("DELETE FROM chapters WHERE book_id = ?", (book_id,))
    for ch in structure.chapters:
        raw = "\n".join(doc.pages[ch.page_start - 1: ch.page_end])
        body = chapter_text(ch.title, raw, idx=ch.idx)
        tp = naming.chapter_text_path(cfg.library_root, slug, ch.idx, ch.title)
        tp.parent.mkdir(parents=True, exist_ok=True)
        tp.write_text(body, encoding="utf-8")
        conn.execute(
            """INSERT INTO chapters (book_id,idx,title,page_start,page_end,word_count,
                   text_path,body) VALUES (?,?,?,?,?,?,?,?)""",
            (book_id, ch.idx, ch.title, ch.page_start, ch.page_end,
             len(body.split()), str(tp), body),
        )


def restructure(cfg: _config.Config, slug: str, keep: list[int]) -> None:
    """Narrow a book to a subset of proposed chapters, renumbering from 1."""
    conn = _db.connect(cfg.db_path)
    book = _db.book_by_slug(conn, slug)
    pages = json.loads(naming.pages_path(cfg.library_root, slug).read_text(encoding="utf-8"))
    rows = _db.chapters_for(conn, book["id"])
    chosen = [r for r in rows if r["idx"] in keep]
    doc = Document(title=book["title"], pages=pages, fmt=book["format"])
    structure = _detect.Structure(
        [_detect.Chapter(i + 1, r["title"], r["page_start"], r["page_end"])
         for i, r in enumerate(chosen)],
        book["structure_src"], book["printed_offset"], 1.0,
    )
    for stale in (naming.book_dir(cfg.library_root, slug) / "text").glob("*.txt"):
        stale.unlink()
    _write_chapters(conn, cfg, book["id"], slug, doc, structure)
    conn.commit()


def confirm(cfg: _config.Config, slug: str) -> None:
    conn = _db.connect(cfg.db_path)
    conn.execute("UPDATE books SET confirmed = 1 WHERE slug = ?", (slug,))
    conn.commit()


def render(cfg: _config.Config, slug: str, *, speed: float = 1.0, voice: str | None = None,
           make_m4b: bool = True, on_event=None) -> dict:
    """Synthesise every chapter, then assemble an M4B. Resumable."""
    _config.require_library(cfg)
    conn = _db.connect(cfg.db_path)
    book = _db.book_by_slug(conn, slug)
    if not book:
        raise KeyError(f"no such book: {slug}")
    rows = _db.chapters_for(conn, book["id"])
    if not rows:
        raise RuntimeError("book has no chapters")

    voice_p = _config.voice_path(cfg, voice)
    if not voice_p.exists():
        raise FileNotFoundError(f"voice not found: {voice_p}")

    jobs = [
        Job(text_path=Path(r["text_path"]),
            out_path=naming.chapter_audio_path(cfg.library_root, slug, r["idx"], r["title"]),
            title=f"{r['idx']:02d} - {r['title']}")
        for r in rows
    ]
    durations = tts_render(jobs, voice_p, workers=cfg.workers, speed=speed, on_event=on_event)

    tracks: list[Track] = []
    for r, job in zip(rows, jobs):
        secs = durations.get(job.out_path, 0.0)
        conn.execute(
            "UPDATE chapters SET audio_path = ?, duration = ? WHERE id = ?",
            (str(job.out_path), secs, r["id"]),
        )
        tracks.append(Track(job.out_path, r["title"], secs))
    conn.commit()

    result = {"tracks": tracks, "total": sum(t.seconds for t in tracks)}
    if make_m4b:
        out = naming.m4b_path(cfg.library_root, slug, book["title"])
        result["m4b"] = build_m4b(tracks, out, title=book["title"], author=book["author"] or "")
    return result


def import_existing(cfg: _config.Config, folder: Path, *, title: str,
                    author: str = "", make_m4b: bool = True) -> str:
    """Adopt an already-rendered folder of chapter MP3/TXT files without re-rendering."""
    _config.require_library(cfg)
    folder = Path(folder)
    conn = _db.connect(cfg.db_path)
    slug = naming.slugify(title)
    if _db.book_by_slug(conn, slug):
        raise DuplicateSource(slug)

    mp3s = sorted(folder.glob("*.mp3"))
    if not mp3s:
        raise RuntimeError(f"no .mp3 files in {folder}")

    conn.execute(
        """INSERT INTO books (slug,title,author,source_path,format,confirmed,added_at)
           VALUES (?,?,?,?,?,1,?)""",
        (slug, title, author, str(folder), "imported", _db.now()),
    )
    book_id = conn.execute("SELECT id FROM books WHERE slug=?", (slug,)).fetchone()["id"]

    from ..tts import duration as _dur

    for i, mp3 in enumerate(mp3s, start=1):
        stem = mp3.stem
        chap_title = stem.split(" - ", 1)[1] if " - " in stem else stem
        txt = mp3.with_suffix(".txt")
        body = txt.read_text(encoding="utf-8", errors="replace") if txt.exists() else ""
        conn.execute(
            """INSERT INTO chapters (book_id,idx,title,word_count,text_path,audio_path,
                   duration,body) VALUES (?,?,?,?,?,?,?,?)""",
            (book_id, i, chap_title, len(body.split()),
             str(txt) if txt.exists() else "", str(mp3), _dur(mp3), body),
        )
    conn.commit()

    if make_m4b:
        rows = _db.chapters_for(conn, book_id)
        tracks = [Track(Path(r["audio_path"]), r["title"], r["duration"] or 0.0)
                  for r in rows if r["audio_path"]]
        if tracks:
            out = naming.m4b_path(cfg.library_root, slug, title)
            build_m4b(tracks, out, title=title, author=author)
    return slug


def doctor(cfg: _config.Config) -> list[tuple[Path, list[str]]]:
    """Audit the library for naming-protocol violations."""
    problems: list[tuple[Path, list[str]]] = []
    root = cfg.library_root
    if not root.exists():
        return problems
    for path in root.rglob("*"):
        if path.is_dir() or path.name in {"library.db", "pages.json"}:
            continue
        if path.name.startswith("library.db"):
            continue
        bad = naming.violations(path)
        if bad:
            problems.append((path, bad))
    return problems


def scan_inbox(cfg: _config.Config) -> list[tuple[Path, str]]:
    """Ingest everything sitting in the inbox and leave it empty."""
    results: list[tuple[Path, str]] = []
    inbox = cfg.inbox
    if not inbox.is_dir():
        return results
    for item in sorted(inbox.iterdir()):
        if item.is_dir() or item.name.startswith("."):
            continue
        try:
            added = add(cfg, item, move=True)
            results.append((item, f"filed as {added.slug}"))
        except DuplicateSource as dup:
            results.append((item, f"duplicate of {dup.slug} -- left in place"))
        except Exception as exc:
            results.append((item, f"FAILED: {exc}"))
    return results
