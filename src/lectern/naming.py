"""The naming protocol -- the single source of truth for every path Lectern creates.

Nothing elsewhere in the codebase may build a filename by hand. Two contexts exist
because they have genuinely different jobs:

*Player names* live inside a book folder and must sort correctly and read well in an
audio player, so they keep spaces and title case::

    07 - Thinking.mp3

*Portable names* can leave their folder -- exports, notes, bibliographies -- and must
still be identifiable months later. This is the "78 documents called Notes" failure the
book warns about, so they carry the source, the unit and an ISO date::

    college-success--ch07--2026-09-08--managing-resources.md
"""

from __future__ import annotations

import datetime as _dt
import re
import unicodedata
from pathlib import Path

SEP = "--"
#  Characters that are illegal on NTFS (where the library lives) or awkward in shells.
_ILLEGAL = r'<>:"/\|?*'
_SLUG_OK = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_PORTABLE_OK = re.compile(
    r"^[a-z0-9-]+(?:--[a-z0-9-]+)*(?:\.[a-z0-9]+)+$"
)


def slugify(text: str, *, max_len: int = 60) -> str:
    """Fold arbitrary text to lowercase-kebab ASCII.

    Lowercase throughout is deliberate: the library sits on a case-insensitive
    filesystem, so ``Notes`` and ``notes`` would collide.
    """
    norm = unicodedata.normalize("NFKD", text)
    ascii_only = norm.encode("ascii", "ignore").decode("ascii")
    ascii_only = ascii_only.replace("&", " and ")
    kebab = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_only).strip("-").lower()
    kebab = re.sub(r"-{2,}", "-", kebab)
    if len(kebab) > max_len:
        kebab = kebab[:max_len].rstrip("-")
    return kebab or "untitled"


def safe_title(text: str) -> str:
    """Keep a human title usable as a filename component without slugifying it."""
    cleaned = "".join(" " if c in _ILLEGAL else c for c in text)
    cleaned = cleaned.replace("\n", " ").replace("\t", " ")
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" .")
    return cleaned or "Untitled"


def chapter_stem(idx: int, title: str) -> str:
    """Player-facing name: ``07 - Thinking``. Zero-padded so players sort correctly."""
    return f"{idx:02d} - {safe_title(title)}"


def portable_name(
    source_slug: str,
    unit: str,
    descriptor: str,
    ext: str,
    *,
    date: _dt.date | None = None,
) -> str:
    """Self-describing name for anything that may leave its folder.

    ``{source-slug}--{unit}--{ISO-date}--{descriptor}.{ext}``
    """
    parts = [slugify(source_slug), slugify(unit)]
    if date is not None:
        parts.append(date.isoformat())
    parts.append(slugify(descriptor))
    ext = ext.lower().lstrip(".")
    return SEP.join(p for p in parts if p) + f".{ext}"


def today() -> _dt.date:
    return _dt.date.today()


# --------------------------------------------------------------------------- paths


def book_dir(library_root: Path, slug: str) -> Path:
    return Path(library_root) / "books" / slug


def chapter_text_path(library_root: Path, slug: str, idx: int, title: str) -> Path:
    return book_dir(library_root, slug) / "text" / f"{chapter_stem(idx, title)}.txt"


def chapter_audio_path(library_root: Path, slug: str, idx: int, title: str) -> Path:
    return book_dir(library_root, slug) / "audio" / f"{chapter_stem(idx, title)}.mp3"


def m4b_path(library_root: Path, slug: str, title: str) -> Path:
    return book_dir(library_root, slug) / f"{safe_title(title)}.m4b"


def pages_path(library_root: Path, slug: str) -> Path:
    return book_dir(library_root, slug) / "pages.json"


def source_path(library_root: Path, slug: str, ext: str) -> Path:
    return book_dir(library_root, slug) / f"source.{ext.lower().lstrip('.')}"


# ---------------------------------------------------------------------- validation


def violations(path: Path) -> list[str]:
    """Report why ``path`` breaks the protocol. Empty list means compliant."""
    name = Path(path).name
    found: list[str] = []
    if any(c in name for c in _ILLEGAL):
        found.append(f"illegal character in {name!r}")
    if name != name.strip():
        found.append(f"leading/trailing whitespace in {name!r}")
    if name.lower() in {"notes", "notes.md", "untitled", "untitled.txt", "new.md"}:
        found.append(f"ambiguous name {name!r} -- unidentifiable once filed")
    if SEP in name and not _PORTABLE_OK.match(name):
        found.append(f"portable name {name!r} is malformed")
    try:
        name.encode("ascii")
    except UnicodeEncodeError:
        found.append(f"non-ASCII characters in {name!r}")
    return found


def is_valid_slug(slug: str) -> bool:
    return bool(_SLUG_OK.match(slug))
