"""EPUB/MOBI/DOCX and friends, via calibre's ebook-convert.

These formats carry real structure and clean text, so they need none of the glyph
archaeology a PDF does.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from . import Document, file_hash

CALIBRE_HINTS = (
    "install calibre, or add ~/.local/calibre to PATH "
    "(the binaries live there on this machine)"
)


def _ebook_convert() -> str:
    exe = shutil.which("ebook-convert") or str(Path.home() / ".local/calibre/ebook-convert")
    if not Path(exe).exists() and not shutil.which(exe):
        raise RuntimeError(f"ebook-convert not found -- {CALIBRE_HINTS}")
    return exe


def load(path: Path) -> Document:
    exe = _ebook_convert()
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "converted.txt"
        proc = subprocess.run(
            [exe, str(path), str(out)], capture_output=True, text=True, timeout=900
        )
        if proc.returncode != 0 or not out.exists():
            raise RuntimeError(f"ebook-convert failed on {path.name}: {proc.stderr[-400:]}")
        body = out.read_text(encoding="utf-8", errors="replace")

    return Document(
        title=path.stem,
        pages=[body],
        fmt=path.suffix.lstrip(".").lower(),
        source_path=path,
        source_hash=file_hash(path),
        notes=["converted via calibre ebook-convert"],
    )
