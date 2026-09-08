"""PDF extraction via PyMuPDF, with glyph repair and a cross-check against poppler.

PyMuPDF is used rather than poppler because poppler silently discards Private Use Area
ligature glyphs; see :mod:`lectern.repair.glyphs`.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from ..repair import glyphs
from . import Document, file_hash


def _poppler_word_count(path: Path) -> int | None:
    """Second opinion on how much text is really there (detects scanned PDFs)."""
    if not shutil.which("pdftotext"):
        return None
    try:
        out = subprocess.run(
            ["pdftotext", str(path), "-"], capture_output=True, timeout=180
        )
    except (subprocess.SubprocessError, OSError):
        return None
    return len(out.stdout.decode("utf-8", "replace").split())


def load(path: Path) -> Document:
    import pymupdf

    doc = pymupdf.open(path)
    pages = [p.get_text("text") for p in doc]
    meta = doc.metadata or {}

    # Infer the glyph mapping once across the whole document: rare codepoints need the
    # statistics of the full text, not of a single page.
    joined = "\n\f\n".join(pages)
    words = glyphs.load_dictionary()
    fixed, report = glyphs.repair(joined, words)
    pages = fixed.split("\n\f\n")

    notes = [report.summary()]
    if report.unresolved:
        notes.append(
            "WARNING: some glyphs could not be inferred; text may still be corrupt"
        )

    poppler_words = _poppler_word_count(path)
    our_words = len(fixed.split())
    if our_words < 100 * len(pages) / 10:  # implausibly little text for the page count
        notes.append(
            "WARNING: very little extractable text -- this may be a scanned PDF needing OCR"
        )
    if poppler_words and our_words and abs(poppler_words - our_words) / our_words > 0.25:
        notes.append(
            f"note: poppler saw {poppler_words} words vs our {our_words} (layout differences)"
        )

    title = (meta.get("title") or "").strip() or path.stem
    return Document(
        title=title,
        author=(meta.get("author") or "").strip(),
        pages=pages,
        fmt="pdf",
        source_path=path,
        source_hash=file_hash(path),
        notes=notes,
    )
