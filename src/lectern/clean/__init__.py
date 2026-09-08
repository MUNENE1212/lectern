"""Normalise extracted text for speech.

Everything removed here is page furniture that a reader's eye skips but a synthesiser
would dutifully pronounce: running heads, bare page numbers, figure credits, bullet
glyphs and raw URLs.
"""

from __future__ import annotations

import re

_BARE_NUM = re.compile(r"^\d{1,4}$")
_RUNNING_HEAD = re.compile(r"^\d{1,2}(?:\.\d{1,2})?\s*[•|]\s*.+$")
_FIGURE_STUB = re.compile(r"^(?:Figure|Table|Exhibit)\s+\d+\.\d+\.?$", re.I)
_CREDIT = re.compile(r"^(?:Credit|Source|Photo)\s*[:.]", re.I)
_FIG_CREDIT = re.compile(r"^(?:Figure|Table)\s+\d+\.\d+\s*Credit", re.I)
_BULLET_ONLY = re.compile(r"^[•\-–—*●▪◦⁃]+$")
_LEAD_BULLET = re.compile(r"^[•●▪◦⁃]\s*")
_URL = re.compile(r"https?://\S+|www\.\S+")
_INLINE_CREDIT = re.compile(r"\(credit[^)]*\)", re.I)
_ATTRIBUTION = "access for free at openstax.org"


def for_tts(text: str, *, drop_urls: bool = True) -> str:
    out: list[str] = []
    for raw in text.split("\n"):
        s = raw.strip()
        if not s:
            continue
        low = s.lower()
        if low == _ATTRIBUTION:
            continue
        if _BARE_NUM.match(s):
            continue
        if _RUNNING_HEAD.match(s):
            continue
        if _FIGURE_STUB.match(s) or _CREDIT.match(s) or _FIG_CREDIT.match(s):
            continue
        if _BULLET_ONLY.match(s):
            continue
        s = _LEAD_BULLET.sub("", s)
        s = _INLINE_CREDIT.sub("", s)
        if drop_urls:
            s = _URL.sub("", s)
        s = re.sub(r"\s{2,}", " ", s).strip()
        if s:
            out.append(s)
    body = "\n".join(out)
    return re.sub(r"\n{3,}", "\n\n", body)


def chapter_text(title: str, body: str, *, idx: int | None = None) -> str:
    """Prefix a spoken chapter heading so the listener knows where they are."""
    head = f"Chapter {idx}. {title}." if idx is not None else f"{title}."
    return f"{head}\n\n{for_tts(body)}"
