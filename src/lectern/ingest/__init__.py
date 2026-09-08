"""Turn any input into a Document: a per-page text list plus metadata.

Keeping text page-by-page (rather than one blob) is what later lets a citation name an
exact printed page, and lets chapter boundaries be expressed as page ranges.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

EBOOK_EXT = {".epub", ".mobi", ".azw3", ".azw", ".docx", ".odt", ".rtf", ".fb2", ".lit"}


@dataclass
class Document:
    title: str
    pages: list[str]
    author: str = ""
    fmt: str = ""
    source_path: Path | None = None
    source_hash: str = ""
    notes: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(self.pages)

    @property
    def word_count(self) -> int:
        return len(self.text.split())


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load(target: str | Path) -> Document:
    """Dispatch on the input's shape: URL, PDF, ebook/office format, or plain text."""
    s = str(target)
    if s.startswith(("http://", "https://")):
        from . import url as _url

        return _url.load(s)

    path = Path(s).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"no such file: {path}")

    ext = path.suffix.lower()
    if ext == ".pdf":
        from . import pdf as _pdf

        return _pdf.load(path)
    if ext in EBOOK_EXT:
        from . import ebook as _ebook

        return _ebook.load(path)
    if ext in {".txt", ".md", ".text"}:
        body = path.read_text(encoding="utf-8", errors="replace")
        return Document(
            title=path.stem,
            pages=[body],
            fmt=ext.lstrip("."),
            source_path=path,
            source_hash=file_hash(path),
        )
    raise ValueError(f"unsupported input type: {ext or path.name}")
