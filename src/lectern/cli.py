"""Command line interface."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import config as _config
from . import db as _db
from . import library


def _fmt_hms(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def _parse_keep(spec: str, available: list[int]) -> list[int]:
    """Accept '1-12', '1,3,5', '1-3,7' or 'all'."""
    spec = spec.strip().lower()
    if spec in {"", "all", "*"}:
        return available
    keep: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            keep.extend(range(int(a), int(b) + 1))
        elif part:
            keep.append(int(part))
    return [k for k in keep if k in available]


def _show_structure(added_structure, title: str) -> None:
    s = added_structure
    print(f"\n  {title}")
    print(
        f"  structure from: {s.source}"
        + (f"   printed->PDF offset: +{s.printed_offset}" if s.printed_offset is not None else "")
        + f"   confidence: {s.confidence:.0%}"
    )
    for note in s.notes:
        print(f"    - {note}")
    print(f"\n  {'#':>3}  {'pages':>11}  {'words':>8}  {'~audio':>8}  title")
    total_w = 0
    for c in s.chapters:
        total_w += c.word_count
        est = c.word_count / 165 * 60
        print(
            f"  {c.idx:>3}  {c.page_start:>4}-{c.page_end:<6}  {c.word_count:>8}  "
            f"{_fmt_hms(est):>8}  {c.title[:52]}"
        )
    print(
        f"\n  {len(s.chapters)} chapters, {total_w:,} words, ~{total_w / 165 / 60:.1f} h of audio\n"
    )


def cmd_add(args) -> int:
    cfg = _config.load()
    try:
        added = library.add(cfg, args.target, title=args.title)
    except library.DuplicateSource as dup:
        print(f"Already in the library as '{dup.slug}'. Nothing to do.")
        return 0
    except _config.LibraryUnavailable as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    for note in added.document.notes:
        print(f"  {note}")
    _show_structure(added.structure, added.title)

    if args.yes:
        library.confirm(cfg, added.slug)
    else:
        try:
            reply = input("  Looks right? [Y/n/edit] ").strip().lower()
        except EOFError:
            reply = "y"
        if reply.startswith("n"):
            print(f"  Left unconfirmed. Adjust with: lectern chapters {added.slug} --keep 1-12")
            return 0
        if reply.startswith("e"):
            avail = [c.idx for c in added.structure.chapters]
            spec = input(f"  Keep which chapters? [{avail[0]}-{avail[-1]}] ").strip()
            keep = _parse_keep(spec, avail)
            if keep:
                library.restructure(cfg, added.slug, keep)
                print(f"  Kept {len(keep)} chapters.")
        library.confirm(cfg, added.slug)

    print(f"  Added as '{added.slug}'.  Render with: lectern render {added.slug}")
    return 0


def cmd_chapters(args) -> int:
    cfg = _config.load()
    conn = _db.connect(cfg.db_path)
    book = _db.book_by_slug(conn, args.slug)
    if not book:
        print(f"no such book: {args.slug}", file=sys.stderr)
        return 1
    rows = _db.chapters_for(conn, book["id"])
    if args.keep:
        keep = _parse_keep(args.keep, [r["idx"] for r in rows])
        library.restructure(cfg, args.slug, keep)
        library.confirm(cfg, args.slug)
        print(f"kept {len(keep)} chapters")
        rows = _db.chapters_for(conn, _db.book_by_slug(conn, args.slug)["id"])
    print(f"\n  {book['title']}")
    print(f"  {'#':>3}  {'pages':>11}  {'words':>8}  {'audio':>9}  title")
    for r in rows:
        pages = f"{r['page_start']}-{r['page_end']}" if r["page_start"] else "-"
        dur = _fmt_hms(r["duration"]) if r["duration"] else "-"
        print(f"  {r['idx']:>3}  {pages:>11}  {r['word_count']:>8}  {dur:>9}  {r['title'][:52]}")
    print()
    return 0


def cmd_render(args) -> int:
    cfg = _config.load()
    try:
        _config.require_library(cfg)
    except _config.LibraryUnavailable as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    free_gb = cfg.free_bytes() / 1e9
    print(f"  library: {cfg.library_root}  ({free_gb:.1f} GB free)  workers: {cfg.workers}")
    if free_gb < 1.0:
        print("  refusing to start: less than 1 GB free", file=sys.stderr)
        return 2

    def on_event(kind, job, secs):
        if kind == "start":
            print(f"  .. {job.title}")
        elif kind == "done":
            print(f"  ok {job.title}  ({_fmt_hms(secs)})")
        elif kind == "skip":
            print(f"  -- {job.title} (already rendered)")
        elif kind == "fail":
            print(f"  !! {job.title} FAILED")

    try:
        result = library.render(
            cfg,
            args.slug,
            speed=args.speed,
            voice=args.voice,
            make_m4b=not args.no_m4b,
            on_event=on_event,
        )
    except (KeyError, FileNotFoundError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"\n  total audio: {_fmt_hms(result['total'])}")
    if result.get("m4b"):
        print(f"  audiobook:   {result['m4b']}")
    return 0


def cmd_find(args) -> int:
    cfg = _config.load()
    conn = _db.connect(cfg.db_path)
    hits = _db.search(conn, args.query, limit=args.limit)
    if not hits:
        print("no matches")
        return 0
    for h in hits:
        page = f" p{h['page_start']}" if h["page_start"] else ""
        print(f"\n  {h['book_title']} — ch{h['idx']} {h['chapter_title']}{page}")
        print(f"    {h['snippet']}")
    print()
    return 0


def cmd_list(args) -> int:
    cfg = _config.load()
    conn = _db.connect(cfg.db_path)
    rows = conn.execute(
        """SELECT b.slug,b.title,b.confirmed,COUNT(c.id) n,
                  COALESCE(SUM(c.duration),0) secs,
                  SUM(CASE WHEN c.audio_path IS NOT NULL AND c.audio_path <> ''
                           THEN 1 ELSE 0 END) done
           FROM books b LEFT JOIN chapters c ON c.book_id=b.id
           GROUP BY b.id ORDER BY b.added_at DESC"""
    ).fetchall()
    if not rows:
        print("library is empty")
        return 0
    print(f"\n  {'slug':<28} {'ch':>3} {'audio':>4} {'length':>9}  title")
    for r in rows:
        print(
            f"  {r['slug']:<28} {r['n']:>3} {r['done'] or 0:>4} "
            f"{_fmt_hms(r['secs']):>9}  {r['title'][:44]}"
        )
    print()
    return 0


def cmd_doctor(args) -> int:
    cfg = _config.load()
    problems = library.doctor(cfg)
    if not problems:
        print("naming protocol: no violations")
        return 0
    for path, issues in problems:
        print(f"  {path}")
        for i in issues:
            print(f"    - {i}")
    print(f"\n{len(problems)} file(s) violate the naming protocol")
    return 1


def cmd_inbox(args) -> int:
    cfg = _config.load()
    cfg.inbox.mkdir(parents=True, exist_ok=True)
    results = library.scan_inbox(cfg)
    if not results:
        print(f"inbox empty: {cfg.inbox}")
        return 0
    for path, outcome in results:
        print(f"  {path.name}: {outcome}")
    return 0


def cmd_import(args) -> int:
    cfg = _config.load()
    try:
        slug = library.import_existing(
            cfg,
            Path(args.folder),
            title=args.title,
            author=args.author or "",
            make_m4b=not args.no_m4b,
        )
    except (RuntimeError, library.DuplicateSource) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"imported as '{slug}'")
    return 0


def cmd_serve(args) -> int:
    from .web.app import serve

    cfg = _config.load()
    serve(cfg, host=args.host, port=args.port)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="lectern", description="Reading and study assistant")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("add", help="ingest a file or URL and propose chapters")
    a.add_argument("target")
    a.add_argument("--title")
    a.add_argument("-y", "--yes", action="store_true", help="accept the proposal without asking")
    a.set_defaults(func=cmd_add)

    c = sub.add_parser("chapters", help="show or narrow a book's chapters")
    c.add_argument("slug")
    c.add_argument("--keep", help="e.g. 1-12 or 1,3,5")
    c.set_defaults(func=cmd_chapters)

    r = sub.add_parser("render", help="synthesise audio and build the audiobook")
    r.add_argument("slug")
    r.add_argument("--speed", type=float, default=1.0)
    r.add_argument("--voice")
    r.add_argument("--no-m4b", action="store_true", help="skip assembling the M4B audiobook")
    r.set_defaults(func=cmd_render)

    f = sub.add_parser("find", help="full-text search the library")
    f.add_argument("query")
    f.add_argument("--limit", type=int, default=10)
    f.set_defaults(func=cmd_find)

    sub.add_parser("list", help="list books").set_defaults(func=cmd_list)
    sub.add_parser("doctor", help="audit naming protocol").set_defaults(func=cmd_doctor)
    sub.add_parser("inbox", help="file everything in the inbox").set_defaults(func=cmd_inbox)

    i = sub.add_parser("import", help="adopt an already-rendered folder")
    i.add_argument("folder")
    i.add_argument("--title", required=True)
    i.add_argument("--author")
    i.add_argument("--no-m4b", action="store_true")
    i.set_defaults(func=cmd_import)

    s = sub.add_parser("serve", help="run the web library")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8765)
    s.set_defaults(func=cmd_serve)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
